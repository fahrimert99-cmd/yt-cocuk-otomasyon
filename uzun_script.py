# uzun_script.py — 3 dk (~450 kelime) UZUN video metni uretir.
import os, json, time, urllib.request
from ai_script import _gemini, _poll_post, _poll_get, _temizle, _claude, _claude_key

# Guncel UCRETSIZ katman modelleri; anahtarin erisebildigi ilki secilir.
GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-2.5-flash"]

def _gemini_uzun(prompt, key, model):
    # ai_script._gemini ile ayni, ama maxOutputTokens buyuk (uzun JSON kesilmesin).
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 8192,
                                 "responseMimeType": "application/json"}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    return d["candidates"][0]["content"]["parts"][0]["text"]

UZUN_PROMPT = """BAŞLIK: {baslik}
Bu başlık için, YouTube'da YATAY bir "gizem / gerçek olay" belgesel-anlatım videosu için Türkçe seslendirme metni yaz.
Ton: merak uyandıran, hafif gerilimli ama güven veren bir anlatıcı; izleyiciyi bir gizemin/olayın peşine takan, sürükleyici belgesel dili.
Uzunluk: yaklaşık 450 kelime (~3 dakika seslendirme). Bilgiler DOĞRU olsun, uydurma istatistik/tarih verme; kesin bilinmeyen yerde "kesin olarak bilinmiyor" de ve teori olduğunu belirt.
Yapı — RETENTION için kritik: SOĞUK AÇILIŞ ile başla (ilk cümle çarpıcı bir soru ya da merak boşluğu; izleyici ilk 3 saniyede DURSUN). Sonra bölümler halinde derinleştir:
(1) gizemi/olayı sahnele: nerede, ne zaman, ne oldu, (2) bilinen gerçekler ve kanıtlar, (3) teoriler ve olasılıklar, (4) en çarpıcı detay / dönüm noktası ("ama sonra işler tuhaflaşıyor" gibi açık döngülerle merak taze tut), (5) düşündüren güçlü kapanış + "bir sonraki gizem için abone ol" tarzı kısa merak-odaklı abone çağrısı.
Her 60-90 saniyede yeni bir soru/merak aç ki izleyici sonuna kadar kalsın.
Emoji YOK, madde YOK, başlık satırı YOK; düz akıcı paragraflar (tek metin).
Anlatımı 11-14 sahneye böl. Sahne 'metin'leri script'in SIRAYLA parçaları olsun (o an anlatılan şey).
Her sahne için 'gorsel': o cümlede anlatılan şeyi gösteren 2-4 KELİMELİK, SOMUT, ARANABİLİR İngilizce stok video anahtar kelimesi.
Somut nesne/mekân/eylem kullan; örnek: "supermarket shopping cart", "credit card payment", "shrinking product package", "child playing phone game".
YASAK: soyut/kavramsal ifadeler ("conceptual", "abstract", "cinematic shot", "shadowy figure", "coins dissolving" gibi). Başa "a"/"the" KOYMA, somut ismi başa yaz.
ÇOK ÖNEMLİ — TÜRKÇE YAZIM: 'script', 'baslik', 'aciklama', 'kanca' ve sahne 'metin' alanlarını KUSURSUZ Türkçe imlâ ile yaz.
Türkçe'ye özgü harfleri (ç, ğ, ı, İ, ö, ş, ü ve büyükleri Ç, Ğ, İ, Ö, Ş, Ü) HER ZAMAN ve EKSİKSİZ kullan.
Bu harfleri ASLA ASCII karşılıklarına (c, g, i, o, s, u) sadeleştirme; aksan/diakritik atlama. Örnek: "guclu" DEĞİL "güçlü", "cocuk" DEĞİL "çocuk", "sirri" DEĞİL "sırrı", "yasiyor" DEĞİL "yaşıyor".
(NOT: yalnızca 'gorsel' alanı İngilizce olacak; onun dışındaki tüm metin doğru Türkçe karakterlerle yazılır.)
SADECE şu JSON'u döndür:
{{"baslik":"...","aciklama":"2-3 cümle","etiketler":["e1","e2","e3","e4","e5","e6","e7","e8"],"kanca":"3-6 kelimelik ŞOK EDİCİ, kaydırmayı durduran, merak/öfke uyandıran Türkçe açılış - izleyici ilk 2 saniyede DURSUN; ZORUNLU, asla boş bırakma","script":"...","sahneler":[{{"metin":"...","gorsel":"cinematic english"}}]}}"""


_TR_OZEL = set("çğıöşüÇĞİÖŞÜ")  # Türkçe'ye özgü, ASCII karşılığı olmayan harfler

def _turkce_yeterli(metin):
    """Metnin gercekten Turkce karakter icerdigini dogrular.
    Diakritiksiz (ASCII'ye sadelestirilmis) uretimi yakalar: gercek bir
    ~450 kelimelik Turkce metin bu harfleri yogun icerir; sadelestirilmis
    metinde neredeyse hic bulunmaz. Kisa metinlerde kontrol atlanir."""
    s = metin or ""
    if len(s) < 200:
        return True  # kanca gibi cok kisa alanlar tek basina yaniltici olabilir
    ozel = sum(1 for c in s if c in _TR_OZEL)
    # Gercek Turkce anlatim ~%8-10 ozel harf icerir; tamamen ASCII ~%0.
    # Esik %3: hem tam hem KISMEN diakritiksiz (kelimelerin bir kismi "guclu",
    # "cocuk" gibi bozuk) metinleri reddeder -> TTS'te yabanci aksan olmaz.
    return ozel >= len(s) * 0.03


def _gemini_key():
    # once UZUN hatta OZEL anahtar (ayri kota); yoksa ortak GEMINI_KEY.
    for _ad in ("GEMINI_KEY_UZUN", "GEMINI_KEY"):
        k = os.environ.get(_ad, "").strip()
        if k: return k
    raw = os.environ.get("GEMINI_API_KEY", "").strip()
    if raw.startswith("{"):
        try:
            j = json.loads(raw)
            return (j.get("gemini") or j.get("google") or "").strip()
        except Exception:
            return ""
    return raw


def uret(baslik):
    prompt = UZUN_PROMPT.format(baslik=baslik)
    hatalar = []
    # 1) Anthropic Claude (en kaliteli/en tutarli Turkce) — birincil saglayici
    ckey = _claude_key()
    if ckey:
        for deneme in range(2):
            try:
                data = json.loads(_temizle(_claude(prompt, ckey)))
                if data.get("script") and data.get("sahneler"):
                    if _turkce_yeterli(data["script"]):
                        print("    Senaryo: Anthropic Claude")
                        return data
                    hatalar.append(f"claude#{deneme+1}: turkce karakter eksik")
                    if deneme == 0:
                        continue
                    break
                hatalar.append("claude: bos yanit")
                break
            except Exception as e:
                msg = str(e)
                hatalar.append(f"claude#{deneme+1}: {msg[:90]}")
                if "429" in msg and deneme == 0:
                    time.sleep(15); continue
                break  # 401/404/diger -> Gemini'ye dus
    # 2) Gemini (yedek)
    key = _gemini_key()
    if key:
        for model in GEMINI_MODELS:
            for deneme in range(2):
                try:
                    data = json.loads(_temizle(_gemini_uzun(prompt, key, model)))
                    if data.get("script") and data.get("sahneler"):
                        if _turkce_yeterli(data["script"]):
                            print(f"    Senaryo: Gemini ({model})")
                            return data
                        # Diakritiksiz (ASCII) uretim -> ses ve altyazi Turkce
                        # karakter kullanmaz; kabul etme, tekrar dene.
                        hatalar.append(f"{model}#{deneme+1}: turkce karakter eksik")
                        if deneme == 0:
                            continue  # ayni modelle bir kez daha dene
                        break         # sonraki modele gec
                    hatalar.append(f"{model}: bos yanit")
                    break
                except Exception as e:
                    msg = str(e)
                    hatalar.append(f"{model}#{deneme+1}: {msg[:90]}")
                    if "429" in msg and deneme == 0:
                        time.sleep(20); continue
                    break  # 404/diger -> bu modeli birak, sonrakine gec
    for ad, fn in (("poll_post", lambda: _poll_post(prompt)),
                   ("poll_get", lambda: _poll_get(prompt))):
        try:
            data = json.loads(_temizle(fn()))
            if data.get("script") and data.get("sahneler"):
                if _turkce_yeterli(data["script"]):
                    print(f"    Senaryo: {ad} (yedek)")
                    return data
                hatalar.append(f"{ad}: turkce karakter eksik")
            else:
                hatalar.append(f"{ad}: bos")
        except Exception as e:
            hatalar.append(f"{ad}: {str(e)[:90]}")
    raise RuntimeError("Uzun script uretilemedi: " + " | ".join(hatalar[:8]))


if __name__ == "__main__":
    import sys
    print(json.dumps(uret(sys.argv[1] if len(sys.argv) > 1 else "BERMUDA ŞEYTAN ÜÇGENİNDE GERÇEKTE NE OLUYOR?"),
                     ensure_ascii=False, indent=2))
