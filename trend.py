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

ARAMALAR = [
    "tüketici tuzağı", "market fiyat tuzağı", "gizli ücret tüketici",
    "market bizi nasıl kandırıyor", "indirim yalanı", "kargo ücreti tuzağı",
    "abonelik iptal tuzağı", "bankalar gizli ücret", "kredi kartı tuzağı",
    "market psikolojisi satış", "restoran menü tuzağı", "tüketici hakları aldatıcı",
]

# Alakasız (oyun/vlog vb.) sonuçları elemek için: başlıkta bunlardan biri geçmeli.
ALAKA = ["tuzak", "tüketici", "kandır", "aldat", "dolandır", "gizli ücret", "ücret",
         "indirim", "fiyat", "market", "banka", "kart", "faiz", "komisyon", "abonelik",
         "zam", "kâr", "kar ", "satış", "psikoloji", "hile", "kandırıyor", "menü",
         "kargo", "fatura", "hak", "para tuza", "kredi"]


def _norm(s):
    return (s or "").translate(str.maketrans("İIŞĞÜÖÇ", "iışğüöç")).lower().strip()


def _populer_videolar(yt, gun=90, k_basina=15):
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=gun)).strftime("%Y-%m-%dT%H:%M:%SZ")
    bulunan = {}
    for q in ARAMALAR:
        try:
            r = yt.search().list(part="snippet", q=q, type="video", order="viewCount",
                                 maxResults=k_basina, publishedAfter=since,
                                 regionCode="TR", relevanceLanguage="tr").execute()
        except Exception as e:
            print(f"  ! arama hata ({q}): {str(e)[:90]}")
            continue
        for it in r.get("items", []):
            bulunan[it["id"]["videoId"]] = True
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
                            "kanal": it["snippet"].get("channelTitle", "")})
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
    """Gemini (öncelik) -> Claude -> Pollinations, ham metin döner. Tüm yollar
    hata-korumalı; hepsi başarısızsa nedenleri toplayıp net hata verir.
    HER İKİ Gemini anahtarı da denenir (GEMINI_KEY video vision'da çalışıyor;
    GEMINI_API_KEY geçersizse diğerine geçilir). 429'da bir kez tekrar dener."""
    import time as _t
    _clean = lambda s: re.sub(r"\s", "", s or "")
    # Aday Gemini anahtarları: önce GEMINI_KEY (vision'da kanıtlı), sonra GEMINI_API_KEY.
    gkeys, gorulen = [], set()
    for k in (os.environ.get("GEMINI_KEY"), os.environ.get("GEMINI_API_KEY")):
        ck = _clean(k)
        if ck and ck not in gorulen:
            gorulen.add(ck)
            gkeys.append(ck)
    ckey = _clean(A._claude_key())
    hatalar = []
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


def _fikir_uret(populer, mevcut_basliklar, sayi):
    ozet = "\n".join(f"- {v['izlenme']:>9,} izlenme | {v['baslik'][:80]}"
                     for v in populer[:20])
    mevcut = "\n".join(f"- {b}" for b in mevcut_basliklar)
    prompt = f"""Sen "TUZAK AVCISI" adlı Türk YouTube Shorts kanalının içerik stratejistisin.
Kanal TEK KONU: tüketici tuzakları (market, banka/kart, restoran, dijital/uygulama,
hizmet/abonelik, psikolojik satış oyunları). Amaç: izleyiciyi uyarmak + merak.

AŞAĞIDA YouTube'da SON DÖNEMDE EN ÇOK İZLENEN benzer Türkçe videolar (izlenme + başlık):
{ozet}

BİZİM HAVUZDA ZATEN OLAN başlıklar (BUNLARI TEKRARLAMA, farklı açı bul):
{mevcut}

GÖREV:
1) Yukarıdaki popüler videolardan çıkan TREND'i ve neden tuttuklarını (viral HOOK
   kalıpları) kısaca analiz et.
2) Kanalımız için {sayi} adet YENİ, ÖZGÜN video fikri öner (havuzda olmayan). Her
   fikir tüketici tuzağı temalı, merak uyandıran olsun.

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
    d["tema"] = "tuzak"
    if isinstance(d.get("etiketler"), list):
        for z in ("tuzak", "tüketici"):
            if z not in d["etiketler"]:
                d["etiketler"].append(z)
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
    mevcut_basliklar = [s.get("baslik", "") for s in havuz][-45:]  # son 45 (prompt kısa kalsın)

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
        if _norm(sen.get("baslik", "")) in mevcut_norm:
            continue
        havuz.append(sen)
        mevcut_norm.add(_norm(sen.get("baslik", "")))
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
