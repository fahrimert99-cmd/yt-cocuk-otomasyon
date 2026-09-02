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
               "zincir market", "reyon", "bakkal", "ambalaj", "organik",
               "paket küçül", "market araba", "büyük paket"],
    "yeme": ["restoran", "menü", "yemek", "kafe", "içecek", "porsiyon", "garson",
             "açık büfe", "büfe", "fast food", "tatlı", "bahşiş",
             "sınırsız", "paket servis", "lokanta", "mönü", "kahve", "sipariş"],
    "hizmet": ["otel", "abonelik", "üyelik", "spor salon", "gym", "sigorta",
               "kargo", "tatil", "rezervasyon", "sözleşme", "iptal", "fatura",
               "tarife", "operatör", "hizmet bedel", "paket tarife",
               "internet paket", "gsm hat", "kuaför", "otopark", "düğün salon",
               "uçak", "bilet", "telefon fatura"],
    # NOT: kısa/açgözlü kelimeler ('indir'->'indirim', 'mobil'->'mobilya',
    # 'hat'->'hata', 'oyun'->'fiyat oyunu') çıkarıldı -> yanlış eşleşme önlenir.
    "dijital": ["uygulama", " app ", "dijital", "online", "internet sitesi",
                "reklam", "bildirim", "ücretsiz uygulama", "otomatik yenile",
                "çerez", "ücretsiz deneme", "premium abone", "in-app",
                "mikro ödeme", "steam", "abonelik uygulama", "e-ticaret",
                "sanal", "aldatıcı buton", "buton", "site tasarım"],
    "psikoloji": ["psikoloji", "algı", "kıtlık", "aciliyet", "yanılsama",
                  "koku", "mağaza müzik", "fiyat oyun", "çapa fiyat",
                  "indirim yanılsama", "kısıtlı süre", "beyin", "dürtü",
                  "vitrin", "manken", "mağaza ışığ", "manipül", "üstü çizili",
                  "99 kuruş", "99 tl", "kumar", "sadakat kart"],
}


# Türkçe-doğru küçültme: "İ".lower() Python'da üstü-noktalı bileşik karakter
# üretip alt-dize eşleşmesini bozar. İ->i, I->ı önce yapılır, sonra lower().
_TR = str.maketrans("İIŞĞÜÖÇ", "iışğüöç")


def _norm(s):
    return (s or "").translate(_TR).lower()


def _kategori(baslik, aciklama=""):
    t = _norm(baslik + "  " + (aciklama or ""))
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


def _liste_ogeleri(yt, pid):
    """Listedeki {videoId: playlistItemId} eşlemesini döner (öge silmek için
    itemId lazım). Yeni liste henüz sorgulanamıyorsa (404) boş döner."""
    from googleapiclient.errors import HttpError
    ogeler, tok = {}, None
    while True:
        try:
            r = yt.playlistItems().list(part="contentDetails", playlistId=pid,
                                        maxResults=50, pageToken=tok).execute()
        except HttpError as e:
            if getattr(e, "resp", None) is not None and e.resp.status == 404:
                return ogeler
            raise
        for it in r.get("items", []):
            ogeler[it["contentDetails"]["videoId"]] = it["id"]
        tok = r.get("nextPageToken")
        if not tok:
            break
    return ogeler


def main():
    sadece_public = os.environ.get("SADECE_PUBLIC", "").strip() in ("1", "true", "evet")
    # TEMIZLE=0 -> yalnızca ekle (taşıma yok). Varsayılan: kendi kendini düzelt
    # (video yanlış yönetilen listedeyse oradan çıkar, doğru listeye taşı).
    temizle = os.environ.get("TEMIZLE", "1").strip() not in ("0", "false", "hayir", "hayır")

    yt = build("youtube", "v3", credentials=YT._kimlik())
    videolar = _tum_videolar(yt, sadece_public)
    print(f"Kanalda işlenecek {len(videolar)} video bulundu"
          f"{' (yalnızca public)' if sadece_public else ''}. TEMIZLE={'açık' if temizle else 'kapalı'}")

    # YÖNETİLEN listeler (yalnızca bunlara dokunulur; kullanıcının diğer listeleri
    # ASLA değiştirilmez). Hepsi önden hazırlanır: id + {videoId: itemId} haritası.
    YONETILEN = list(LISTE_AD.values()) + [VARSAYILAN]
    pid_ad, oge_ad = {}, {}
    for ad in YONETILEN:
        pid = YT._oynatma_listesi_bul_veya_olustur(yt, ad)
        pid_ad[ad] = pid
        oge_ad[ad] = _liste_ogeleri(yt, pid)
        print(f"  · liste hazır: {ad} (mevcut {len(oge_ad[ad])} video)")

    eklendi = atlandi = tasindi = 0
    dagilim = {}
    for v in videolar:
        kat = _kategori(v["baslik"])          # YALNIZCA başlık (açıklama footer'ı gürültü)
        dogru = LISTE_AD.get(kat, VARSAYILAN)

        # 1) Doğru listede değilse ekle
        if v["id"] in oge_ad[dogru]:
            atlandi += 1
        else:
            try:
                r = yt.playlistItems().insert(part="snippet", body={"snippet": {
                    "playlistId": pid_ad[dogru],
                    "resourceId": {"kind": "youtube#video", "videoId": v["id"]}}}).execute()
                oge_ad[dogru][v["id"]] = r["id"]
                eklendi += 1
                dagilim[dogru] = dagilim.get(dogru, 0) + 1
                print(f"  + [{dogru}] {v['baslik'][:58]}")
            except Exception as e:
                print(f"  ! eklenemedi ({v['id']}): {str(e)[:110]}")

        # 2) TEMIZLE: aynı videoyu DİĞER yönetilen listelerden çıkar (yanlış yer)
        if temizle:
            for ad in YONETILEN:
                if ad == dogru:
                    continue
                itemid = oge_ad[ad].get(v["id"])
                if itemid:
                    try:
                        yt.playlistItems().delete(id=itemid).execute()
                        del oge_ad[ad][v["id"]]
                        tasindi += 1
                        print(f"  - [{ad}] çıkarıldı: {v['baslik'][:50]}")
                    except Exception as e:
                        print(f"  ! çıkarılamadı ({v['id']} / {ad}): {str(e)[:90]}")

    print(f"\nTAMAM ✓  {eklendi} eklendi, {atlandi} zaten doğru listedeydi, "
          f"{tasindi} yanlış listeden çıkarıldı.")
    print("Güncel dağılım (yönetilen listeler):")
    for ad in YONETILEN:
        print(f"  {ad}: {len(oge_ad[ad])} video")


if __name__ == "__main__":
    main()
