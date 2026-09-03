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
    "tüketici tuzağı", "market tuzağı", "gizli ücret", "tüketici kandırıyor",
    "para tuzağı", "indirim tuzağı", "market oyunları", "abonelik tuzağı",
    "bankalar nasıl kazanıyor", "alışveriş tuzağı",
]


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
    return veriler


def _llm(prompt):
    """Gemini (öncelik) -> Claude -> Pollinations, ham metin döner. Tüm yollar
    hata-korumalı; hepsi başarısızsa nedenleri toplayıp net hata verir.
    Gemini anahtarı GEMINI_API_KEY veya GEMINI_KEY'den okunur (repo ikisini de
    kullanıyor); 429'da bir kez tekrar dener."""
    import time as _t
    gkey = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_KEY") or "").strip()
    ckey = A._claude_key()
    hatalar = []
    if gkey:
        for mdl in ("gemini-2.0-flash", "gemini-1.5-flash"):
            for deneme in range(2):
                try:
                    return A._gemini(prompt, gkey, model=mdl)
                except Exception as e:
                    msg = str(e)
                    hatalar.append(f"gemini/{mdl}#{deneme+1}: {msg[:70]}")
                    if "429" in msg and deneme == 0:
                        _t.sleep(20)
                    else:
                        break
    if ckey:
        try:
            return A._claude(prompt, ckey)
        except Exception as e:
            hatalar.append(f"claude: {str(e)[:70]}")
    try:
        return A._poll_post(prompt)
    except Exception as e:
        hatalar.append(f"poll: {str(e)[:70]}")
    raise RuntimeError("LLM üretilemedi | " + " || ".join(hatalar))


def _fikir_uret(populer, mevcut_basliklar, sayi):
    ozet = "\n".join(f"- {v['izlenme']:>9,} izlenme | {v['baslik'][:80]}"
                     for v in populer[:30])
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
    ham = _llm(prompt)
    return json.loads(A._temizle(ham))


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
    ham = _llm(SENARYO_PROMPT.format(baslik=baslik, kanca=kanca))
    d = json.loads(A._temizle(ham))
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
    mevcut_basliklar = [s.get("baslik", "") for s in havuz][-60:]  # son 60 (prompt kısa kalsın)

    print(f"[2/4] LLM ile trend analizi + {sayi} yeni fikir üretiliyor ...")
    analiz = _fikir_uret(populer, mevcut_basliklar, sayi)
    trend = analiz.get("trend", "")
    hooklar = analiz.get("hook_kaliplari", []) or []
    fikirler = analiz.get("fikirler", []) or []
    print(f"      Trend: {trend[:120]}")
    print(f"      Fikir sayısı: {len(fikirler)}")

    print("[3/4] Yeni fikirler için tam senaryo üretiliyor ...")
    eklenen = []
    for fk in fikirler:
        bas = (fk.get("baslik") or "").strip()
        knc = (fk.get("kanca") or "").strip()
        if not bas:
            continue
        if _norm(bas) in mevcut_norm:
            print(f"      · atlandı (zaten var): {bas[:60]}")
            continue
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
