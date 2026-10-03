#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gemini görsel üretimi tanısı (geçici): her anahtarla erişilebilen görsel
modellerini listeler, A101 sahnesiyle tek görsel dener, sonucu raporlar."""
import base64, json, os, urllib.error, urllib.request

OUT = "onizleme/gemini_test"
os.makedirs(OUT, exist_ok=True)
PROMPT = ("Photorealistic cinematic documentary still: long queue of shoppers waiting outside "
          "a Turkish discount supermarket at 9am on a Thursday, store sign reading 'A101', "
          "morning light, wide shot, 35mm film look, no other text, no watermark")
rapor = []

def anahtar(raw):
    raw = (raw or "").strip()
    if raw.startswith("{"):
        try:
            j = json.loads(raw); return (j.get("gemini") or j.get("google") or "").strip()
        except Exception:
            return ""
    return raw

def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode())

for ad in ("GEMINI_API_KEY", "GEMINI_KEY", "GEMINI_KEY_UZUN", "GEMINI_IMAGE_API_KEY"):
    key = anahtar(os.environ.get(ad))
    if not key:
        rapor.append(f"{ad}: boş"); continue
    try:
        modeller, tok = [], ""
        while True:
            d = get(f"https://generativelanguage.googleapis.com/v1beta/models?pageSize=200&key={key}{tok}")
            modeller += d.get("models", [])
            if not d.get("nextPageToken"): break
            tok = "&pageToken=" + d["nextPageToken"]
    except Exception as e:
        rapor.append(f"{ad}: model listesi alınamadı ({str(e)[:120]})"); continue
    gorsel = [m["name"].split("/")[-1] for m in modeller
              if "image" in m["name"] or "imagen" in m["name"]]
    rapor.append(f"{ad}: {len(modeller)} model; görsel modelleri: {', '.join(gorsel) or 'YOK'}")
    for model in gorsel:
        if "imagen" in model:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict?key={key}"
            body = {"instances": [{"prompt": PROMPT}], "parameters": {"sampleCount": 1, "aspectRatio": "16:9"}}
        else:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            body = {"contents": [{"parts": [{"text": "Generate an image: " + PROMPT}]}],
                    "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "16:9"}}}
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=150) as r:
                d = json.loads(r.read().decode())
            b64 = None
            for p in (d.get("predictions") or []):
                b64 = p.get("bytesBase64Encoded") or b64
            for c in d.get("candidates", []):
                for part in (c.get("content") or {}).get("parts", []):
                    inl = part.get("inlineData") or part.get("inline_data")
                    if inl and inl.get("data"): b64 = inl["data"]
            if b64:
                yol = f"{OUT}/{ad}_{model}.jpg"
                open(yol, "wb").write(base64.b64decode(b64))
                rapor.append(f"  ✓ {model}: görsel üretildi ({yol})")
            else:
                rapor.append(f"  ✗ {model}: yanıt var, görsel yok: {json.dumps(d)[:200]}")
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            try: msg = json.loads(msg)["error"]["message"]
            except Exception: pass
            rapor.append(f"  ✗ {model}: HTTP {e.code}: {msg[:260]}")
        except Exception as e:
            rapor.append(f"  ✗ {model}: {type(e).__name__}: {str(e)[:160]}")

metin = "\n".join(rapor)
print(metin)
open(f"{OUT}/rapor.txt", "w", encoding="utf-8").write(metin + "\n")
