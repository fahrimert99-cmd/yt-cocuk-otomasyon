#!/usr/bin/env python3
import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

VIDEO_ID = os.environ["VIDEO_ID"]
TARGET = os.environ["TARGET_PUBLISH_AT"]

client_id = os.environ["YT_CLIENT_ID"]
client_secret = os.environ["YT_CLIENT_SECRET"]
refresh_token = os.environ["YT_REFRESH_TOKEN"]
creds = Credentials(
    None,
    refresh_token=refresh_token,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=client_id,
    client_secret=client_secret,
    scopes=["https://www.googleapis.com/auth/youtube"],
)
creds.refresh(Request())
yt = build("youtube", "v3", credentials=creds)
old = yt.videos().list(part="status,snippet", id=VIDEO_ID).execute().get("items", [])
if not old:
    raise SystemExit(f"Video bulunamadı: {VIDEO_ID}")
status = old[0].get("status", {})
if status.get("privacyStatus") != "private":
    raise SystemExit(f"Güvenlik durdurması: video private değil ({status.get('privacyStatus')})")
body = {
    "id": VIDEO_ID,
    "status": {
        "privacyStatus": "private",
        "publishAt": TARGET,
        "selfDeclaredMadeForKids": bool(status.get("selfDeclaredMadeForKids", False)),
    },
}
if "containsSyntheticMedia" in status:
    body["status"]["containsSyntheticMedia"] = bool(status["containsSyntheticMedia"])
yt.videos().update(part="status", body=body).execute()
check = yt.videos().list(part="status,snippet", id=VIDEO_ID).execute()["items"][0]
print("RESCHEDULE_OK", VIDEO_ID, check["status"].get("privacyStatus"), check["status"].get("publishAt"), check["snippet"].get("title"))
