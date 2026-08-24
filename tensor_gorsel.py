#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tensor.Art (TAMS) AI görsel üretimi — AITools / workflow template API.
Resmi ComfyUI entegrasyonuyla aynı akış:
  1) GET  /v1/workflows/{aiToolsId}          -> alan şeması (fields.fieldAttrs)
  2) POST /v1/jobs/workflow/template         -> iş oluştur (templateId + fields)
  3) GET  /v1/jobs/{jobId}                    -> poll, SUCCESS'te successInfo.images[].url

Gerekli:
  - TENSOR_API_KEY (secret): tams.tensor.art/apps'te bir APPLICATION altında üretilmiş anahtar.
  - aiToolsId: tensor.art'ta yayınlanmış bir AITool (metin->görsel) workflow ID'si.
Anahtar koda YAZILMAZ; sadece env'den okunur.
"""
import os, json, time, uuid, urllib.request, urllib.error

BASE = (os.environ.get("TENSOR_BASE_URL") or "https://ap-east-1.tensorart.cloud").rstrip("/")

def _key():
    return (os.environ.get("TENSOR_API_KEY") or os.environ.get("TENSORART_API_KEY") or "").strip()

def _istek(method, path, govde=None):
    url = BASE + path
    data = json.dumps(govde).encode() if govde is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + _key(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as he:
        raise RuntimeError(f"HTTP {he.code} ({method} {path}): {he.read().decode()[:500]}")

def _prompt_alanlarini_doldur(field_attrs, prompt):
    """GET şemasındaki alanları {nodeId, fieldName, fieldValue} listesine çevirir;
    prompt/text benzeri alana prompt'u yazar, diğerlerinde mevcut/default değeri korur."""
    out, prompt_yazildi = [], False
    for a in field_attrs:
        node_id = a.get("nodeId") or a.get("node_id")
        fname = a.get("fieldName") or a.get("field_name") or a.get("name")
        fval = a.get("fieldValue", a.get("defaultValue", a.get("default", a.get("value", ""))))
        etiket = f"{fname} {a.get('label','')} {a.get('title','')}".lower()
        if not prompt_yazildi and ("prompt" in etiket or "text" in etiket
                                   or (fname or "").lower() in ("prompt", "text", "positive")):
            fval = prompt
            prompt_yazildi = True
        out.append({"nodeId": node_id, "fieldName": fname, "fieldValue": fval})
    # hiç prompt alanı bulunamadıysa ilk alanı prompt yap (son çare)
    if not prompt_yazildi and out:
        out[0]["fieldValue"] = prompt
    return out

def _indir(url, yol):
    os.makedirs(os.path.dirname(yol) or ".", exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as r, open(yol, "wb") as f:
        f.write(r.read())

def uret(prompt, cikti_path, aitools_id):
    if not _key():
        raise RuntimeError("TENSOR_API_KEY yok")
    if not aitools_id:
        raise RuntimeError("aitools_id gerekli (tensor.art'ta yayınlanmış AITool workflow ID)")
    # 1) alan şeması
    sema = _istek("GET", f"/v1/workflows/{aitools_id}")
    field_attrs = (sema.get("fields") or {}).get("fieldAttrs") or []
    print(f"      [AITool: {sema.get('name','?')} | alan sayısı: {len(field_attrs)}]")
    print(f"      [fieldAttrs şema: {json.dumps(field_attrs, ensure_ascii=False)[:600]}]")
    fields = _prompt_alanlarini_doldur(field_attrs, prompt)
    # 2) iş oluştur
    govde = {"requestId": uuid.uuid4().hex, "templateId": str(aitools_id),
             "fields": {"fieldAttrs": fields}}
    d = _istek("POST", "/v1/jobs/workflow/template", govde)
    jid = (d.get("job") or {}).get("id") or d.get("jobId") or d.get("id")
    print(f"      [tensor iş: id={jid} durum={((d.get('job') or {}).get('status'))}]")
    if not jid:
        raise RuntimeError(f"job id alınamadı: {json.dumps(d)[:400]}")
    # 3) poll
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

if __name__ == "__main__":
    import sys
    p = os.environ.get("PROMPT") or (sys.argv[1] if len(sys.argv) > 1
        else "underwater ancient ruins of a lost city, cinematic, dramatic god rays, photorealistic")
    tool = os.environ.get("AITOOLS_ID") or (sys.argv[2] if len(sys.argv) > 2 else "")
    uret(p, "output/tensor_test.jpg", tool)
    print("TAMAM ✓")
