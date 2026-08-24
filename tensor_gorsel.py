#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tensor.Art (TAMS) AI görsel üretimi. İki yol destekler:

  A) DOĞRUDAN MODEL (stages) — model_id ile: POST /v1/jobs
     {stages: [INPUT_INITIALIZE, DIFFUSION{sdModel, prompts, ...}]}
  B) AITool (workflow template) — aitools_id ile: GET /v1/workflows/{id} +
     POST /v1/jobs/workflow/template

Her ikisinde de: poll GET /v1/jobs/{id} -> SUCCESS -> successInfo.images[].url indir.
Anahtar (TENSOR_API_KEY) tams.tensor.art/apps'te bir Application altında üretilmeli.
Anahtar koda YAZILMAZ; sadece env'den okunur.
"""
import os, json, time, uuid, urllib.request, urllib.error

BASE = (os.environ.get("TENSOR_BASE_URL") or "https://ap-east-1.tensorart.cloud").rstrip("/")
NEGATIF = ("blurry, low quality, watermark, text, logo, signature, deformed, "
           "ugly, cartoon, drawing, cropped, jpeg artifacts")

def _key():
    return (os.environ.get("TENSOR_API_KEY") or os.environ.get("TENSORART_API_KEY") or "").strip()

def _istek(method, path, govde=None):
    req = urllib.request.Request(BASE + path,
        data=(json.dumps(govde).encode() if govde is not None else None), method=method,
        headers={"Authorization": "Bearer " + _key(),
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
        if durum == "FAILED":
            raise RuntimeError(f"iş başarısız: {json.dumps(j)[:400]}")
        print(f"      [bekleniyor... durum={durum or '?'}]")
    raise RuntimeError("iş zaman aşımı")

# --- A) doğrudan model (stages) ---
def uret_model(prompt, cikti_path, model_id, width=1024, height=576, steps=25):
    govde = {"requestId": uuid.uuid4().hex, "stages": [
        {"type": "INPUT_INITIALIZE", "inputInitialize": {"seed": -1, "count": 1}},
        {"type": "DIFFUSION", "diffusion": {
            "width": int(width), "height": int(height),
            "prompts": [{"text": prompt}], "negativePrompts": [{"text": NEGATIF}],
            "sdModel": str(model_id), "sdVae": "Automatic", "sampler": "Euler a",
            "steps": int(steps), "cfgScale": 7, "clipSkip": 2}}]}
    d = _istek("POST", "/v1/jobs", govde)
    jid = (d.get("job") or {}).get("id") or d.get("jobId") or d.get("id")
    print(f"      [stages iş: id={jid} durum={((d.get('job') or {}).get('status'))}]")
    if not jid:
        raise RuntimeError(f"job id alınamadı: {json.dumps(d)[:400]}")
    return _poll_indir(jid, cikti_path)

# --- B) AITool (workflow template) ---
def uret_aitool(prompt, cikti_path, aitools_id):
    sema = _istek("GET", f"/v1/workflows/{aitools_id}")
    attrs = (sema.get("fields") or {}).get("fieldAttrs") or []
    print(f"      [AITool: {sema.get('name','?')} | alan: {len(attrs)}]")
    print(f"      [fieldAttrs: {json.dumps(attrs, ensure_ascii=False)[:600]}]")
    fields, yazildi = [], False
    for a in attrs:
        fn = a.get("fieldName") or a.get("name")
        fv = a.get("fieldValue", a.get("defaultValue", a.get("default", a.get("value", ""))))
        et = f"{fn} {a.get('label','')} {a.get('title','')}".lower()
        if not yazildi and ("prompt" in et or "text" in et or (fn or "").lower() in ("prompt", "text", "positive")):
            fv, yazildi = prompt, True
        fields.append({"nodeId": a.get("nodeId") or a.get("node_id"), "fieldName": fn, "fieldValue": fv})
    if not yazildi and fields:
        fields[0]["fieldValue"] = prompt
    d = _istek("POST", "/v1/jobs/workflow/template",
               {"requestId": uuid.uuid4().hex, "templateId": str(aitools_id),
                "fields": {"fieldAttrs": fields}})
    jid = (d.get("job") or {}).get("id") or d.get("jobId") or d.get("id")
    print(f"      [aitool iş: id={jid} durum={((d.get('job') or {}).get('status'))}]")
    if not jid:
        raise RuntimeError(f"job id alınamadı: {json.dumps(d)[:400]}")
    return _poll_indir(jid, cikti_path)

def uret(prompt, cikti_path, model_id=None, aitools_id=None, width=1024, height=576):
    if not _key():
        raise RuntimeError("TENSOR_API_KEY yok")
    if model_id:
        return uret_model(prompt, cikti_path, model_id, width, height)
    if aitools_id:
        return uret_aitool(prompt, cikti_path, aitools_id)
    raise RuntimeError("model_id ya da aitools_id gerekli")

if __name__ == "__main__":
    p = os.environ.get("PROMPT") or "underwater ancient ruins of a lost city, cinematic, dramatic god rays, photorealistic"
    m = (os.environ.get("MODEL_ID") or "").strip() or None
    a = (os.environ.get("AITOOLS_ID") or "").strip() or None
    W = int(os.environ.get("WIDTH", "1024")); H = int(os.environ.get("HEIGHT", "576"))
    uret(p, "output/tensor_test.jpg", model_id=m, aitools_id=a, width=W, height=H)
    print("TAMAM ✓")
