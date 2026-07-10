#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Yükleyici — IMPROVED: Retry logic + Better error handling
"""
import os
import time
import traceback
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

TOKEN_URI = "https://oauth2.googleapis.com/token"

def _kimlik():
    """OAuth2 credentials (refresh token) ile kimlik doğrula."""
    return Credentials(
        token=None,
        refresh_token=os.environ.get("YT_REFRESH_TOKEN"),
        token_uri=TOKEN_URI,
        client_id=os.environ.get("YT_CLIENT_ID"),
        client_secret=os.environ.get("YT_CLIENT_SECRET"),
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )

def yukle(dosya, baslik, aciklama, etiketler, gizlilik="private", kategori="27", 
          cocuk_icerigi=False, max_retry=3):
    """
    YouTube'a video yükle (resumable upload + retry).
    
    Args:
        dosya: MP4 dosya yolu
        baslik: Video başlığı (max 100 char)
        aciklama: Video açıklaması
        etiketler: Liste
        gizlilik: 'public' | 'unlisted' | 'private'
        kategori: 27=Eğitim, 28=Bilim&Teknoloji, 24=Eğlence
        cocuk_icerigi: Boolean (COPPA compliance)
        max_retry: Hata durumunda kaç kez retry yapılacak
    
    Returns:
        video_id (örn: "HkDcmneUbSw")
    
    Raises:
        Exception: Upload başarısız ise
    """
    
    if not os.path.exists(dosya):
        raise FileNotFoundError(f"Video dosyası bulunamadı: {dosya}")
    
    for attempt in range(max_retry):
        try:
            yt = build("youtube", "v3", credentials=_kimlik())
            
            body = {
                "snippet": {
                    "title": baslik[:100],
                    "description": aciklama,
                    "tags": etiketler,
                    "categoryId": str(kategori),
                },
                "status": {
                    "privacyStatus": gizlilik,
                    "selfDeclaredMadeForKids": bool(cocuk_icerigi),
                },
            }
            
            # Resumable upload (büyük dosyalara karşı robust)
            media = MediaFileUpload(dosya, chunksize=-1, resumable=True, mimetype="video/mp4")
            istek = yt.videos().insert(part="snippet,status", body=body, media_body=media)
            
            yanit = None
            while yanit is None:
                try:
                    status, yanit = istek.next_chunk()
                    if status:
                        print(f"      Upload ilerleme: {int(status.progress() * 100)}%")
                except HttpError as e:
                    if e.resp.status in [500, 502, 503, 504]:
                        # Server error: retry
                        print(f"      API server hatası ({e.resp.status}), retry...")
                        time.sleep(5 * (attempt + 1))
                        raise
                    else:
                        # Client error: fatal
                        raise
            
            vid = yanit["id"]
            print(f"✓ Yüklendi: https://youtu.be/{vid}  (gizlilik: {gizlilik})")
            return vid
            
        except Exception as e:
            error_msg = str(e)
            if attempt < max_retry - 1:
                wait_time = 10 * (attempt + 1)
                print(f"      ✗ Hata: {error_msg}")
                print(f"      → {wait_time}s sonra retry... ({attempt+1}/{max_retry})")
                time.sleep(wait_time)
            else:
                # Son deneme başarısız
                print(f"      ✗ Upload başarısız ({max_retry} deneme tamamlandı): {error_msg}")
                raise RuntimeError(f"YouTube upload başarısız: {error_msg}\n{traceback.format_exc()}")
    
    raise RuntimeError("YouTube upload başarısız: Bilinmeyen hata")
