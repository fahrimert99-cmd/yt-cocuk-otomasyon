#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cloudflare Workers AI model testi (geçici).

1) Hesapta açık modelleri görev türüne göre listeler.
2) Aynı A101 sahnesini her görsel modeliyle üretir, süreyi ölçer, yan yana panel yapar.
3) Whisper'ı önizleme videosunun 30 sn'lik Türkçe sesiyle dener.
Çıktı: onizleme/cf_test/ (rapor.json, rapor.txt, model görselleri, panel.jpg)
"""
import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid

TOKEN = os.environ["CF_API_TOKEN"].strip()
HESAP = os.environ["CF_ACCOUNT_ID"].strip()
API = f"https://api.cloudflare.com/client/v4/accounts/{HESAP}/ai"
CIKTI = "onizleme/cf_test"
os.makedirs(CIKTI, exist_ok=True)

PROMPT = ("photorealistic documentary photo inside a Turkish discount supermarket, "
          "an almost empty promotional shelf with only two boxes left, shoppers with "
          "baskets in the background, fluorescent lighting, cinematic, 35mm, "
          "no text, no letters, blank signs, no logos")

GORSEL_MODELLER = [
    "@cf/black-forest-labs/flux-1-schnell",
    "@cf/black-forest-labs/flux-2-dev",
    "@cf/black-forest-labs/flux-2-klein-9b",
    "@cf/black-forest-labs/flux-2-klein-4b",
    "@cf/leonardo/lucid-origin",
    "@cf/leonardo/phoenix-1.0",
    "@cf/bytedance/stable-diffusion-xl-lightning",
    "@cf/stabilityai/stable-diffusion-xl-base-1.0",
]


def _istek(url, data=None, ctype="application/json", timeout=180):
    h = {"Authorization": f"Bearer {TOKEN}"}
    if data is not None:
        h["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.headers.get("Content-Type", ""), r.read()


def modeller_listele():
    tum, sayfa = [], 1
    while True:
        _, b = _istek(f"{API}/models/search?per_page=100&page={sayfa}")
        d = json.loads(b)
        tum += d.get("result") or []
        if len(d.get("result") or []) < 100:
            break
        sayfa += 1
    gruplar = {}
    for m in tum:
        gorev = (m.get("task") or {}).get("name", "?")
        gruplar.setdefault(gorev, []).append(m.get("name"))
    return gruplar


def _multipart(alanlar):
    sinir = uuid.uuid4().hex
    parca = b""
    for k, v in alanlar.items():
        parca += (f"--{sinir}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    parca += f"--{sinir}--\r\n".encode()
    return parca, f"multipart/form-data; boundary={sinir}"


def _kaydet(ctype, b, yol):
    if ctype.startswith("image/"):
        open(yol, "wb").write(b)
        return True
    d = json.loads(b)
    img = (d.get("result") or {}).get("image") if isinstance(d.get("result"), dict) else None
    if img:
        open(yol, "wb").write(base64.b64decode(img))
        return True
    raise RuntimeError(f"görsel yok: {str(d)[:200]}")


STORYBOOK = ("storybook illustration, hand-painted children's picture book style, soft "
             "watercolor and gouache textures, warm colors, gentle lighting, friendly rounded "
             "shapes, inside a Turkish discount supermarket, an almost empty promotional shelf "
             "with only two boxes left, shoppers with baskets in the background, "
             "no text, no letters, blank signs, no logos")


def gorsel_dene(model, PROMPT=PROMPT, ek=""):
    yol = os.path.join(CIKTI, model.split("/")[-1] + ek + ".jpg")
    url = f"{API}/run/{model}"
    t0 = time.time()
    try:
        if "flux-2" in model:  # FLUX.2 multipart form ister
            data, ct = _multipart({"prompt": PROMPT, "width": 1344, "height": 768})
            ctype, b = _istek(url, data, ct)
        else:
            body = {"prompt": PROMPT}
            if "schnell" in model:
                body["steps"] = 8
            else:
                body.update({"width": 1344, "height": 768})
            ctype, b = _istek(url, json.dumps(body).encode())
        _kaydet(ctype, b, yol)
        return {"model": model + ek, "durum": "OK", "sure_sn": round(time.time() - t0, 1), "dosya": yol}
    except urllib.error.HTTPError as e:
        govde = e.read().decode(errors="ignore")[:300]
        return {"model": model, "durum": f"HTTP {e.code}", "hata": govde}
    except Exception as e:
        return {"model": model, "durum": "HATA", "hata": str(e)[:300]}


def whisper_dene(gruplar):
    asr = [m for m in gruplar.get("Automatic Speech Recognition", []) if "whisper" in m]
    video = "onizleme/uzun/video_480p.mp4"
    if not asr or not os.path.exists(video):
        return {"durum": "atlandı"}
    model = next((m for m in asr if "turbo" in m), asr[0])
    mp3 = "/tmp/klip.mp3"
    import imageio_ffmpeg
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", "60", "-t", "30", "-i", video,
                    "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", mp3], check=True)
    body = {"audio": base64.b64encode(open(mp3, "rb").read()).decode(), "language": "tr"}
    try:
        _, b = _istek(f"{API}/run/{model}", json.dumps(body).encode())
        d = json.loads(b).get("result") or {}
        return {"model": model + ek, "durum": "OK", "metin": (d.get("text") or "")[:600]}
    except urllib.error.HTTPError as e:
        return {"model": model, "durum": f"HTTP {e.code}", "hata": e.read().decode(errors="ignore")[:300]}


def panel(sonuclar):
    from PIL import Image, ImageDraw, ImageFont
    ok = [s for s in sonuclar if s["durum"] == "OK"]
    if not ok:
        return
    w, h = 640, 360
    sut = 2
    sat = (len(ok) + sut - 1) // sut
    P = Image.new("RGB", (w * sut, (h + 40) * sat), (20, 20, 24))
    try:
        f = ImageFont.truetype("assets/font/Anton-Regular.ttf", 26)
    except Exception:
        f = ImageFont.load_default()
    d = ImageDraw.Draw(P)
    for i, s in enumerate(ok):
        im = Image.open(s["dosya"]).convert("RGB")
        r = max(w / im.width, h / im.height)
        im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1))
        im = im.crop(((im.width - w) // 2, (im.height - h) // 2, (im.width - w) // 2 + w, (im.height - h) // 2 + h))
        x, y = (i % sut) * w, (i // sut) * (h + 40)
        P.paste(im, (x, y + 40))
        d.text((x + 10, y + 4), f"{i + 1}. {s['model'].split('/')[-1]}  ({s['sure_sn']} sn)", font=f, fill=(255, 210, 60))
    P.save(os.path.join(CIKTI, "panel.jpg"), quality=88)


def main():
    rapor = {"zaman_utc": time.strftime("%Y-%m-%d %H:%M"), "prompt": PROMPT}
    gruplar = modeller_listele()
    rapor["modeller"] = gruplar
    t2i = gruplar.get("Text-to-Image", [])
    denenecek = [m for m in (os.environ.get("CF_TEST_MODELLER") or "@cf/black-forest-labs/flux-2-dev").split(",") if m in t2i]
    rapor["gorsel"] = []
    for m in denenecek:
        s = gorsel_dene(m)
        print(s)
        rapor["gorsel"].append(s)
        if "flux-2" in m:   # aynı sahnenin storybook (illüstrasyon) sürümü
            s = gorsel_dene(m, STORYBOOK, "-storybook")
            print(s)
            rapor["gorsel"].append(s)
    rapor["kota_dolu"] = any(s["durum"] == "HTTP 429" for s in rapor["gorsel"])
    try:
        rapor["whisper"] = whisper_dene(gruplar)
    except Exception as e:
        rapor["whisper"] = {"durum": "HATA", "hata": str(e)[:300]}
    print(rapor["whisper"])
    panel(rapor["gorsel"])
    json.dump(rapor, open(os.path.join(CIKTI, "rapor.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(CIKTI, "rapor.txt"), "w", encoding="utf-8") as f:
        for g, ms in sorted(gruplar.items()):
            f.write(f"## {g} ({len(ms)})\n" + "\n".join(f"  {m}" for m in ms) + "\n")
        f.write("\n## GÖRSEL TESTİ\n")
        for s in rapor["gorsel"]:
            f.write(f"  {s['model']}: {s['durum']} {s.get('sure_sn', '')} {s.get('hata', '')[:150]}\n")
        f.write(f"\n## WHISPER\n  {rapor['whisper']}\n")


if __name__ == "__main__":
    main()
