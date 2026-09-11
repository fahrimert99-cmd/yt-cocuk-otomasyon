#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TREND & SENARYO BESLEME — "Sandcastles" benzeri, ücretsiz, kendi pipeline'ımız.

Akış:
  1) YouTube'da popüler Türkçe tüketici-tuzağı içeriklerini bulur (izlenmeye göre).
  2) En çok izlenenleri LLM'e analiz ettirir: trend özeti + viral HOOK kalıpları +
     havuzumuzda OLMAYAN yeni video fikirleri (başlık + kanca).
  3) Her fikir için TAM senaryo üretir (kanalın tuzak şeması: 6 sahne + CTA/teaser).
  4) Dedup + hafif kalite kontrol -> senaryolar.json'a EKLER.
  5) trend_rapor.md özeti yazar.

Env:
  YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN   (YouTube arama)
  GEMINI_API_KEY ve/veya ANTHROPIC_API_KEY|CLAUDE_API_KEY (analiz + üretim)
  SAYI      : eklenecek yeni senaryo sayısı (varsayılan 4, azami 10)
  GUN       : kaç günlük pencere (varsayılan 90)
"""
import os, re, json, datetime
from googleapiclient.discovery import build
import youtube_yukle as YT
import ai_script as A
import nvidia_araclar as NA   # NVIDIA NIM kalite araçları (hepsi non-fatal)

# ARAMALAR 5 İÇERİK KOLUNA göre çeşitlendirildi (döngüyü kırmak için — kanal
# eskiden çoğunlukla 'market/banka genel tuzağı' üretiyordu). Her kol farklı bir
# viral niş: 1) shrinkflation/gramaj  2) dark pattern/arayüz oyunu  3) retail
# psikoloji  4) finansal gotcha  5) test/ifşa.
ARAMALAR = [
    # 1) SHRINKFLATION / gramaj küçültme (2026'da en viral kol; TR'de az işlendi)
    "gramaj küçültme market", "shrinkflation türkiye", "paket küçüldü fiyat aynı",
    # 2) DARK PATTERN / karanlık arayüz oyunları
    "sahte indirim etiketi", "abonelik iptal edilmiyor tuzak", "sahte son ürün uyarısı",
    # 3) RETAIL PSİKOLOJİSİ
    "market raf düzeni psikoloji", "market bizi nasıl kandırıyor",
    # 4) FİNANSAL GOTCHA
    "kredi kartı gizli ücret", "alışveriş kredisi tuzağı", "puan iade tuzağı",
    # 5) TEST / İFŞA
    "pahalı ürün gerçekten daha iyi mi", "market marka farkı test",
    # 6) RESALE / DEAL / DEĞER (Amerikan format -> TR: ikinci el, flip, koleksiyon)
    "ikinci el fiyat şişirme", "sıfır ayarında ikinci el tuzağı", "koleksiyon değeri balon",
]

# AMERİKAN (İngilizce) ARAMALAR = PRİMER TREND KAYNAĞI. Strateji: ABD'de kanıtlanmış
# tüketici/deal/resale formatlarını bul -> Türk tüketicisine uyarla (fikir arbitrajı;
# risk önceden test edilmiş, TR'de arz az). YABANCI=0 ile kapatılır (her sorgu 100 birim).
ARAMALAR_YABANCI = [
    # 1) SHRINKFLATION (küresel olarak en viral; 2026 yasal davalar gündemde)
    "shrinkflation examples 2026", "shrinkflation before after", "double labeling packaging",
    # 2) DARK PATTERNS
    "dark patterns subscription trap", "click to cancel scam", "fake urgency countdown online",
    # 3) RETAIL PSİKOLOJİSİ
    "supermarket psychology tricks", "decoy pricing effect",
    # 4) FİNANSAL GOTCHA
    "buy now pay later trap", "hidden bank fees exposed", "loyalty points devaluation",
    # 5) TEST / İFŞA
    "name brand vs generic test", "is expensive product worth it",
    # 6) RESALE / DEAL / DEĞER (Amerikan viral format: ikinci el/flip/koleksiyon)
    "reseller markup exposed", "thrift store flipping profit", "retail markup how much",
    "collector items scam value", "dropshipping markup exposed", "is it worth the hype",
]

# Alakasız (oyun/vlog vb.) sonuçları elemek için: başlıkta bunlardan biri geçmeli.
# TR + EN anahtarlar (yabancı niş videolar da filtreden geçebilsin).
ALAKA = ["tuzak", "tüketici", "kandır", "aldat", "dolandır", "gizli ücret", "ücret",
         "indirim", "fiyat", "market", "banka", "kart", "faiz", "komisyon", "abonelik",
         "zam", "kâr", "kar ", "satış", "psikoloji", "hile", "kandırıyor", "menü",
         "kargo", "fatura", "hak", "para tuza", "kredi",
         # yeni TR kollar:
         "gramaj", "küçül", "shrinkflation", "sahte", "karanlık", "puan", "test",
         "greedflation", "aldatıcı paket", "birim fiyat",
         # EN:
         "trap", "scam", "hidden fee", "hidden cost", "dark pattern", "shrinkflation",
         "drip pricing", "trick", "rip off", "rip-off", "consumer", "subscription",
         "fee", "pricing", "psychology", "sneaky", "loyalty", "gotcha", "fine print",
         "generic", "brand vs", "worth it", "before after", "downsizing", "packaging",
         # resale/deal/değer kolu:
         "reseller", "resale", "flip", "flipping", "thrift", "markup", "collector",
         "ikinci el", "koleksiyon", "şişir", "dropshipping"]


def _norm(s):
    return (s or "").translate(str.maketrans("İIŞĞÜÖÇ", "iışğüöç")).lower().strip()


# KONU-TEKRARI FİLTRESİ (embedding'e bağlı DEĞİL): iki başlık, jenerik kelimeler
# atıldıktan sonra >=2 anlamlı kök paylaşıyorsa AYNI KONU sayılır. Türkçe eklerden
# etkilenmemek için her kelimenin ilk 4 harfi 'kök' kabul edilir (FAİZSİZ/FAİZİNDEKİ
# -> FAİZ; TAKSİT/TAKSİTSİZ -> TAKS; KARGO -> KARG). TÜM havuza karşı çalışır
# (benzer_var_mi'nin son-60 penceresi eski konuları kaçırıyordu).
_KONU_STOP = {
    "NEDEN", "NASIL", "TUZAĞI", "TUZAK", "GİZLİ", "GERÇEK", "GERÇEKTE", "BÖYLE",
    "SENİ", "KADAR", "DAHA", "İLE", "BİR", "NEDİR", "VAR", "YOK", "İLAVE", "EDİLEN",
    "AYLIK", "GÜNDE", "GERÇEKTEN", "KİM", "HANGİ", "NELER", "ÖNÜNDE", "İÇİN",
    "OLAN", "OLUR", "GİDER", "MALİYET",
}


def _kokler(baslik):
    import re
    t = re.sub(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü ]", " ", (baslik or "").upper())
    return {w[:4] for w in t.split() if len(w) >= 4 and w not in _KONU_STOP}


def _konu_cakismasi(baslik, tum_basliklar):
    """baslik, havuzdaki bir başlıkla >=2 anlamlı kök paylaşıyorsa O başlığı döner
    (aynı konu); yoksa None."""
    k = _kokler(baslik)
    if len(k) < 2:
        return None
    for e in (tum_basliklar or []):
        if e and len(k & _kokler(e)) >= 2:
            return e
    return None


def _populer_videolar(yt, gun=90, k_basina=15):
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=gun)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # (video_id -> yabanci mi) ; yabanci geçişte True işaretlenir.
    bulunan = {}
    # 1) TÜRKÇE geçiş (TR bölge/dil)
    for q in ARAMALAR:
        try:
            r = yt.search().list(part="snippet", q=q, type="video", order="viewCount",
                                 maxResults=k_basina, publishedAfter=since,
                                 regionCode="TR", relevanceLanguage="tr").execute()
        except Exception as e:
            print(f"  ! arama hata ({q}): {str(e)[:90]}")
            continue
        for it in r.get("items", []):
            bulunan.setdefault(it["id"]["videoId"], False)
    # 2) YABANCI geçiş (US bölge / EN dil) — niş içerik. YABANCI=0 ile kapatılır.
    if (os.environ.get("YABANCI", "1") or "1").strip() != "0":
        for q in ARAMALAR_YABANCI:
            try:
                r = yt.search().list(part="snippet", q=q, type="video", order="viewCount",
                                     maxResults=k_basina, publishedAfter=since,
                                     regionCode="US", relevanceLanguage="en").execute()
            except Exception as e:
                print(f"  ! yabanci arama hata ({q}): {str(e)[:90]}")
                continue
            for it in r.get("items", []):
                bulunan[it["id"]["videoId"]] = True   # yabanci işaretle
        print(f"      (yabancı niş arama açık: {len(ARAMALAR_YABANCI)} sorgu)")
    ids = list(bulunan)
    veriler = []
    for i in range(0, len(ids), 50):
        try:
            r = yt.videos().list(part="statistics,snippet", id=",".join(ids[i:i+50])).execute()
        except Exception as e:
            print(f"  ! istatistik hata: {str(e)[:90]}")
            continue
        for it in r.get("items", []):
            st = it.get("statistics", {})
            veriler.append({"id": it["id"], "baslik": it["snippet"].get("title", ""),
                            "izlenme": int(st.get("viewCount", 0) or 0),
                            "kanal": it["snippet"].get("channelTitle", ""),
                            "yabanci": bool(bulunan.get(it["id"], False))})
    veriler.sort(key=lambda x: x["izlenme"], reverse=True)
    # ALAKA filtresi: başlığı tüketici-tuzağı kelimesi içerenleri tut (oyun/vlog ele).
    alakali = [v for v in veriler if any(a in _norm(v["baslik"]) for a in ALAKA)]
    return alakali if len(alakali) >= 5 else veriler


def _gemini_call(prompt, key, model):
    """Gemini generateContent — HATA GÖVDESİNİ okur (400'ün gerçek sebebini görmek
    için: 'API key not valid' vb.)."""
    import urllib.request, urllib.error
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
           f":generateContent?key={key}")
    gen = {"temperature": 0.85, "maxOutputTokens": 8192,
           "responseMimeType": "application/json"}
    if model.startswith("gemini-2.5"):
        # 2.5 varsayılan 'thinking' çıktı token bütçesini yiyip JSON'u kesebiliyor.
        gen["thinkingConfig"] = {"thinkingBudget": 0}
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as he:
        raise RuntimeError(f"{he.code}: {he.read().decode()[:160]}")
    cand = (d.get("candidates") or [{}])[0]
    return "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))


def _llm(prompt):
    """NVIDIA NIM (öncelik) -> Gemini -> Claude -> Pollinations, ham metin döner.
    Tüm yollar hata-korumalı; hepsi başarısızsa nedenleri toplayıp net hata verir.
    NVIDIA (build.nvidia.com) ücretsiz ~260 model sunar; Gemini free kotası dolsa
    da çalışır. HER İKİ Gemini anahtarı da denenir. 429'da bir kez tekrar dener."""
    import time as _t
    _clean = lambda s: re.sub(r"\s", "", s or "")
    hatalar = []
    # 0) NVIDIA NIM — en güvenilir ücretsiz sağlayıcı (kota dolmadan çalışır).
    #    Sırayla: palmyra-creative -> nemotron-super-120b -> nemotron-70b.
    nkey = A._nvidia_key()
    if nkey:
        for mdl in A._nvidia_modeller():
            for deneme in range(2):
                try:
                    return A._nvidia(prompt, nkey, model=mdl)
                except Exception as e:
                    msg = str(e)
                    hatalar.append(f"nvidia/{mdl.split('/')[-1][:16]}#{deneme+1}: {msg[:70]}")
                    if "429" in msg and deneme == 0:
                        _t.sleep(15)
                    else:
                        break
    # Aday Gemini anahtarları: önce GEMINI_KEY (vision'da kanıtlı), sonra GEMINI_API_KEY.
    gkeys, gorulen = [], set()
    for k in (os.environ.get("GEMINI_KEY"), os.environ.get("GEMINI_API_KEY")):
        ck = _clean(k)
        if ck and ck not in gorulen:
            gorulen.add(ck)
            gkeys.append(ck)
    ckey = _clean(A._claude_key())
    for gi, gkey in enumerate(gkeys):
        for mdl in ("gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"):
            for deneme in range(2):
                try:
                    return _gemini_call(prompt, gkey, mdl)
                except Exception as e:
                    msg = str(e)
                    hatalar.append(f"gemini{gi}/{mdl}: {msg[:80]}")
                    if "429" in msg and deneme == 0:
                        _t.sleep(20)
                    else:
                        break
    if ckey:
        try:
            return A._claude(prompt, ckey)
        except Exception as e:
            hatalar.append(f"claude: {str(e)[:80]}")
    try:
        return A._poll_post(prompt)
    except Exception as e:
        hatalar.append(f"poll: {str(e)[:80]}")
    raise RuntimeError("LLM üretilemedi | " + " || ".join(hatalar))


def _llm_json(prompt, tries=3):
    """LLM'den JSON alır. YALNIZCA JSON kesik/bozuk gelirse tekrar dener; LLM
    sağlayıcısı çökerse (404/429/kota) HEMEN durur (tekrar denemek kotayı boşa
    yakar). Böylece kota hatasında 3x israf olmaz."""
    son = ""
    for k in range(tries):
        ham = _llm(prompt)                 # sağlayıcı hatası -> yukarı fırlar (retry yok)
        try:
            return json.loads(A._temizle(ham))
        except Exception as e:
            son = f"{type(e).__name__}: {str(e)[:90]}"   # sadece JSON parse -> tekrar
    raise RuntimeError(f"JSON çözülemedi ({tries} deneme): {son}")


def _performans_ipuclari():
    """GERİ BESLEME: analiz_rapor.json'dan KAZANAN ve ZAYIF başlık kalıplarını
    çıkarır -> yeni fikirler kanıtlanmış yöne kayar. MARKA GÜVENLİĞİ: açık
    gizem/keşif başlıkları elenir (kanal 'tuzak' kimliğinde kalır; miras gizem
    videolarının yüksek retention'ı yanlış yöne çekmesin). Rapor yoksa ([],[]).
    - kazanan: retention'ı yüksek (>=%60) TUZAK videoları (video_28g) ya da en
      çok izlenen tuzak başlıkları (top10) -> 'bu kalıptan üret'.
    - zayif: son 7 günde günlük izlenmesi en düşük tuzak videoları -> 'bundan kaçın'.
    """
    try:
        with open("analiz_rapor.json", encoding="utf-8") as f:
            r = json.load(f)
    except Exception:
        return [], []
    # Açık gizem/keşif işaretleri (marka dışı) -> ele
    GIZEM = ("OKYANUS", "BERMUDA", "MARIANA", "HAYALET", "ÜÇGEN", "GEMİ", "DİBİNDE",
             "ATLANTİS", "PİRAMİT", "UZAY", "NAZCA", "MUMYA", "LOCH", "ANTİK",
             "SFENKS", "STONEHENGE", "PASKALYA", "KARA DELİK", "EVREN")
    def tuzak_mi(b):
        B = (b or "").upper()
        return b and not any(k in B for k in GIZEM)
    a = r.get("analytics") or {}
    vd = [v for v in (a.get("video_28g") or []) if tuzak_mi(v.get("baslik"))]
    # retention'ı yüksek (loop/%100+ hariç, gerçek tutma) tuzak videoları
    kazanan = [v["baslik"] for v in sorted(vd, key=lambda x: -(x.get("retention_yuzde") or 0))
               if 60 <= (v.get("retention_yuzde") or 0) <= 100][:6]
    if not kazanan:                       # retention yoksa en çok izlenen tuzağa düş
        top = [v for v in (r.get("top10") or []) if tuzak_mi(v.get("baslik"))]
        kazanan = [v["baslik"] for v in top[:6]]
    zayif = [v["baslik"] for v in
             sorted((r.get("son7gun") or []), key=lambda x: (x.get("izlenme_gunluk") or 0))
             if tuzak_mi(v.get("baslik"))][:5]
    return kazanan, zayif


def _fikir_uret(populer, mevcut_basliklar, sayi):
    _yerli = [v for v in populer if not v.get("yabanci")]
    _yabanci = [v for v in populer if v.get("yabanci")]
    # PRİMER KAYNAK = AMERİKAN trendler (daha geniş liste). TR yerelleştirme referansı.
    yabanci_ozet = "\n".join(f"- {v['izlenme']:>10,} | {v['baslik'][:80]} ({v.get('kanal','')[:24]})"
                             for v in _yabanci[:20]) or "(bu koşuda ABD sonucu gelmedi)"
    ozet = "\n".join(f"- {v['izlenme']:>9,} izlenme | {v['baslik'][:80]}"
                     for v in _yerli[:10])
    mevcut = "\n".join(f"- {b}" for b in mevcut_basliklar)
    # GERİ BESLEME: kendi kanalımızın gerçek performansından öğren.
    _kazanan, _zayif = _performans_ipuclari()
    _perf = ""
    if _kazanan:
        _perf += ("\n\nKENDİ KANALIMIZDA EN İYİ TUTAN videolarımız (yüksek izlenme/"
                  "retention — BU KALIBA/TARZA benzer, SOMUT günlük tuzaklar üret):\n"
                  + "\n".join(f"- {b}" for b in _kazanan))
    if _zayif:
        _perf += ("\n\nEN ZAYIF performans gösterenler (bu tarz/soyut açılardan KAÇIN):\n"
                  + "\n".join(f"- {b}" for b in _zayif))
    prompt = f"""Sen "TUZAK AVCISI" adlı Türk YouTube Shorts kanalının içerik stratejistisin.
Kanal TEK KONU: tüketici tuzakları (market, banka/kart, restoran, dijital/uygulama,
hizmet/abonelik, psikolojik satış oyunları). Amaç: izleyiciyi uyarmak + merak.

*** PRİMER TREND KAYNAĞI — AMERİKAN/ULUSLARARASI videolar ***
Strateji: ABD'de KANITLANMIŞ (yüksek izlenmeli) tüketici/deal/resale formatlarını
al, TÜRK tüketicisine UYARLA (fikir arbitrajı — risk test edilmiş, TR'de arz az).
Aşağıdakiler ABD'de en çok izlenen ilgili videolar (izlenme | başlık | kanal):
{yabanci_ozet}

İkincil — Türkiye'de bu konularda popüler videolar (YERELLEŞTİRME referansı; neyin
zaten TR'de yapıldığını gör, kopyalama, ABD trendini TR'ye taşırken buradan dil/örnek al):
{ozet}

BİZİM HAVUZDA ZATEN OLAN başlıklar (BUNLARI TEKRARLAMA, farklı açı bul):
{mevcut}
{_perf}

GÖREV:
1) ABD listesindeki TREND'i ve neden tuttuklarını (viral HOOK kalıpları) kısaca
   analiz et. Sonra bu trendlerin Türkiye'ye NASIL uyarlanacağını düşün.
2) Kanalımız için {sayi} adet YENİ, ÖZGÜN video fikri öner (havuzda olmayan). Her
   fikir bir ABD trendinden ESİNLENİP Türk hayatına UYARLANMIŞ olsun (doğrudan çeviri
   DEĞİL — Türk marketleri/bankaları/uygulamaları/ikinci el pazarları ile yerel örnek).

   KANAL DÖNGÜYE GİRDİ: eskiden hep 'market/banka genel tuzağı' ürettik. BUNU KIR.
   Fikirleri ŞU 6 İÇERİK KOLUNA DAĞIT (mümkünse her koldan en az bir tane, aynı
   koldan 2'den fazla verme):
     A) SHRINKFLATION / gramaj küçültme (aynı fiyat, küçülen paket — 2026'nın en
        viral konusu; TR'de az işlendi. Ör: çikolata 100g→90g, cips havası).
     B) DARK PATTERN / karanlık arayüz (sahte geri sayım, 'son 2 ürün' yalanı,
        iptal edilemeyen abonelik, varsayılan işaretli ek ürün).
     C) RETAIL PSİKOLOJİSİ (raf düzeni, çapa fiyat, decoy/tuzak seçenek).
     D) FİNANSAL GOTCHA (alışveriş kredisi/BNPL, gizli faiz, puan devalüasyonu).
     E) TEST / İFŞA ('pahalı olan gerçekten daha mı iyi', sahte yorum, markup).
     F) RESALE / DEAL / DEĞER (Amerikan viral format -> TR: ikinci el fiyat şişirme,
        sıfır ayarında satma tuzağı, koleksiyon/hype ürün değer balonu, dropshipping
        markup'ı, 'bu gerçekten değer mi'). Nick Giovanni / resale-kralı tarzı ama
        kanalın TUZAK diliyle: izleyiciyi ALDANMAKTAN koru.

   KURALLAR:
   - SOMUT ve SPESİFİK ol: 'marketler kandırır' DEĞİL -> 'X paket 3 ayda 500g'dan
     450g'a düştü, fiyat aynı' gibi net, kanıtlanabilir açı.
   - Yabancı NİŞ konuları TÜRK hayatına UYARLA (doğrudan çeviri değil; Türk
     marketleri/bankaları/uygulamaları ile yerel örnek). Güncel küresel olayları
     (gramaj davaları, 'double labeling', click-to-cancel) yerelleştir.
   - Havuzda çok işlenmiş kolları (klasik market/banka geneli) TEKRARLAMA.

SADECE geçerli JSON döndür, başka hiçbir şey yazma:
{{"trend":"1-2 cümle trend özeti","hook_kaliplari":["kalıp1","kalıp2","kalıp3"],
"fikirler":[{{"baslik":"BÜYÜK HARF MERAK BAŞLIĞI + emoji","kanca":"2-3 KELİME"}}]}}
Türkçe harfleri (ç,ğ,ı,İ,ö,ş,ü) eksiksiz kullan."""
    return _llm_json(prompt)


SENARYO_PROMPT = """Sen "TUZAK AVCISI" Türk YouTube Shorts kanalı için senaryo yazarısın.
Konu bir TÜKETİCİ TUZAĞI. BAŞLIK: {baslik}
KANCA (kapak/açılış merak cümlesi): {kanca}

Bir Türkçe seslendirme metni yaz (~100-120 kelime). KURALLAR:
- İLK CÜMLE vurucu olsun; kurulumla başlama, doğrudan tuzağı/şaşırtıcı gerçeği ver.
- Tüketiciyi bu tuzağa karşı NASIL koruyacağını da anlat (pratik uyarı).
- Uydurma istatistik/sayı verme.
- SONDA şu iki şey olsun: (a) kısa bir ABONE çağrısı, (b) bir sonraki videoya
  merak bırakan TEASER cümlesi.
- Emoji/başlık/madde YOK; düz paragraf.
- Anlatımı 6 SAHNEYE böl; her sahne için İNGİLİZCE sinematik görsel tarifi yaz.
TÜRKÇE YAZIM: ç,ğ,ı,İ,ö,ş,ü harflerini EKSİKSİZ kullan; ASCII'ye sadeleştirme.
(Yalnızca 'gorsel' İngilizce olacak.)

SADECE geçerli JSON döndür, başka hiçbir şey yazma:
{{"baslik":"{baslik}","aciklama":"2-3 cümle","etiketler":["tuzak","tüketici","e3","e4","e5"],
"kanca":"{kanca}","script":"...","sahneler":[{{"metin":"...","gorsel":"cinematic english"}}],
"tema":"tuzak"}}"""


def _senaryo_uret(baslik, kanca):
    d = _llm_json(SENARYO_PROMPT.format(baslik=baslik, kanca=kanca))
    # şema güvenceleri
    d.setdefault("baslik", baslik)
    d.setdefault("kanca", kanca)
    # ÜÇ KELİME KURALI: kanca en fazla 3 kelime olmalı (kapak/açılış kısa-vurucu).
    _kk = (d.get("kanca") or kanca or "").split()
    if len(_kk) > 3:
        d["kanca"] = " ".join(_kk[:3])
    d["tema"] = "tuzak"
    # ETİKETLER GARANTİSİ: model null/eksik döndürse de her zaman geçerli, dolu
    # bir liste olsun (SEO tag'leri boş kalmasın).
    et = d.get("etiketler")
    if not isinstance(et, list):
        et = []
    et = [str(x).strip() for x in et if str(x).strip() and str(x).strip().lower()
          not in ("e3", "e4", "e5")]              # şablon yer tutucularını ele
    for z in ("tuzak", "tüketici", "tüketici hakları", "tasarruf", "para"):
        if z not in et:
            et.append(z)
    d["etiketler"] = et[:12]
    return d


def _gecerli(d):
    if not isinstance(d, dict):
        return False
    if not (d.get("script") and d.get("baslik") and d.get("sahneler")):
        return False
    if len((d["script"] or "").split()) < 55:      # çok kısa -> ele
        return False
    if not isinstance(d["sahneler"], list) or len(d["sahneler"]) < 4:
        return False
    for s in d["sahneler"]:
        if not (s.get("metin") and s.get("gorsel")):
            return False
    return True


def main():
    sayi = max(1, min(10, int(os.environ.get("SAYI", "4") or "4")))
    gun = max(7, int(os.environ.get("GUN", "90") or "90"))

    yt = build("youtube", "v3", credentials=YT._kimlik())
    print(f"[1/4] YouTube'da popüler tüketici-tuzağı videoları aranıyor (son {gun} gün) ...")
    populer = _populer_videolar(yt, gun=gun)
    print(f"      {len(populer)} video bulundu. En çok izlenen 5:")
    for v in populer[:5]:
        print(f"        {v['izlenme']:>10,} | {v['baslik'][:70]}")
    if not populer:
        raise SystemExit("Popüler video bulunamadı (arama boş döndü).")

    with open("senaryolar.json", encoding="utf-8") as f:
        havuz = json.load(f)
    mevcut_norm = {_norm(s.get("baslik", "")) for s in havuz}
    tum_basliklar = [s.get("baslik", "") for s in havuz]           # TÜM havuz (konu dedup)
    mevcut_basliklar = tum_basliklar[-45:]                         # son 45 (prompt kısa kalsın)

    print(f"[2/4] LLM ile trend analizi + {sayi} yeni fikir üretiliyor ...")
    analiz = _fikir_uret(populer, mevcut_basliklar, sayi)
    trend = analiz.get("trend", "")
    hooklar = analiz.get("hook_kaliplari", []) or []
    fikirler = analiz.get("fikirler", []) or []
    print(f"      Trend: {trend[:120]}")
    print(f"      Fikir sayısı: {len(fikirler)}")

    print("[3/4] Yeni fikirler için tam senaryo üretiliyor ...")
    import time
    eklenen = []
    for _i, fk in enumerate(fikirler):
        bas = (fk.get("baslik") or "").strip()
        knc = (fk.get("kanca") or "").strip()
        if not bas:
            continue
        if _norm(bas) in mevcut_norm:
            print(f"      · atlandı (zaten var): {bas[:60]}")
            continue
        if _i:                     # Gemini ücretsiz kota: çağrılar arası bekle
            time.sleep(6)
        try:
            sen = _senaryo_uret(bas, knc)
        except Exception as e:
            print(f"      ! senaryo üretilemedi ({bas[:40]}): {str(e)[:90]}")
            continue
        if not _gecerli(sen):
            print(f"      ! kalite/şema geçmedi, atlandı: {bas[:50]}")
            continue
        # NVIDIA ÖZ-İYİLEŞTİRME: senaryoyu güçlü bir modele eleştirtip güçlendir.
        # Sadece dönen sürüm geçerliyse kullan; değilse orijinalde kal (non-fatal).
        gelismis = NA.senaryo_iyilestir(sen)
        if gelismis and _gecerli(gelismis) and _norm(gelismis.get("baslik", "")) not in (
                mevcut_norm - {_norm(bas)}):
            sen = gelismis
            print(f"      ✎ senaryo güçlendirildi (NVIDIA/{NA.KRITIK_MODEL})")
        # REASONING ile kanca/açılış (ilk 2 sn) güçlendirme — havuz üretiminde,
        # non-fatal. Başlık/konu korunur; yalnızca kanca + açılış cümlesi keskinleşir.
        _onceki_kanca = sen.get("kanca", "")
        sen = NA.kanca_guclendir(sen)
        if sen.get("kanca", "") != _onceki_kanca:
            print(f"      ⚡ kanca/açılış güçlendirildi (NVIDIA/{NA.REASONING_MODEL})")
        if _norm(sen.get("baslik", "")) in mevcut_norm:
            continue
        # KONU TEKRARI (kök-kelime, TÜM havuz, embedding'siz): farklı kelime ama
        # aynı konu -> ele. Eski havuzdaki konuları da yakalar.
        _cak = _konu_cakismasi(sen.get("baslik", ""), tum_basliklar)
        if _cak:
            print(f"      · atlandı (konu tekrarı ~ '{_cak[:40]}'): {sen.get('baslik','')[:45]}")
            continue
        # ANLAMSAL TEKRAR: farklı kelime ama aynı konu -> ele (embedding, TÜM havuz, non-fatal).
        if NA.benzer_var_mi(sen.get("baslik", ""), tum_basliklar):
            print(f"      · atlandı (anlamsal tekrar): {sen.get('baslik','')[:55]}")
            continue
        havuz.append(sen)
        mevcut_norm.add(_norm(sen.get("baslik", "")))
        tum_basliklar.append(sen.get("baslik", ""))
        mevcut_basliklar.append(sen.get("baslik", ""))
        eklenen.append(sen)
        print(f"      + eklendi: {sen['baslik'][:60]}")

    if not eklenen:
        print("Yeni senaryo eklenmedi (hepsi mevcut ya da üretim başarısız).")
        return

    with open("senaryolar.json", "w", encoding="utf-8") as f:
        json.dump(havuz, f, ensure_ascii=False, indent=2)

    print("[4/4] Rapor yazılıyor: trend_rapor.md")
    tarih = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    with open("trend_rapor.md", "w", encoding="utf-8") as f:
        f.write(f"# Trend Raporu — {tarih}\n\n")
        f.write(f"**Trend özeti:** {trend}\n\n")
        f.write("**Viral hook kalıpları:**\n")
        for h in hooklar:
            f.write(f"- {h}\n")
        f.write(f"\n**En çok izlenen 10 rakip video:**\n")
        for v in populer[:10]:
            f.write(f"- {v['izlenme']:,} izlenme — {v['baslik']}  _(kanal: {v['kanal']})_\n")
        f.write(f"\n**Havuza eklenen {len(eklenen)} yeni senaryo:**\n")
        for s in eklenen:
            f.write(f"- {s['baslik']}  — kanca: _{s.get('kanca','')}_\n")

    print(f"\nTAMAM ✓  {len(eklenen)} yeni senaryo senaryolar.json'a eklendi "
          f"(toplam {len(havuz)}). Rapor: trend_rapor.md")


if __name__ == "__main__":
    main()
