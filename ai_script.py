#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Senaryo Üretici (GitHub-native).
GEMINI_API_KEY tanımlıysa Google Gemini kullanır (daha kaliteli);
yoksa anahtarsız ücretsiz Pollinations AI'ya düşer.
Başlık verilir -> {baslik, aciklama, etiketler, script, sahneler} döner.
"""
import os, re, json, urllib.request

PROMPT = """Sen Veritasium tarzinda, meraki uyandiran bilim ve egitim icerigi ureten bir YouTube yazarisin. Sasirtici, sezgiye aykiri bilim gercekleri anlatirsin.
Asagidaki BASLIK icin genel izleyiciye uygun, akici ve merakli bir Turkce seslendirme metni yaz.
BASLIK: {baslik}
Kurallar: Yaklasik 50 saniyelik dikey video, yaklasik 110 kelime. Ilk cumle guclu bir kanca (sasirtici soru/iddia) olsun; ortada net ve DOGRU bir aciklama; sonda dusundurucu bir kapanis. Bilimsel olarak dogru ol; sade ama etkileyici bir dil kullan. Emoji/baslik/madde YOK, duz paragraf.
Anlatimi 5 sahneye bol; her sahne icin o anki anlatimla uyumlu, sinematik ve bilimsel, INGILIZCE bir gorsel tarifi yaz (gorselde yazi olmasin).
Yaniti SADECE tek satirlik gecerli JSON olarak ver, kod blogu veya aciklama ekleme:
{{"baslik":"basligi kullan","aciklama":"2-3 cumle","etiketler":["e1","e2","e3","e4","e5"],"script":"tam seslendirme metni","sahneler":[{{"metin":"sahnenin turkce cumlesi","gorsel":"cinematic scientific english illustration description"}}]}}"""


def _temizle(t):
    t = t.strip()
    t = re.sub(r"^```(json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    # ilk { ile son } arasini al (fazlalik metni ele)
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


def _pollinations(prompt):
    # anahtarsiz, OpenAI-uyumlu ucretsiz endpoint
    url = "https://text.pollinations.ai/openai"
    body = {"model": "openai", "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    return d["choices"][0]["message"]["content"]


def uret(baslik):
    prompt = PROMPT.format(baslik=baslik)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    ham = None
    if key:
        try:
            ham = _gemini(prompt, key)
        except Exception as e:
            print(f"   [Gemini hata: {e}; Pollinations'a düşülüyor]")
    if ham is None:
        ham = _pollinations(prompt)
    return json.loads(_temizle(ham))


if __name__ == "__main__":
    import sys
    print(json.dumps(uret(sys.argv[1] if len(sys.argv) > 1 else "Gökyüzü neden mavidir?"),
                     ensure_ascii=False, indent=2))
