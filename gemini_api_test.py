#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gemini görsel anahtarı için YouTube'suz tek istek tanısı."""
import base64
import json
import os
import urllib.error
import urllib.request

KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()
MODEL = os.environ.get("GEMINI_TEST_MODEL", "gemini-2.5-flash-image").strip()
OUT = os.environ.get("GEMINI_TEST_OUTPUT", "gemini-test.jpg")

if not KEY:
    raise SystemExit("GEMINI_API_KEY secret boş veya aktarılmamış")

url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}"
body = {
    "contents": [{"parts": [{"text": "Generate a simple blue circle on a white background. No text."}]}],
    "generationConfig": {
        "responseModalities": ["IMAGE"],
        "imageConfig": {"aspectRatio": "1:1"},
    },
}
req = urllib.request.Request(
    url,
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json", "User-Agent": "yt-otomasyon-gemini-test"},
)
try:
    with urllib.request.urlopen(req, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    detail = exc.read().decode("utf-8", "replace")[:1200]
    print(f"GEMINI_TEST_FAIL HTTP {exc.code}: {detail}")
    raise SystemExit(2)
except Exception as exc:
    print(f"GEMINI_TEST_FAIL {type(exc).__name__}: {exc}")
    raise SystemExit(3)

image = None
for candidate in data.get("candidates", []):
    for part in (candidate.get("content") or {}).get("parts", []):
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            image = inline["data"]
            break
    if image:
        break

if not image:
    print("GEMINI_TEST_FAIL: HTTP başarılı fakat inline image bulunamadı")
    print(json.dumps(data, ensure_ascii=False)[:1200])
    raise SystemExit(4)

with open(OUT, "wb") as handle:
    handle.write(base64.b64decode(image))
print(f"GEMINI_TEST_OK model={MODEL} output={OUT} bytes={os.path.getsize(OUT)}")
