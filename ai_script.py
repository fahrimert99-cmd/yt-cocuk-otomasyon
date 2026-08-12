#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Senaryo Üretici (GitHub-native, sağlam).
GEMINI_API_KEY varsa Gemini (en kaliteli/güvenilir); yoksa anahtarsız Pollinations
(POST /openai -> GET fallback). Her yol için tekrar denemeli + esnek JSON ayrıştırma.
"""
import os, re, json, time, urllib.parse, urllib.request

PROMPT = """Sen Veritasium tarzında bilim içeriği üreten bir YouTube yazarısın.
BAŞLIK: {baslik}
Bu başlık için genel izleyiciye uygun, akıcı, bilimsel olarak DOĞRU bir Türkçe seslendirme metni yaz. ~110 kelime, ilk cümle güçlü bir kanca olsun, sonda düşündürücü bir kapanış. Emoji/başlık/madde YOK, düz paragraf. Anlatımı 5 sahneye böl; her sahne için İNGİLİZCE sinematik bir görsel tarifi yaz.
ÇOK ÖNEMLİ — TÜRKÇE YAZIM: 'script', 'baslik', 'aciklama' ve sahne 'metin' alanlarını KUSURSUZ Türkçe imlâ ile yaz. Türkçe'ye özgü harfleri (ç, ğ, ı, İ, ö, ş, ü ve büyükleri) HER ZAMAN ve EKSİKSİZ kullan; ASLA ASCII karşılıklarına (c, g, i, o, s, u) sadeleştirme. Örnek: "guclu" DEĞİL "güçlü", "bilim icerigi" DEĞİL "bilim içeriği". (Yalnızca 'gorsel' alanı İngilizce olacak.)
CEVABINI SADECE geçerli JSON olarak ver. Başka hiçbir şey yazma, açıklama/kod bloğu ekleme:
{{"baslik":"...","aciklama":"2-3 cümle","etiketler":["e1","e2","e3","e4","e5"],"script":"...","sahneler":[{{"metin":"...","gorsel":"cinematic english description"}}]}}"""


def _temizle(t):
    t = (t or "").strip()
    t = re.sub(r"^```(json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    i, j = t.find("{"), t.rfind("}")
    if i >= 0 and j > i:
        t = t[i:j+1]
    return t


def _gemini(prompt, key, model="gemini-2.0-flash"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 4096,
                                 "responseMimeType": "application/json"}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read().decode())
    return d["candidates"][0]["content"]["parts"][0]["text"]


# --- Anthropic Claude (en kaliteli Türkçe metin) -------------------------
# Model ANTHROPIC_MODEL ile degistirilebilir (maliyet icin ornegin
# "claude-sonnet-5" veya "claude-haiku-4-5"). Varsayilan: en yetenekli Opus.
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "").strip() or "claude-opus-5"


def _claude_key():
    return (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY") or "").strip()


def _claude(prompt, key, model=None, max_tokens=8192):
    """Anthropic Messages API (ham HTTP, ek bagimlilik yok) ile metin uretir."""
    model = model or ANTHROPIC_MODEL
    url = "https://api.anthropic.com/v1/messages"
    body = {"model": model, "max_tokens": max_tokens,
            "thinking": {"type": "disabled"},  # duz JSON istiyoruz; dusunme kapali
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    # content bir blok listesidir; sadece metin bloklarini birlestir
    return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")


def _poll_post(prompt):
    url = "https://text.pollinations.ai/openai"
    body = {"model": "openai", "temperature": 0.9,
            "messages": [{"role": "system", "content": "Yalnizca gecerli JSON dondur."},
                         {"role": "user", "content": prompt}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "yt"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    return d["choices"][0]["message"]["content"]


def _poll_get(prompt):
    q = urllib.parse.quote(prompt)
    url = f"https://text.pollinations.ai/{q}?model=openai"
    req = urllib.request.Request(url, headers={"User-Agent": "yt"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "ignore")


def uret(baslik):
    prompt = PROMPT.format(baslik=baslik)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    ckey = _claude_key()
    yollar = []
    if ckey:
        yollar.append(("claude", lambda: _claude(prompt, ckey)))
    if key:
        yollar.append(("gemini", lambda: _gemini(prompt, key)))
    yollar += [("poll_post", lambda: _poll_post(prompt)),
               ("poll_get", lambda: _poll_get(prompt))]

    hatalar = []
    for ad, yol in yollar:
        denemeler = 4 if ad in ("gemini", "claude") else 1
        for k in range(denemeler):
            try:
                ham = yol()
                data = json.loads(_temizle(ham))
                if data.get("script"):
                    return data
                hatalar.append(f"{ad}: script bos")
                break
            except Exception as e:
                msg = str(e)
                hatalar.append(f"{ad}#{k+1}: {type(e).__name__}: {msg[:120]}")
                if "429" in msg and k < denemeler - 1:
                    time.sleep(30)      # dakika-limiti sifirlanmasini bekle
                else:
                    break
    import time as _t
    raise SystemExit("AI senaryo uretilemedi @" + _t.strftime("%H:%M:%S") +
                     " | " + " || ".join(hatalar))


if __name__ == "__main__":
    import sys
    print(json.dumps(uret(sys.argv[1] if len(sys.argv) > 1 else "Gökyüzü neden mavidir?"),
                     ensure_ascii=False, indent=2))
