#!/usr/bin/env python

import requests
import time
import os.path
import pickle
import argparse
import threading
import datetime
import logging

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# If modifying these SCOPES, delete the file token.pickle.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

DefaultRecordTTL = 3 * 60 * 60  # 3 hours
DefaultGCInterval = 60  # 1 min
DefaultPollingInterval = 5 * 60  # 5 mins

# Configure the logging module
logging.basicConfig(
    level=logging.DEBUG,  # Set the root logger level to DEBUG
    format="%(asctime)s [%(levelname)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Create a logger instance for your module or application
logger = logging.getLogger("gmail-bot")


class HistRecords:
    def __init__(self):
        self.records = []
        self.lock = threading.Lock()
        self.ttl = DefaultRecordTTL

    def run(self):
        def stale(tup):
            dur = datetime.datetime.now() - tup[0]
            return dur.total_seconds() > self.ttl

        # periodically check the list and remove old records
        while True:
            with self.lock:
                self.records = [x for x in self.records if not stale(x)]
            time.sleep(DefaultGCInterval)

    def add_record(self, msg_info):
        with self.lock:
            if not self.__exist__(msg_info):
                self.records.append((datetime.datetime.now(), msg_info))

    def exist(self, msg_info):
        with self.lock:
            return self.__exist__(msg_info)

    def __exist__(self, msg_info):
        for r in self.records:
            if msg_info.equal(r[1]):
                return True
        return False


class MessageInfo:
    def __init__(self, msg_from, msg_to, msg_subject, msg_date):
        self.msg_from = msg_from
        self.msg_to = msg_to
        self.msg_subject = msg_subject
        self.msg_date = msg_date

    def equal(self, other):
        return (
            self.msg_from == other.msg_from
            and self.msg_to == other.msg_to
            and self.msg_subject == other.msg_subject
            and self.msg_date == other.msg_date
        )


def get_credentials(token_file):
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(token_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
    return creds


def poll_gmail_account(service, keywords):
    # get the qualified emails
    # query = "is:unread " + " OR ".join(f"{keyword}" for keyword in keywords)
    query = "is:unread"
    results = service.users().messages().list(userId="me", q=query).execute()
    messages = results.get("messages", [])
    msg_infos = []

    for message in messages:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message["id"], format="full")
            .execute()
        )

        msg_from = ""
        msg_subject = ""
        msg_to = ""
        msg_date = ""

        for header in msg["payload"]["headers"]:
            if header["name"] == "Return-Path":
                msg_from = header["value"]
            if header["name"] == "Subject":
                msg_subject = header["value"]
            if header["name"] == "Delivered-To":
                msg_to = header["value"]
            if header["name"] == "Date":
                msg_date = header["value"]

        for keyword in keywords:
            if keyword in msg_subject or keyword in msg_subject:
                msg_infos.append(
                    MessageInfo(msg_from, msg_to, msg_subject, msg_date)
                )

    return msg_infos


def send_msg_to_lark(info, webhook, hist_rds):
    headers = {"Content-Type": "application/json"}
    data = {
        "msg_type": "text",
        "content": {
            "text": f"From: {info.msg_from}\n"
            + f"To: {info.msg_to}\n"
            + f"Subject: {info.msg_subject}\n"
            + f"Date: {info.msg_date}\n"
        },
    }
    response = requests.post(webhook, json=data, headers=headers)
    code = response.status_code
    if code < 200 or code >= 300:
        print(f"fail to send request to the lark with status code: {code}")
        return
    hist_rds.add_record(info)


def monitor_gmail_account(keywords, token_file, webhook, hist_rds):
    creds = get_credentials(token_file)
    service = build("gmail", "v1", credentials=creds)

    while True:
        msg_infos = poll_gmail_account(service, keywords)
        for msg_info in msg_infos:
            if hist_rds.exist(msg_info):
                logger.debug(f"{msg_info} will not be sent")
            else:
                send_msg_to_lark(msg_info, webhook, hist_rds)
        time.sleep(DefaultPollingInterval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gmail bot")
    parser.add_argument("-t", "--token", help="path to the gmail token file")
    parser.add_argument("-w", "--webhook", help="feishu bot webhook link")
    parser.add_argument(
        "-k", "--keywords", help="list of keywords seperated by comma"
    )
    args = parser.parse_args()

    # Configure the logging module
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    keywords = []
    if args.keywords:
        keywords = args.keywords.split(",")

    hist_rds = HistRecords()

    t1 = threading.Thread(
        target=monitor_gmail_account,
        args=(
            keywords,
            args.token,
            args.webhook,
            hist_rds,
        ),
    )
    t2 = threading.Thread(target=hist_rds.run)

    t1.start()
    t2.start()

    t1.join()
    t2.join()
