#!/usr/bin/env python

import requests
import time
import os.path
import base64
import pickle
import argparse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# If modifying these SCOPES, delete the file token.pickle.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class MessageInfo:
    def __init__(self, msg_from, msg_to, msg_subject, msg_date):
        self.msg_from = msg_from
        self.msg_to = msg_to
        self.msg_subject = msg_subject
        self.msg_date = msg_date


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


def get_msg_body(message):
    payload = message["payload"]
    headers = payload["headers"]

    for part in payload.get("parts", []):
        if part["mimeType"] == "text/plain":
            text = base64.urlsafe_b64decode(
                part["body"]["data"].encode("ASCII")
            )
            return text.decode("utf-8")
        elif part["mimeType"] == "text/html":
            html = base64.urlsafe_b64decode(
                part["body"]["data"].encode("ASCII")
            )
            return html.decode("utf-8")

    print("No message body found in payload.")
    return None


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

        msg_body = get_msg_body(msg)

        for keyword in keywords:
            if keyword in msg_subject or keyword in msg_subject:
                msg_infos.append(
                    MessageInfo(msg_from, msg_subject, msg_to, msg_date)
                )

    return msg_infos


def send_msg_to_lark(info, webhook):
    headers = {"Content-Type": "application/json"}
    data = {
        "msg_type": "text",
        "content": {
            "text": f"from: {info.msg_from}, to: {info.msg_to}, to: {info.msg_subject}, date: {info.msg_date}"
        },
    }
    response = requests.post(webhook, json=data, headers=headers)
    code = response.status_code
    if code < 200 or code >= 300:
        print(f"fail to send request to the lark with status code: {code}")


def monitor_gmail_account(keywords, token_file, interval_sec, webhook):
    creds = get_credentials(token_file)
    service = build("gmail", "v1", credentials=creds)

    while True:
        msg_infos = poll_gmail_account(service, keywords)
        for msg_info in msg_infos:
            send_msg_to_lark(msg_info, webhook)
        time.sleep(60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gmail bot")
    parser.add_argument("-t", "--token", help="path to the gmail token file")
    parser.add_argument("-w", "--webhook", help="feishu bot webhook link")
    parser.add_argument(
        "-i", "--interval", help="gmail polling interval in secs"
    )
    args = parser.parse_args()

    keywords = ["test"]
    monitor_gmail_account(keywords, args.token, args.interval, args.webhook)
