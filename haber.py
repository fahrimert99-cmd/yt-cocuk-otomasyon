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
    "https://www.ntv.com.tr/ekonomi.rss",
    "https://www.hurriyet.com.tr/rss/ekonomi",
    "https://www.cnnturk.com/feed/rss/ekonomi/news",
    "https://www.sozcu.com.tr/feeds-rss-category-ekonomi",
    "https://www.milliyet.com.tr/rss/rssnew/ekonomirss.xml",
    "https://www.haberturk.com/rss/ekonomi.xml",
    "https://www.sabah.com.tr/rss/ekonomi.xml",
    "https://www.dunya.com/rss?dunya",
    "https://www.trthaber.com/xml_mobile.php?tur=xml_genel&kategori=ekonomi",
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
              "cnnturk.com": "CNN Türk", "sozcu.com.tr": "Sözcü",
              "milliyet.com.tr": "Milliyet", "haberturk.com": "Habertürk",
              "sabah.com.tr": "Sabah", "dunya.com": "Dünya"}
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


_KISALTMA = {
    "TCMB": "Merkez Bankası", "ÖTV": "Özel Tüketim Vergisi",
    "KDV": "Katma Değer Vergisi", "TÜİK": "Türkiye İstatistik Kurumu",
    "SGK": "Sosyal Güvenlik Kurumu", "BDDK": "Bankacılık Düzenleme ve Denetleme Kurumu",
    "TÜFE": "tüketici enflasyonu", "ÜFE": "üretici enflasyonu",
    "EYT": "emeklilikte yaşa takılanlar", "AVM": "alışveriş merkezi",
}


def _kisaltma_ac(text):
    """Seslendirmede kötü okunan kısaltmaları aç (TCMB -> Merkez Bankası)."""
    if not text:
        return text
    for k, v in _KISALTMA.items():
        text = re.sub(r"\b" + re.escape(k) + r"\b", v, text)
    return text


def _akici_script(item):
    """Haberi AKICI, konuşma diline çevirir (LLM). SADECE verilen bilgiyi
    kullanır (uydurma yok), kaynağı belirtir. Başarısızsa None (şablona düşülür).
    Kesik/robotik seslendirmenin sebebi ham RSS metniydi; bu, akıcı cümleler üretir."""
    ozet = item["ozet"] or item["baslik"]
    if len(ozet) > 400:
        ozet = ozet[:397].rsplit(" ", 1)[0] + "..."
    prompt = (
        "Sen 'TUZAK AVCISI' adlı tüketici farkındalığı YouTube kanalı için metin "
        "yazarısın. Aşağıdaki GÜNCEL HABERİ bir GİRİŞ/kanca olarak kullan; sonra o "
        "konuda tüketiciyi bilinçlendiren NET ve EKSİKSİZ bir Short metni yaz "
        "(~40 saniye, yaklaşık 80-110 kelime, DİKEY Short, tek parça seslendirme).\n"
        "KURALLAR:\n"
        "- Haberin KENDİSİ hakkında yeni RAKAM/TARİH/oran UYDURMA. Kesin veri yoksa "
        "  rakam verme; 'habere göre ... gündemde' gibi söyle.\n"
        "- AMA konuyu (ör. kredi kartı faizi, zam, dolandırıcılık, abonelik) GENEL ve "
        "  DOĞRU bilgiyle AÇIKLA — izleyici somut bir şey ÖĞRENSİN. CÜMLELERİ ASLA "
        "  YARIM BIRAKMA, metni tamamla.\n"
        "- KISALTMA KULLANMA, açık yaz: 'TCMB' yerine 'Merkez Bankası', 'ÖTV' yerine "
        "  'Özel Tüketim Vergisi', 'KDV' yerine 'Katma Değer Vergisi' gibi.\n"
        "- Akış: (1) haber-kancası, (2) bu konu tüketiciyi nasıl etkiler (net açıklama), "
        "  (3) nasıl korunmalı (somut ipucu), (4) 'Kaynak: " + item["kaynak"] + "' de, "
        "  (5) kısa 'abone ol' çağrısı.\n"
        "- Doğal, akıcı, konuşma dili. Emoji/başlık/parantez kullanma.\n"
        "- 'gorseller': KONUYLA İLGİLİ 6 kısa İNGİLİZCE stok video arama terimi ver "
        "  (her sahne için biri; son terim abone/bildirim temalı olsun). "
        "  Örn kredi kartı için: [\"credit card debt\",\"bank interest rate\","
        "\"person paying bills worried\",\"financial calculator\","
        "\"cutting credit card\",\"youtube subscribe bell\"].\n"
        'SADECE şu JSON: {"baslik":"...","script":"...","gorseller":["...","...","...","...","...","..."]}\n\n'
        "HABER BAŞLIK: " + item["baslik"] + "\nHABER ÖZET: " + ozet
    )
    try:
        import ai_script, json as _json
        gkey = os.environ.get("GEMINI_API_KEY", "").strip()
        ckey = ai_script._claude_key()
        ham = None
        if gkey:
            try: ham = ai_script._gemini(prompt, gkey)
            except Exception: ham = None
        if not ham and ckey:
            ham = ai_script._claude(prompt, ckey)
        if not ham:
            return None
        veri = _json.loads(ai_script._temizle(ham))
        b = _kisaltma_ac((veri.get("baslik") or item["baslik"]).strip())
        s = _kisaltma_ac(re.sub(r"\s+", " ", (veri.get("script") or "")).strip())
        # Çok kısa (eksik) script'i kabul etme -> yeniden/şablona düşsün
        if len(s.split()) < 40:
            print("  [akici script cok kisa, atlandi]:", len(s.split()), "kelime")
            return None
        # Yarım bitmişse son eksik cümleyi at (tam cümlede bitsin)
        if s[-1:] not in ".!?":
            parcalar = re.split(r"(?<=[.!?])\s+", s)
            if len(parcalar) > 1:
                s = " ".join(parcalar[:-1]).strip()
        gorseller = veri.get("gorseller")
        if isinstance(gorseller, list):
            gorseller = [str(x).strip() for x in gorseller if str(x).strip()][:6]
            if len(gorseller) < 6:
                gorseller = None
        else:
            gorseller = None
        return b, s, gorseller
    except Exception as e:
        print("  [akici script atlandi]:", str(e)[:100])
        return None


def _bol(text, n=6):
    """Metni n sahneye SIRALI böler (sahne süresi/gorsel için)."""
    import math
    cumleler = [c.strip() for c in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if c.strip()]
    if len(cumleler) < n:
        kel = (text or "").split()
        boyut = max(1, math.ceil(len(kel) / n))
        cumleler = [" ".join(kel[i:i + boyut]) for i in range(0, len(kel), boyut)] or [text]
    k = max(1, math.ceil(len(cumleler) / n))
    gruplar = [" ".join(cumleler[i:i + k]) for i in range(0, len(cumleler), k)]
    while len(gruplar) < n:
        gruplar.append(gruplar[-1] if gruplar else (text or ""))
    return gruplar[:n]


# Konu anahtar kelimesine göre KONUYLA İLGİLİ görsel sorguları (LLM yoksa).
GORSEL_KONU = [
    (("kredi", "kart", "faiz", "banka", "borç", "taksit"),
     ["credit card debt", "bank interest rate", "person paying bills worried",
      "financial calculator money", "cutting credit card scissors", "youtube subscribe bell"]),
    (("zam", "fiyat", "enflasyon", "akaryak", "motorin", "benzin", "mazot", "fahiş"),
     ["gas station fuel pump", "turkish lira inflation", "supermarket price tags",
      "empty wallet money", "shopping receipt long", "youtube subscribe bell"]),
    (("dolandırıc", "sahte", "hile", "kandır", "aldat", "siber"),
     ["phone scam fraud alert", "hacker cyber security", "fake sms message phone",
      "warning sign red alert", "protecting personal data", "youtube subscribe bell"]),
    (("market", "alışveriş", "etiket", "raf", "stok", "indirim", "kampanya"),
     ["supermarket shopping cart", "price tag shelf store", "checkout cashier",
      "grocery receipt", "reading label magnifier", "youtube subscribe bell"]),
    (("abonelik", "ücret", "sözleşme", "fatura"),
     ["subscription cancel phone", "hidden fees contract", "reading fine print magnifier",
      "money leaving wallet", "calendar reminder phone", "youtube subscribe bell"]),
]
GORSEL_VARSAYILAN = ["news studio breaking", "turkish lira money shopping",
                     "warning sign alert red", "person shopping supermarket",
                     "reading contract magnifier", "youtube subscribe bell"]


def _gorseller_konu(item):
    metin = (item["baslik"] + " " + item["ozet"]).lower()
    for kelimeler, gorseller in GORSEL_KONU:
        if any(k in metin for k in kelimeler):
            return gorseller
    return GORSEL_VARSAYILAN


def senaryo_yap(item):
    kaynak = item["kaynak"]
    ozet = item["ozet"] or item["baslik"]
    if len(ozet) > 240:
        ozet = ozet[:237].rsplit(" ", 1)[0] + "..."
    llm = _akici_script(item)
    llm_gorseller = None
    if llm:
        ham_baslik, script, llm_gorseller = llm
        baslik = _tr_upper(ham_baslik)[:90] + " 📰"
    else:
        # Yedek: LLM yoksa/başarısızsa ham-metin şablonu (kesik olabilir ama üretir)
        korunma = _korunma(item)
        baslik = _tr_upper(item["baslik"])[:90] + " 📰"
        script = (f"Tüketiciyi ilgilendiren son gelişme. Habere göre: {ozet} "
                  f"Peki sen ne yapmalısın? {korunma} Kaynak: {kaynak}. "
                  f"Böyle gelişmeleri kaçırmamak için abone ol, yarın yeni bir tuzak.")
    kanca = re.split(r"(?<=[.!?])\s+", script.strip())[0][:80]
    # Görsel: (1) LLM'in verdiği konu-uyumlu sorgular, yoksa (2) anahtar-kelime
    # eşlemesi, yoksa (3) jenerik. Böylece her haber KONUSUNA göre görsel alır.
    g = llm_gorseller or _gorseller_konu(item)
    parcalar = _bol(script, 6)
    sahneler = [{"metin": parcalar[i], "gorsel": g[i % len(g)]} for i in range(6)]
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
    # Haber gizliliği config'ten (ilk testlerde 'unlisted' -> önce incele,
    # beğenince config.haber_gizlilik'i 'public' yap).
    sen["gizlilik"] = str(cfg.get("haber_gizlilik", "unlisted") or "unlisted").strip()
    os.makedirs(os.path.dirname(CIKTI_P) or ".", exist_ok=True)
    with open(CIKTI_P, "w", encoding="utf-8") as f:
        json.dump(sen, f, ensure_ascii=False, indent=2)
    durum["yapilan_link"] = (durum["yapilan_link"] + [sec["link"]])[-200:]
    _durum_yaz(durum)
    print(f"[3/3] Senaryo yazıldı: {CIKTI_P}")


if __name__ == "__main__":
    main()
