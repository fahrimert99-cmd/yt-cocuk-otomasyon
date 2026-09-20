#!/usr/bin/env python3
import os
import time
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

VIDEO_ID = os.environ["VIDEO_ID"]
TARGET = os.environ["TARGET_PUBLISH_AT"]
creds = Credentials(
    token=None,
    refresh_token=os.environ["YT_REFRESH_TOKEN"],
    token_uri="https://oauth2.googleapis.com/token",
    client_id=os.environ["YT_CLIENT_ID"],
    client_secret=os.environ["YT_CLIENT_SECRET"],
    scopes=["https://www.googleapis.com/auth/youtube.force-ssl",
            "https://www.googleapis.com/auth/yt-analytics.readonly"],
)
creds.refresh(Request())
yt = build("youtube", "v3", credentials=creds)
item = yt.videos().list(part="snippet,status", id=VIDEO_ID).execute().get("items", [])
if not item:
    raise SystemExit(f"Video bulunamadı: {VIDEO_ID}")
old = item[0]
sn = old.get("snippet", {})
st = old.get("status", {})
if st.get("privacyStatus") != "private":
    raise SystemExit(f"Güvenlik durdurması: video private değil ({st.get('privacyStatus')})")
body = {
    "id": VIDEO_ID,
    "snippet": {
        "title": sn.get("title", ""),
        "categoryId": sn.get("categoryId", "28"),
        "description": sn.get("description", ""),
        "tags": sn.get("tags", []),
    },
    "status": {
        "privacyStatus": "private",
        "publishAt": TARGET,
        "selfDeclaredMadeForKids": bool(st.get("selfDeclaredMadeForKids", False)),
    },
}
if "containsSyntheticMedia" in st:
    body["status"]["containsSyntheticMedia"] = bool(st["containsSyntheticMedia"])
updated = yt.videos().update(part="snippet,status", body=body).execute()
print("UPDATE_RESPONSE", updated.get("id"), updated.get("status", {}).get("publishAt"), updated.get("status", {}).get("privacyStatus"))
time.sleep(5)
check = yt.videos().list(part="status,snippet", id=VIDEO_ID).execute()["items"][0]
print("RESCHEDULE_CHECK", VIDEO_ID, check["status"].get("privacyStatus"), check["status"].get("publishAt"), check["snippet"].get("title"))
if check["status"].get("publishAt") != TARGET:
    raise SystemExit(f"Saat doğrulanamadı: beklenen {TARGET}, dönen {check['status'].get('publishAt')}")
