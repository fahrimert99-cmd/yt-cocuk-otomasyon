# -*- coding: utf-8 -*-
"""Video public olduktan sonra kanaldan ilk yorumu atar (durum.json -> bekleyen_yorum)."""
import json, os, sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DURUM = "durum.json"

def main():
    if not os.path.exists(DURUM):
        print("durum.json yok"); return
    with open(DURUM, encoding="utf-8-sig") as f:
        durum = json.load(f)
    bek = durum.get("bekleyen_yorum")
    if not bek or not bek.get("video_id"):
        print("bekleyen yorum yok"); return

    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    yt = build("youtube", "v3", credentials=creds)
    try:
        ins = yt.commentThreads().insert(
            part="snippet",
            body={"snippet": {"videoId": bek["video_id"],
                              "topLevelComment": {"snippet": {"textOriginal": bek["metin"]}}}},
        ).execute()
        print("OK yorum eklendi:", ins["snippet"]["topLevelComment"]["id"])
        durum["bekleyen_yorum"] = None
        durum["son_yorum"] = "OK " + bek["video_id"]
    except Exception as e:
        print("HATA yorum eklenemedi:", str(e)[:200])
        durum["son_yorum"] = "HATA " + str(e)[:150]
    with open(DURUM, "w", encoding="utf-8") as f:
        json.dump(durum, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
