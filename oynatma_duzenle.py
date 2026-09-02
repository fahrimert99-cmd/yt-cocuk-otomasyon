#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KANALDAKİ MEVCUT VİDEOLARI oynatma listelerine yerleştirir (toplu düzenleme).

Her videoyu başlık/açıklamasından konusuna göre sınıflandırır ve ilgili
oynatma listesine ekler (liste yoksa oluşturur). İDEMPOTENT: bir videoyu zaten
içeren listeye tekrar eklemez, dolayısıyla güvenle tekrar çalıştırılabilir.

Gerekli env (GitHub Secret): YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN
(scope: youtube.force-ssl). Kanala video YÜKLEMEZ; yalnızca oynatma listelerini
düzenler.

Env seçenekleri:
  SADECE_PUBLIC=1  -> yalnızca herkese açık (public) videoları işle (varsayılan:
                      hepsi; zamanlanmış/özel videolar da eklenir, public olunca
                      listede görünür).
"""
import os
from googleapiclient.discovery import build
import youtube_yukle as YT

# Oynatma listesi adları (otomasyon.py ile birebir aynı).
LISTE_AD = {
    "market":    "🛒 Market & AVM Tuzakları",
    "finans":    "💳 Banka & Kart Tuzakları",
    "dijital":   "📱 Dijital & Uygulama Tuzakları",
    "psikoloji": "🧠 Psikolojik Satış Oyunları",
    "yeme":      "🍔 Restoran & Yeme-İçme Tuzakları",
    "hizmet":    "🏨 Hizmet & Abonelik Tuzakları",
}
VARSAYILAN = "🎯 Tüm Tuzaklar"   # hiçbir kategoriye net oturmayan videolar

# Türkçe anahtar kelimeler (başlık + açıklamada aranır). Öncelik: en çok eşleşen.
ANAHTAR = {
    "finans": ["banka", "kredi kart", "kredi", "faiz", "taksit", "komisyon",
               "hesap işletim", "aidat", "borç", "pos", "atm", "havale", "eft",
               "döviz", "yatırım", "kripto", "sigorta prim", "ek hesap", "nakit avans",
               "kart aidat", "ödeme", "banka masraf"],
    "market": ["market", "avm", "raf", "kasa", "süpermarket", "indirim etiket",
               "fiyat etiket", "alışveriş", "sepet", "kampanya", "büyük boy",
               "gıda", "ürün yerleş", "son kullanma", "gramaj", "birim fiyat",
               "zincir market", "reyon", "bakkal", "ambalaj"],
    "yeme": ["restoran", "menü", "yemek", "kafe", "içecek", "porsiyon", "garson",
             "açık büfe", "büfe", "fast food", "kola", "tatlı", "bahşiş",
             "sınırsız", "paket servis", "lokanta", "mönü", "kahve", "sipariş"],
    "hizmet": ["otel", "abonelik", "üyelik", "spor salon", "gym", "sigorta",
               "kargo", "tatil", "rezervasyon", "sözleşme", "iptal", "fatura",
               "tarife", "operatör", "hizmet bedel", "üye ol", "paket tarife",
               "internet paket", "gsm", "hat", "ulaşım"],
    "dijital": ["uygulama", " app", "dijital", "online", "internet sitesi",
                "reklam", "oyun", "indir", "bildirim", "veri", "ücretsiz uygulama",
                "otomatik yenile", "site", "çerez", "ücretsiz deneme", "premium",
                "in-app", "mikro ödeme", "steam", "mobil", "ekran"],
    "psikoloji": ["psikoloji", "algı", "99", "kıtlık", "aciliyet", "yanılsama",
                  "renk", "koku", "müzik", "fiyat oyun", "çapa", "indirim yanılsama",
                  "kısıtlı süre", "son x", "beyin", "dürtü", "vitrin", "manken",
                  "ışık", "his", "manipül"],
}


def _kategori(baslik, aciklama=""):
    t = (baslik + "  " + (aciklama or "")).lower()
    skor = {k: 0 for k in ANAHTAR}
    for k, kelimeler in ANAHTAR.items():
        for w in kelimeler:
            if w in t:
                skor[k] += 1
    en = max(skor, key=skor.get)
    return en if skor[en] > 0 else None


def _tum_videolar(yt, sadece_public):
    ch = yt.channels().list(part="contentDetails", mine=True).execute()
    items = ch.get("items", [])
    if not items:
        raise SystemExit("Kanal bulunamadı (kimlik/kanal sorunu).")
    up = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    vids, tok = [], None
    while True:
        r = yt.playlistItems().list(part="snippet,contentDetails", playlistId=up,
                                    maxResults=50, pageToken=tok).execute()
        for it in r.get("items", []):
            sn = it["snippet"]
            vids.append({"id": it["contentDetails"]["videoId"],
                         "baslik": sn.get("title", ""),
                         "aciklama": sn.get("description", "")})
        tok = r.get("nextPageToken")
        if not tok:
            break
    if sadece_public and vids:
        ids = [v["id"] for v in vids]
        acik = set()
        for i in range(0, len(ids), 50):
            r = yt.videos().list(part="status", id=",".join(ids[i:i+50])).execute()
            for it in r.get("items", []):
                if it.get("status", {}).get("privacyStatus") == "public":
                    acik.add(it["id"])
        vids = [v for v in vids if v["id"] in acik]
    return vids


def _liste_video_idleri(yt, pid):
    ids, tok = set(), None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=pid,
                                    maxResults=50, pageToken=tok).execute()
        for it in r.get("items", []):
            ids.add(it["contentDetails"]["videoId"])
        tok = r.get("nextPageToken")
        if not tok:
            break
    return ids


def main():
    sadece_public = os.environ.get("SADECE_PUBLIC", "").strip() in ("1", "true", "evet")
    yt = build("youtube", "v3", credentials=YT._kimlik())
    videolar = _tum_videolar(yt, sadece_public)
    print(f"Kanalda işlenecek {len(videolar)} video bulundu"
          f"{' (yalnızca public)' if sadece_public else ''}.")

    liste_pid, liste_ids = {}, {}

    def hedef(ad):
        if ad not in liste_pid:
            pid = YT._oynatma_listesi_bul_veya_olustur(yt, ad)
            liste_pid[ad] = pid
            liste_ids[ad] = _liste_video_idleri(yt, pid)
            print(f"  · liste hazır: {ad} (mevcut {len(liste_ids[ad])} video)")
        return liste_pid[ad], liste_ids[ad]

    eklendi = atlandi = 0
    dagilim = {}
    for v in videolar:
        kat = _kategori(v["baslik"], v["aciklama"])
        ad = LISTE_AD.get(kat, VARSAYILAN)
        pid, ids = hedef(ad)
        if v["id"] in ids:
            atlandi += 1
            continue
        try:
            yt.playlistItems().insert(part="snippet", body={"snippet": {
                "playlistId": pid,
                "resourceId": {"kind": "youtube#video", "videoId": v["id"]}}}).execute()
            ids.add(v["id"])
            eklendi += 1
            dagilim[ad] = dagilim.get(ad, 0) + 1
            print(f"  + [{ad}] {v['baslik'][:60]}")
        except Exception as e:
            print(f"  ! eklenemedi ({v['id']}): {str(e)[:120]}")

    print(f"\nTAMAM ✓  {eklendi} video eklendi, {atlandi} zaten listedeydi.")
    for ad, c in sorted(dagilim.items()):
        print(f"  {ad}: +{c}")


if __name__ == "__main__":
    main()
