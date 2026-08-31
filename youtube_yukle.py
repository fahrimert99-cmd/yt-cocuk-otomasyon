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


def yukle(dosya, baslik, aciklama, etiketler, gizlilik="private", kategori="27", cocuk_icerigi=False, kapak=None, yayin_zamani=None):
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
    return vid


def video_public(video_id):
    """Video herkese acik (public) mi kontrol eder.
    Zamanlanmis (private + publishAt) video yayin saatine kadar 'private'
    doner; bu videoya yorum atmak 403 verir. Yorumu ancak public olunca at.
    API hatasi / bulunamama durumunda guvenli tarafta kal: False don (ertele).
    """
    try:
        yt = build("youtube", "v3", credentials=_kimlik())
        r = yt.videos().list(part="status", id=video_id).execute()
        items = r.get("items", [])
        if not items:
            return False
        return items[0].get("status", {}).get("privacyStatus") == "public"
    except Exception:
        return False


def sil(video_id):
    """Videoyu kanaldan tamamen siler (geri alinamaz).
    Yeniden uretimde eski (yedek sesli) surumu kaldirmak icin kullanilir."""
    yt = build("youtube", "v3", credentials=_kimlik())
    yt.videos().delete(id=video_id).execute()
    print(f"✓ Eski video silindi: {video_id}")


def _oynatma_listesi_bul_veya_olustur(yt, ad, aciklama=""):
    """Verilen adda oynatma listesi varsa id'sini döner, yoksa oluşturur (public)."""
    tok = None
    while True:
        r = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=tok).execute()
        for it in r.get("items", []):
            if it["snippet"]["title"] == ad:
                return it["id"]
        tok = r.get("nextPageToken")
        if not tok:
            break
    r = yt.playlists().insert(part="snippet,status", body={
        "snippet": {"title": ad, "description": aciklama},
        "status": {"privacyStatus": "public"}}).execute()
    return r["id"]


def oynatma_listesine_ekle(video_id, liste_adi, liste_aciklama=""):
    """Videoyu adı verilen oynatma listesine ekler (liste yoksa oluşturur).
    İzlenme süresi/oturum uzunluğu için: kategoriye göre grupla."""
    yt = build("youtube", "v3", credentials=_kimlik())
    pid = _oynatma_listesi_bul_veya_olustur(yt, liste_adi, liste_aciklama)
    yt.playlistItems().insert(part="snippet", body={
        "snippet": {"playlistId": pid,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
    return pid


def yorum_at(video_id, metin):
    """Kanaldan videoya ust duzey yorum ekler (video PUBLIC olmali)."""
    yt = build("youtube", "v3", credentials=_kimlik())
    ins = yt.commentThreads().insert(
        part="snippet",
        body={"snippet": {"videoId": video_id,
                          "topLevelComment": {"snippet": {"textOriginal": metin}}}},
    ).execute()
    return ins["snippet"]["topLevelComment"]["id"]
