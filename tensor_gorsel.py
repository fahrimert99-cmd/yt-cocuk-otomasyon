#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tensor.Art (TAMS) AI görsel üretimi — REST API (Bearer token).
POST /v1/jobs ile iş oluşturur, durumu poll eder, sonuç görselini indirir.
Gerekli: TENSOR_API_KEY (env). model_id tensor.art model sayfasından alınır.

Şu an TEST/deneme amaçlı bağımsız modül; doğrulandıktan sonra video.py'ye
gorsel_stil='tensor' olarak bağlanacak. Ağ erişimi GitHub Actions runner'ında
olduğu için doğrulama workflow ile yapılır.
"""
import os, json, time, uuid, urllib.request, urllib.error

BASE = "https://ap-east-1.tensorart.cloud"
NEGATIF = ("blurry, low quality, watermark, text, logo, signature, deformed, "
           "ugly, cartoon, drawing, cropped, jpeg artifacts")

def _key():
    return (os.environ.get("TENSOR_API_KEY") or os.environ.get("TENSORART_API_KEY") or "").strip()

def _istek(method, path, govde=None):
    url = BASE + path
    data = json.dumps(govde).encode() if govde is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + _key(),
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as he:
        raise RuntimeError(f"HTTP {he.code}: {he.read().decode()[:500]}")

def _job_id(d):
    return d.get("jobId") or (d.get("job") or {}).get("id") or d.get("id")

def _job_durum(d):
    j = d.get("job") or d
    return (j.get("status") or "").upper()

def _job_gorsel_url(d):
    j = d.get("job") or d
    si = j.get("successInfo") or {}
    for im in (si.get("images") or []):
        u = im.get("url") or im.get("imageUrl")
        if u:
            return u
    return None

def _indir(url, yol):
    os.makedirs(os.path.dirname(yol) or ".", exist_ok=True)
    with urllib.request.urlopen(url, timeout=90) as r, open(yol, "wb") as f:
        f.write(r.read())

def uret(prompt, cikti_path, model_id, width=1024, height=576, steps=25, cfg=7):
    """Prompt'tan görsel üretir, cikti_path'e indirir. Başarılıysa True."""
    if not _key():
        raise RuntimeError("TENSOR_API_KEY yok")
    if not model_id:
        raise RuntimeError("model_id gerekli (tensor.art model numarası)")
    govde = {
        "requestId": uuid.uuid4().hex,
        "stages": [
            {"type": "INPUT_INITIALIZE", "inputInitialize": {"seed": -1, "count": 1}},
            {"type": "DIFFUSION", "diffusion": {
                "width": int(width), "height": int(height),
                "prompts": [{"text": prompt}],
                "negativePrompts": [{"text": NEGATIF}],
                "sdModel": str(model_id),
                "sdVae": "Automatic",
                "sampler": "Euler a",
                "steps": int(steps),
                "cfgScale": cfg,
                "clipSkip": 2,
            }},
        ],
    }
    d = _istek("POST", "/v1/jobs", govde)
    jid = _job_id(d)
    print(f"      [tensor iş oluşturuldu: id={jid} durum={_job_durum(d)}]")
    if not jid:
        raise RuntimeError(f"job id alınamadı: {json.dumps(d)[:400]}")
    for _ in range(60):  # ~3 dk poll
        time.sleep(3)
        r = _istek("GET", f"/v1/jobs/{jid}")
        durum = _job_durum(r)
        if durum in ("SUCCESS", "SUCCEED", "SUCCEEDED", "FINISH", "FINISHED", "DONE"):
            url = _job_gorsel_url(r)
            if not url:
                raise RuntimeError(f"başarılı ama görsel url yok: {json.dumps(r)[:400]}")
            _indir(url, cikti_path)
            print(f"      [tensor görsel indirildi -> {cikti_path}]")
            return True
        if durum in ("FAILED", "FAIL", "ERROR", "CANCELED", "CANCELLED"):
            raise RuntimeError(f"iş başarısız ({durum}): {json.dumps(r)[:400]}")
        print(f"      [tensor bekleniyor... durum={durum or '?'}]")
    raise RuntimeError("iş zaman aşımı (SUCCESS gelmedi)")

if __name__ == "__main__":
    import sys
    p = os.environ.get("PROMPT") or (sys.argv[1] if len(sys.argv) > 1
        else "underwater ancient ruins of a lost city, cinematic, dramatic god rays, photorealistic")
    m = os.environ.get("MODEL_ID") or (sys.argv[2] if len(sys.argv) > 2 else "")
    W = int(os.environ.get("WIDTH", "1024")); H = int(os.environ.get("HEIGHT", "576"))
    uret(p, "output/tensor_test.jpg", m, width=W, height=H)
    print("TAMAM ✓")
