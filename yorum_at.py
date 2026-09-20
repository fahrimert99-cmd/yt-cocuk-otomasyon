# -*- coding: utf-8 -*-
"""Kendi videolarına videoya özgü yorumu güvenli biçimde gönderir.

Gönderimden önce hedef videonun OAuth hesabının kanalına ait ve public olduğunu
doğrular; aynı kanalın aynı metni daha önce göndermiş olması halinde tekrar
yorum eklemez. Bu bir spam filtresi aşma mekanizması değildir.
"""
import hashlib, json, os, re, sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DURUM = "durum.json"


def yorum_metni_uret(veri):
    """Trend senaryosundan kısa, videoya özgü ve tanıtımsız yorum üretir."""
    if not isinstance(veri, dict):
        return "Bu videodaki ayrıntılardan hangisini daha önce fark etmiştin?"
    yorum = str(veri.get("yorum") or "").strip()
    if yorum and len(yorum) <= 280 and "http" not in yorum.lower():
        return yorum
    baslik = re.sub(r"[\U00010000-\U0010ffff]", "", str(veri.get("baslik") or "")).strip()
    baslik = re.sub(r"\s+", " ", baslik).rstrip("!?., ")
    return f"{baslik or 'Bu videodaki konu'} hakkında sen en çok hangi ayrıntıyı gözden kaçırıyorsun?"


def _kimlik():
    return Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
    )


def _kanal_ve_video_dogrula(yt, video_id):
    """Hedef video OAuth hesabının kanalı mı ve herkese açık mı kontrol eder."""
    mine = yt.channels().list(part="id", mine=True).execute().get("items", [])
    kanal_id = (mine[0].get("id") if mine else "")
    video = yt.videos().list(part="snippet,status", id=video_id).execute().get("items", [])
    if not kanal_id or not video:
        raise RuntimeError("kanal veya video doğrulanamadı")
    item = video[0]
    if item.get("snippet", {}).get("channelId") != kanal_id:
        raise RuntimeError("hedef video OAuth kanalına ait değil; yorum durduruldu")
    if item.get("status", {}).get("privacyStatus") != "public":
        raise RuntimeError("video henüz public değil; yorum ertelendi")
    return kanal_id


def gonder(video_id, metin):
    """Yorumu güvenli ve idempotent biçimde gönderir; mevcut id'yi döndürür."""
    metin = re.sub(r"\s+", " ", str(metin or "")).strip()
    if not metin or len(metin) > 280 or "http" in metin.lower():
        raise ValueError("yorum boş, çok uzun veya bağlantı içeriyor")
    yt = build("youtube", "v3", credentials=_kimlik())
    kanal_id = _kanal_ve_video_dogrula(yt, video_id)
    # Ağ zaman aşımı sonrası tekrar çalışmada aynı yorumu ikinci kez ekleme.
    liste = yt.commentThreads().list(part="snippet", videoId=video_id,
                                     maxResults=100, order="time").execute()
    for thread in liste.get("items", []):
        top = thread.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
        author = (top.get("authorChannelId") or {}).get("value")
        if author == kanal_id and (top.get("textOriginal") or "").strip() == metin:
            return thread.get("id") or top.get("id")
    ins = yt.commentThreads().insert(
        part="snippet",
        body={"snippet": {"videoId": video_id,
                          "topLevelComment": {"snippet": {"textOriginal": metin}}}},
    ).execute()
    return ins["snippet"]["topLevelComment"]["id"]

def main():
    if not os.path.exists(DURUM):
        print("durum.json yok"); return
    with open(DURUM, encoding="utf-8-sig") as f:
        durum = json.load(f)
    bek = durum.get("bekleyen_yorum")
    if not bek or not bek.get("video_id"):
        print("bekleyen yorum yok"); return

    try:
        yorum_id = gonder(bek["video_id"], bek["metin"])
        print("OK yorum eklendi/mevcut:", yorum_id)
        durum["bekleyen_yorum"] = None
        durum["son_yorum"] = "OK " + bek["video_id"]
    except Exception as e:
        print("HATA yorum eklenemedi:", str(e)[:200])
        durum["son_yorum"] = "HATA " + str(e)[:150]
    with open(DURUM, "w", encoding="utf-8") as f:
        json.dump(durum, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
