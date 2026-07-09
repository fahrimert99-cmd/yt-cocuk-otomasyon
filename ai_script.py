#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Senaryo Üretici (GitHub-native, sağlam).
GEMINI_API_KEY varsa Gemini (en kaliteli/güvenilir); yoksa anahtarsız Pollinations
(POST /openai -> GET fallback). Her yol için tekrar denemeli + esnek JSON ayrıştırma.
"""
import os, re, json, time, urllib.parse, urllib.request

PROMPT = """Sen Veritasium tarzinda bilim icerigi ureten bir YouTube yazarisin.
BASLIK: {baslik}
Bu baslik icin genel izleyiciye uygun, akici, bilimsel olarak DOGRU bir Turkce seslendirme metni yaz. ~110 kelime, ilk cumle guclu bir kanca olsun, sonda dusundurucu bir kapanis. Emoji/baslik/madde YOK, duz paragraf. Anlatimi 5 sahneye bol; her sahne icin INGILIZCE sinematik bir gorsel tarifi yaz.
CEVABINI SADECE gecerli JSON olarak ver. Baska hicbir sey yazma, aciklama/kod blogu ekleme:
{{"baslik":"...","aciklama":"2-3 cumle","etiketler":["e1","e2","e3","e4","e5"],"script":"...","sahneler":[{{"metin":"...","gorsel":"cinematic english description"}}]}}"""


def _temizle(t):
    t = (t or "").strip()
    t = re.sub(r"^```(json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    i, j = t.find("{"), t.rfind("}")
    if i >= 0 and j > i:
        t = t[i:j+1]
    return t


def _gemini(prompt, key, model="gemini-2.5-flash"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 2048}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read().decode())
    return d["candidates"][0]["content"]["parts"][0]["text"]


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
    yollar = []
    if key:
        yollar.append(lambda: _gemini(prompt, key))
    yollar += [lambda: _poll_post(prompt), lambda: _poll_get(prompt)]

    son_hata = None
    for yol in yollar:
        for deneme in range(2):
            try:
                ham = yol()
                data = json.loads(_temizle(ham))
                if data.get("script"):
                    return data
            except Exception as e:
                son_hata = e
                time.sleep(2)
    raise SystemExit(f"AI senaryo üretilemedi (tüm yollar başarısız). Son hata: {son_hata}. "
                     f"Öneri: GEMINI_API_KEY ekleyin (aistudio.google.com/apikey).")


if __name__ == "__main__":
    import sys
    print(json.dumps(uret(sys.argv[1] if len(sys.argv) > 1 else "Gökyüzü neden mavidir?"),
                     ensure_ascii=False, indent=2))
