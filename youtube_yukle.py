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
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
    )

def _durum_bloku(gizlilik, cocuk_icerigi, yayin_zamani):
    st = {"selfDeclaredMadeForKids": bool(cocuk_icerigi)}
    if yayin_zamani:
        # zamanlanmis yayin: video 'private' yuklenir, publishAt'ta otomatik public olur
        st["privacyStatus"] = "private"
        st["publishAt"] = yayin_zamani
    else:
        st["privacyStatus"] = gizlilik
    return st


def yukle(dosya, baslik, aciklama, etiketler, gizlilik="private", kategori="27", cocuk_icerigi=False, kapak=None, yayin_zamani=None, ilk_yorum=None):
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
        "status": _durum_bloku(gizlilik, cocuk_icerigi, yayin_zamani),
    }
    media = MediaFileUpload(dosya, chunksize=-1, resumable=True, mimetype="video/mp4")
    istek = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    yanit = None
    while yanit is None:
        _, yanit = istek.next_chunk()
    vid = yanit["id"]
    print(f"✓ Yüklendi: https://youtu.be/{vid}" + (f"  (yayın: {yayin_zamani} UTC)" if yayin_zamani else f"  (gizlilik: {gizlilik})"))
    # Çarpıcı kapak fotoğrafını yükle (kanal doğrulanmamışsa atlanır, video kaybolmaz)
    if kapak and os.path.exists(kapak):
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(kapak)).execute()
            print("✓ Kapak fotoğrafı ayarlandı")
        except Exception as e:
            print(f"! Kapak ayarlanamadı (kanal doğrulanmamış olabilir): {str(e)[:120]}")
    if ilk_yorum:
        try:
            ins = yt.commentThreads().insert(
                part="snippet",
                body={"snippet": {"videoId": vid,
                                  "topLevelComment": {"snippet": {"textOriginal": ilk_yorum}}}},
            ).execute()
            print("✓ Abone yorumu eklendi: " + ins["snippet"]["topLevelComment"]["id"])
        except Exception as e:
            print(f"! Yorum eklenemedi: {str(e)[:160]}")
    return vid
