#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Yükleyici — YouTube Data API v3 (ücretsiz günlük kota)
Refresh token ile kimlik doğrular (bir kere token_al.py ile alınır).
Gerekli GitHub Secret / env: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
"""
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TOKEN_URI = "https://oauth2.googleapis.com/token"

def _kimlik():
    return Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri=TOKEN_URI,
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )

def yukle(dosya, baslik, aciklama, etiketler, gizlilik="private", kategori="27", cocuk_icerigi=False):
    """
    gizlilik: 'public' | 'unlisted' | 'public'
    kategori: 27=Eğitim, 24=Eğlence, 28=Bilim&Teknoloji, 22=İnsanlar&Bloglar
    """
    yt = build("youtube", "v3", credentials=_kimlik())
    body = {
        "snippet": {
            "title": baslik[:100],
            "description": aciklama,
            "tags": etiketler,
            "categoryId": kategori,
        },
        "status": {
            "privacyStatus": gizlilik,
            "selfDeclaredMadeForKids": bool(cocuk_icerigi),
        },
    }
    media = MediaFileUpload(dosya, chunksize=-1, resumable=True, mimetype="video/mp4")
    istek = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    yanit = None
    while yanit is None:
        _, yanit = istek.next_chunk()
    vid = yanit["id"]
    print(f"✓ Yüklendi: https://youtu.be/{vid}  (gizlilik: {gizlilik})")
    return vid
