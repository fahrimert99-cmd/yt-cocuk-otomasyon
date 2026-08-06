# uzun_script.py — 6 dk (~900 kelime) UZUN video metni uretir.
import os, json, time
from ai_script import _gemini, _poll_post, _poll_get, _temizle

UZUN_PROMPT = """BASLIK: {baslik}
Bu baslik icin, YouTube'da YATAY bir "detayli anlatim" videosu icin Turkce seslendirme metni yaz.
Ton: uyarici/ifsa edici ama sakin ve guven veren; izleyiciyi bir tuzak/aldatma konusunda egiten.
Uzunluk: yaklasik 900 kelime (~6 dakika seslendirme). Bilgiler DOGRU olsun, uydurma istatistik verme.
Yapi: TEK guclu kanca ile basla (ilk cumle). Sonra bolumler halinde derinlestir:
(1) mekanizma/para nereden geliyor, (2) psikolojik numaralar, (3) kimler risk altinda ozellikle cocuklar,
(4) MUTLAKA sonda somut "nasil korunursun" adimlari. Sonda dusundurucu guclu kapanis + kisa abone cagrisi.
Emoji YOK, madde YOK, baslik satiri YOK; duz akici paragraflar (tek metin).
Anlatimi 18-22 sahneye bol; her sahne icin KISA INGILIZCE sinematik stok gorsel tarifi yaz.
Sahne 'metin'leri script'in sirayla parcalari olsun.
SADECE su JSON'u dondur:
{{"baslik":"...","aciklama":"2-3 cumle","etiketler":["e1","e2","e3","e4","e5","e6","e7","e8"],"kanca":"kisa vurucu acilis","script":"...","sahneler":[{{"metin":"...","gorsel":"cinematic english"}}]}}"""


def _gemini_key():
    k = os.environ.get("GEMINI_KEY", "").strip()
    if k: return k          # ayri/ozel Gemini anahtari (onerilir)
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
    key = _gemini_key()
    yollar = []
    if key:
        yollar.append(("gemini", lambda: _gemini(prompt, key)))
    yollar += [("poll_post", lambda: _poll_post(prompt)),
               ("poll_get",  lambda: _poll_get(prompt))]
    hatalar = []
    for ad, fn in yollar:
        for _ in range(3 if ad == "gemini" else 1):
            try:
                data = json.loads(_temizle(fn()))
                if data.get("script") and data.get("sahneler"):
                    return data
                hatalar.append(f"{ad}: bos")
            except Exception as e:
                hatalar.append(f"{ad}: {str(e)[:140]}")
            time.sleep(30 if ad=='gemini' else 2)
    raise RuntimeError("Uzun script uretilemedi: " + " | ".join(hatalar[:6]))


if __name__ == "__main__":
    import sys
    print(json.dumps(uret(sys.argv[1] if len(sys.argv) > 1 else "OYUNLARDAKİ SATIN ALMA TUZAĞI"),
                     ensure_ascii=False, indent=2))
