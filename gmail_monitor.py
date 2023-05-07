#!/usr/bin/env python

import os.path
import base64
import pickle
import argparse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# If modifying these SCOPES, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_credentials(token_file):
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                token_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds

def monitor_gmail_account(keywords, token_file):
    creds = get_credentials(token_file)
    service = build('gmail', 'v1', credentials=creds)

    query = 'is:unread ' + ' OR '.join(f'{keyword}' for keyword in keywords)
    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])

    for message in messages:
        msg = service.users().messages().get(userId='me', id=message['id'], format='full').execute()
        msg_subject = ''
        msg_body = ''

        for header in msg['payload']['headers']:
            if header['name'] == 'subject' or header['name'] == 'Subject':
                msg_subject = header['value']
                break

        if 'parts' in msg['payload']:
            for part in msg['payload']['parts']:
                if part['mimeType'] == 'text/plain':
                    msg_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break

        print(f'Subject: {msg_subject}')
        print(f'Message: {msg_body}')
        print('---')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Gmail bot")
    parser.add_argument("-t", "--token", help="path to the gmail token file")
    args = parser.parse_args()

    keywords = ['google', 'test']
    monitor_gmail_account(keywords, args.token)

