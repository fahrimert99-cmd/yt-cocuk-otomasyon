#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GÜNCEL TÜKETİCİ HABERİ -> kanal senaryosu (TUZAK AVCISI).
Türkçe ekonomi/tüketici RSS kaynaklarından haber çeker, tüketici-tuzağı
anahtar kelimeleriyle filtreler, EN TAZE + uygun haberi seçer ve kanal
tarzında bir Short senaryosu (output/haber_senaryo.json) üretir.

GÜVENLİK / DOĞRULUK:
- Haber YENİDEN YORUMLANMAZ (AI hallüsinasyon riski yok): başlık/özet kaynağa
  ATIFLA, temkinli dille ("habere göre") kullanılır ve KAYNAK belirtilir.
- Aynı haber tekrar işlenmesin diye kullanılan linkler haber_durum.json'da tutulur.

Kullanım (workflow): python haber.py  -> output/haber_senaryo.json yazar
Sonra: SENARYO_DOSYA=output/haber_senaryo.json python uret_dispatch.py
"""
import os, json, re, ssl, urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

DURUM_P = "haber_durum.json"
CIKTI_P = "output/haber_senaryo.json"

# Güvenilir Türkçe ekonomi/tüketici RSS kaynakları (config.haber_kaynaklar ile
# değiştirilebilir). Çalışmayan feed atlanır; en az biri çalışırsa yeter.
VARSAYILAN_KAYNAKLAR = [
    "https://www.aa.com.tr/tr/rss/default?cat=ekonomi",
    "https://www.trthaber.com/ekonomi.rss",
    "https://www.ntv.com.tr/ekonomi.rss",
    "https://www.hurriyet.com.tr/rss/ekonomi",
    "https://www.cnnturk.com/feed/rss/ekonomi/news",
]

# Tüketici-tuzağı damarına uygun anahtar kelimeler (başlık+özet taranır).
ANAHTAR = [
    "zam", "fahiş", "dolandırıcı", "dolandırıcılık", "tuzak", "aldatıcı",
    "aldatma", "kandır", "sahte", "geri çağır", "iade", "tüketici", "fiyat",
    "indirim", "kampanya", "abonelik", "gizli ücret", "faiz", "kredi",
    "market", "etiket", "stokçu", "vurgun", "ceza", "şikayet", "hile",
]

# Anahtar kelimeye göre "kendini koru" ipucu (haberi eyleme dönüştürür).
KORUNMA = [
    (("dolandırıcı", "sahte", "kandır", "hile", "aldat"),
     "Şüpheli mesaj ve linklere tıklama, bilgilerini kimseyle paylaşma."),
    (("zam", "fiyat", "fahiş", "etiket", "stokçu"),
     "Fiyatı kasada bir daha kontrol et, farklı marketlerle karşılaştır."),
    (("geri çağır", "iade"),
     "Ürünü kullanmayı bırak, satıcıdan iade/değişim hakkını iste."),
    (("abonelik", "gizli ücret", "faiz", "kredi", "kampanya", "indirim"),
     "Sözleşmedeki küçük yazıları ve otomatik yenilemeyi mutlaka oku."),
]
GENEL_KORUNMA = "Acele karar verme, koşulları oku ve haklarını öğren."


def _cfg():
    try:
        with open("config.json", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def _durum():
    try:
        with open(DURUM_P, encoding="utf-8-sig") as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("yapilan_link", [])
    return d


def _durum_yaz(d):
    with open(DURUM_P, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _temizle(html):
    t = re.sub(r"<[^>]+>", " ", html or "")
    t = re.sub(r"&[a-zA-Z#0-9]+;", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _kaynak_adi(link, feed_url):
    m = re.search(r"https?://(?:www\.)?([^/]+)", link or feed_url or "")
    dom = (m.group(1) if m else "").lower()
    harita = {"aa.com.tr": "Anadolu Ajansı", "trthaber.com": "TRT Haber",
              "ntv.com.tr": "NTV", "hurriyet.com.tr": "Hürriyet",
              "cnnturk.com": "CNN Türk"}
    for k, v in harita.items():
        if k in dom:
            return v
    return dom or "haber kaynağı"


def _tr_upper(s):
    return s.translate(str.maketrans({"i": "İ", "ı": "I", "ş": "Ş", "ğ": "Ğ",
                                      "ü": "Ü", "ö": "Ö", "ç": "Ç"})).upper()


def cek(kaynaklar):
    ctx = ssl.create_default_context()
    for p in ("/root/.ccr/ca-bundle.crt",):
        try:
            ctx.load_verify_locations(p)
        except Exception:
            pass
    items = []
    for u in kaynaklar:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=20, context=ctx).read()
            items += _parse(data, u)
        except Exception as e:
            print(f"  [feed atlandı] {u} -> {str(e)[:80]}")
    return items


def _parse(data, feed_url):
    out = []
    try:
        root = ET.fromstring(data)
    except Exception:
        return out
    for it in root.findall(".//item"):
        baslik = _temizle(it.findtext("title") or "")
        ozet = _temizle(it.findtext("description") or "")
        link = (it.findtext("link") or "").strip()
        tarih = it.findtext("pubDate") or ""
        try:
            ts = parsedate_to_datetime(tarih)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = datetime(1970, 1, 1, tzinfo=timezone.utc)
        if baslik:
            out.append({"baslik": baslik, "ozet": ozet, "link": link,
                        "ts": ts, "kaynak": _kaynak_adi(link, feed_url)})
    return out


def _skor(item):
    metin = (item["baslik"] + " " + item["ozet"]).lower()
    return sum(1 for k in ANAHTAR if k in metin)


def filtrele(items, yapilan_link):
    uygun = []
    gorulen = set(yapilan_link)
    for it in items:
        if not it["link"] or it["link"] in gorulen:
            continue
        if _skor(it) <= 0:
            continue
        uygun.append(it)
    # önce anahtar-skoru yüksek, sonra en taze
    uygun.sort(key=lambda x: (-_skor(x), -x["ts"].timestamp()))
    return uygun


def _korunma(item):
    metin = (item["baslik"] + " " + item["ozet"]).lower()
    for kelimeler, tip in KORUNMA:
        if any(k in metin for k in kelimeler):
            return tip
    return GENEL_KORUNMA


def senaryo_yap(item):
    kaynak = item["kaynak"]
    ozet = item["ozet"] or item["baslik"]
    if len(ozet) > 240:
        ozet = ozet[:237].rsplit(" ", 1)[0] + "..."
    korunma = _korunma(item)
    baslik = _tr_upper(item["baslik"])[:90] + " 📰"

    kanca = "Tüketiciyi ilgilendiren son gelişme!"
    script = (
        f"{kanca} Habere göre: {ozet} "
        f"Peki sen ne yapmalısın? {korunma} "
        f"Kaynak: {kaynak}. "
        f"Böyle tüketici gelişmelerini kaçırmamak için abone ol, yarın yeni bir tuzak."
    )
    g = ["news studio breaking", "turkish lira money shopping",
         "warning sign alert red", "person shopping supermarket",
         "reading contract magnifier", "youtube subscribe bell"]
    metinler = [
        kanca,
        f"Habere göre: {ozet}",
        f"Sen ne yapmalısın? {korunma}",
        f"Kaynak: {kaynak}.",
        "Uyanık tüketici ol, haklarını bil.",
        "Abone ol, yarın yeni bir tüketici tuzağı!",
    ]
    sahneler = [{"metin": metinler[i], "gorsel": g[i]} for i in range(6)]
    return {
        "baslik": baslik,
        "aciklama": f"Habere göre: {ozet} (Kaynak: {kaynak})",
        "etiketler": ["tüketici", "haber", "güncel", "tuzak", "farkındalık"],
        "kanca": kanca,
        "tema": "haber",
        "gizlilik": "public",
        "kaynak": kaynak,
        "link": item["link"],
        "script": script,
        "sahneler": sahneler,
    }


def main():
    cfg = _cfg()
    # Eski senaryo dosyasını temizle: uygun haber yoksa workflow yanlışlıkla
    # bayat senaryoyu üretmesin.
    try:
        if os.path.exists(CIKTI_P):
            os.remove(CIKTI_P)
    except Exception:
        pass
    kaynaklar = cfg.get("haber_kaynaklar") or VARSAYILAN_KAYNAKLAR
    durum = _durum()
    print(f"[1/3] {len(kaynaklar)} kaynaktan haber çekiliyor ...")
    items = cek(kaynaklar)
    print(f"      {len(items)} haber alındı.")
    uygun = filtrele(items, durum["yapilan_link"])
    print(f"[2/3] {len(uygun)} tüketici-uygun haber (filtre sonrası).")
    if not uygun:
        print("      Uygun taze haber yok — bu turda video üretilmeyecek.")
        raise SystemExit(0)
    sec = uygun[0]
    print(f"      Seçilen: {sec['baslik'][:70]}  [{sec['kaynak']}]")
    sen = senaryo_yap(sec)
    os.makedirs(os.path.dirname(CIKTI_P) or ".", exist_ok=True)
    with open(CIKTI_P, "w", encoding="utf-8") as f:
        json.dump(sen, f, ensure_ascii=False, indent=2)
    durum["yapilan_link"] = (durum["yapilan_link"] + [sec["link"]])[-200:]
    _durum_yaz(durum)
    print(f"[3/3] Senaryo yazıldı: {CIKTI_P}")


if __name__ == "__main__":
    main()
