#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tensor.Art (TAMS) AI görsel üretimi — İMZA TABANLI kimlik (RSA/SHA256).

Önceki deneme sadece `Authorization: Bearer <key>` kullandığı için 'app not found'
alıyordu. TAMS API'si imza ister:

  İmzalanan metin:  METHOD\\nPATH\\nTIMESTAMP\\nNONCE\\nBODY
    NONCE = md5(TIMESTAMP)
  İmza: RSA-SHA256 (PKCS1v15) -> base64
  Header: Authorization: TAMS-SHA256-RSA app_id=..,nonce_str=..,timestamp=..,signature=..

Kaynak: github.com/Tensor-Art/tams-signature-demo (python)

GEREKLİ ortam değişkenleri (GitHub Secrets olarak):
  TENSOR_APP_ID        tams.tensor.art/apps'te oluşturulan App'in id'si
  TENSOR_PRIVATE_KEY   RSA private key (PEM içeriği). Public'i konsola yüklersin.
                       (Alternatif: TENSOR_PRIVATE_KEY_PATH ile dosya yolu)
  TENSOR_BASE_URL      App'in endpoint'i, örn https://ap-east-1.tensorart.cloud
  TENSOR_MODEL_ID      Kullanılacak sdModel id'si (Tensor.Art model sayfasından)

Anahtar KODA YAZILMAZ; yalnızca ortamdan okunur.
"""
import os, json, time, uuid, hashlib, base64, urllib.request, urllib.error

BASE = (os.environ.get("TENSOR_BASE_URL") or "https://ap-east-1.tensorart.cloud").rstrip("/")
NEGATIF = ("blurry, low quality, watermark, text, logo, signature, deformed, "
           "ugly, cropped, jpeg artifacts")


def _app_id():
    return (os.environ.get("TENSOR_APP_ID") or "").strip()


def _pem_temizle(pem):
    """Kopyala-yapıştır kaynaklı bozulmaları düzeltir: BOM, süslü tireler
    (–—‒‑ vb. -> '-'), kaçış '\\n' -> gerçek satır sonu, sar tırnak."""
    import re
    if not pem:
        return ""
    pem = pem.replace("﻿", "")
    for d in ("‐", "‑", "‒", "–", "—", "―",
              "−", "⁃", "－", "─"):
        pem = pem.replace(d, "-")
    if "\\n" in pem and "\n" not in pem.strip():
        pem = pem.replace("\\n", "\n")
    return pem.strip().strip("'\"").strip() + "\n"


def _private_key_pem():
    """PEM içeriğini sırasıyla dener: TENSOR_PRIVATE_KEY_B64 (base64, en sağlam)
    -> TENSOR_PRIVATE_KEY (ham PEM, temizlenir) -> TENSOR_PRIVATE_KEY_PATH."""
    import re, base64
    b64 = os.environ.get("TENSOR_PRIVATE_KEY_B64", "")
    if b64.strip():
        try:
            return base64.b64decode(re.sub(r"\s+", "", b64)).decode("utf-8")
        except Exception as e:
            print(f"      [uyarı: TENSOR_PRIVATE_KEY_B64 çözülemedi: {str(e)[:80]}]")
    pem = os.environ.get("TENSOR_PRIVATE_KEY", "")
    if pem.strip():
        return _pem_temizle(pem)
    yol = os.environ.get("TENSOR_PRIVATE_KEY_PATH", "").strip()
    if yol and os.path.exists(yol):
        with open(yol, "r", encoding="utf-8") as f:
            return _pem_temizle(f.read())
    return ""


def _imza_header(method, path, body):
    """TAMS imzalı Authorization header'ını üretir."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    app_id = _app_id()
    pem = _private_key_pem()
    if not (app_id and pem):
        raise RuntimeError("TENSOR_APP_ID veya TENSOR_PRIVATE_KEY ayarlı değil")

    ts = str(int(time.time()))
    nonce = hashlib.md5(ts.encode()).hexdigest()
    imzalanacak = f"{method.upper()}\n{path}\n{ts}\n{nonce}\n{body or ''}"

    anahtar = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    imza = anahtar.sign(imzalanacak.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    imza_b64 = base64.b64encode(imza).decode()
    return (f"TAMS-SHA256-RSA app_id={app_id},nonce_str={nonce},"
            f"timestamp={ts},signature={imza_b64}")


def _istek(method, path, govde=None):
    body = json.dumps(govde) if govde is not None else ""
    veri = body.encode() if govde is not None else None
    req = urllib.request.Request(
        BASE + path, data=veri, method=method,
        headers={"Authorization": _imza_header(method, path, body),
                 "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as he:
        raise RuntimeError(f"HTTP {he.code} ({method} {path}): {he.read().decode()[:500]}")


def _indir(url, yol):
    os.makedirs(os.path.dirname(yol) or ".", exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as r, open(yol, "wb") as f:
        f.write(r.read())


def _poll_indir(jid, cikti_path):
    for _ in range(80):  # ~4 dk
        time.sleep(3)
        r = _istek("GET", f"/v1/jobs/{jid}")
        j = r.get("job") or r
        durum = (j.get("status") or "").upper()
        if durum == "SUCCESS":
            imgs = (j.get("successInfo") or {}).get("images") or []
            url = next((im.get("url") for im in imgs if im.get("url")), None)
            if not url:
                raise RuntimeError(f"SUCCESS ama görsel yok: {json.dumps(j)[:400]}")
            _indir(url, cikti_path)
            print(f"      [tensor görsel indirildi -> {cikti_path}]")
            return True
        if durum in ("FAILED", "ERROR"):
            raise RuntimeError(f"iş başarısız: {json.dumps(j)[:400]}")
        print(f"      [bekleniyor... durum={durum or '?'}]")
    raise RuntimeError("iş zaman aşımı")


def uret(prompt, cikti_path, model_id=None, width=1024, height=576, steps=25):
    """Verilen prompt ile bir görsel üretip cikti_path'e indirir. Model id
    TENSOR_MODEL_ID env'inden de alınabilir."""
    model_id = model_id or os.environ.get("TENSOR_MODEL_ID", "").strip()
    if not model_id:
        raise RuntimeError("TENSOR_MODEL_ID ayarlı değil (sdModel gerekli)")
    govde = {"requestId": uuid.uuid4().hex, "stages": [
        {"type": "INPUT_INITIALIZE", "inputInitialize": {"seed": -1, "count": 1}},
        {"type": "DIFFUSION", "diffusion": {
            "width": int(width), "height": int(height),
            "prompts": [{"text": prompt}], "negativePrompts": [{"text": NEGATIF}],
            "sdModel": str(model_id), "sdVae": "Automatic", "sampler": "Euler a",
            "steps": int(steps), "cfgScale": 7, "clipSkip": 2}}]}
    d = _istek("POST", "/v1/jobs", govde)
    jid = (d.get("job") or {}).get("id") or d.get("jobId") or d.get("id")
    print(f"      [tensor iş: id={jid} durum={((d.get('job') or {}).get('status'))}]")
    if not jid:
        raise RuntimeError(f"iş id alınamadı: {json.dumps(d)[:400]}")
    return _poll_indir(jid, cikti_path)


def kullanilabilir():
    """video.py'nin güvenle kontrol edebilmesi için: gerekli secret'lar var mı?"""
    return bool(_app_id() and _private_key_pem() and
                os.environ.get("TENSOR_MODEL_ID", "").strip())


if __name__ == "__main__":
    import sys
    prompt = os.environ.get("PROMPT") or (sys.argv[1] if len(sys.argv) > 1 else
             "a cinematic wide shot of a mysterious deep ocean, dramatic lighting")
    cikti = os.environ.get("CIKTI", "output/tensor_test.jpg")
    print(f"[tensor test] app_id set={bool(_app_id())}, key set={bool(_private_key_pem())}, "
          f"model set={bool(os.environ.get('TENSOR_MODEL_ID'))}, base={BASE}")
    uret(prompt, cikti)
    print(f"[tensor test] TAMAM -> {cikti}")
