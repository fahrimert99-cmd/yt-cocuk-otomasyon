#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Senaryo Üretici (IMPROVED — Robust JSON parsing + Validation)
"""
import os, re, json, time, urllib.parse, urllib.request
from typing import Dict, Any

PROMPT = """Sen Veritasium tarzinda bilim icerigi ureten bir YouTube yazarisin.
BASLIK: {baslik}
Bu baslik icin genel izleyiciye uygun, akici, bilimsel olarak DOGRU bir Turkce seslendirme metni yaz. ~110 kelime, ilk cumle guclu bir kanca olsun, sonda dusundurucu bir kapanis. Emoji/baslik/madde YOK, duz paragraf. Anlatimi 5 sahneye bol; her sahne icin INGILIZCE sinematik bir gorsel tarifi yaz.
CEVABINI SADICE gecerli JSON olarak ver. Baska hicbir sey yazma, aciklama/kod blogu ekleme:
{{"baslik":"...","aciklama":"2-3 cumle","etiketler":["e1","e2","e3","e4","e5"],"script":"...","sahneler":[{{"metin":"...","gorsel":"cinematic english description"}}]}}"""


def _temizle_robust(text: str) -> str:
    """
    Robust JSON extraction:
    - Strip markdown code blocks
    - Handle nested objects with balanced braces
    - Try multiple strategies
    """
    text = (text or "").strip()
    
    # Strategy 1: Strip markdown code blocks
    text = re.sub(r"^```(json)?", "", text, flags=re.MULTILINE).strip()
    text = re.sub(r"```$", "", text, flags=re.MULTILINE).strip()
    
    # Strategy 2: Find balanced braces (handles nested objects)
    brace_count = 0
    start_idx = -1
    
    for i, char in enumerate(text):
        if char == "{":
            if brace_count == 0:
                start_idx = i
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0 and start_idx >= 0:
                json_str = text[start_idx:i+1]
                try:
                    json.loads(json_str)  # Verify it's valid JSON
                    return json_str
                except json.JSONDecodeError:
                    continue  # Try next candidate
    
    # Strategy 3: Try raw text as-is
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    
    # Failed all strategies
    raise ValueError(f"No valid JSON found in response")


def _validate_output(data: Dict[str, Any], baslik: str) -> Dict[str, Any]:
    """
    Validate AI-generated scenario structure + content.
    """
    required = ["baslik", "aciklama", "script", "sahneler", "seslendirme"]
    
    # 1. Check all required fields exist
    for field in required:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
        
        # Check not empty
        if isinstance(data[field], str):
            if not data[field].strip():
                raise ValueError(f"Field '{field}' is empty")
        elif isinstance(data[field], list):
            if len(data[field]) == 0:
                raise ValueError(f"Array '{field}' is empty")
        elif isinstance(data[field], dict):
            if len(data[field]) == 0:
                raise ValueError(f"Object '{field}' is empty")
    
    # 2. Validate script length
    script_len = len(data["script"].split())
    if script_len < 50:
        raise ValueError(f"Script too short ({script_len} words, min 50)")
    if script_len > 200:
        raise ValueError(f"Script too long ({script_len} words, max 200)")
    
    # 3. Validate sahneler structure
    sahneler = data["sahneler"]
    if not isinstance(sahneler, list):
        raise ValueError(f"'sahneler' must be array, got {type(sahneler)}")
    
    if len(sahneler) < 3:
        raise ValueError(f"'sahneler' must have >=3 scenes, got {len(sahneler)}")
    
    for i, sahne in enumerate(sahneler):
        if not isinstance(sahne, dict):
            raise ValueError(f"sahne[{i}] must be object, got {type(sahne)}")
        
        if "metin" not in sahne or not sahne["metin"].strip():
            raise ValueError(f"sahne[{i}] missing/empty 'metin'")
        
        if "gorsel" not in sahne or not sahne["gorsel"].strip():
            raise ValueError(f"sahne[{i}] missing/empty 'gorsel'")
    
    # 4. Validate seslendirme
    ss = data["seslendirme"]
    if not isinstance(ss, dict):
        raise ValueError(f"'seslendirme' must be object, got {type(ss)}")
    
    for field in ["motor", "ses", "hiz", "pitch"]:
        if field not in ss:
            raise ValueError(f"'seslendirme' missing: {field}")
    
    return data


def _gemini(prompt: str, key: str, model: str = "gemini-2.0-flash") -> str:
    """Call Gemini API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json"
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read().decode())
    return d["candidates"][0]["content"]["parts"][0]["text"]


def _poll_post(prompt: str) -> str:
    """Call Pollinations POST endpoint."""
    url = "https://text.pollinations.ai/openai"
    body = {
        "model": "openai",
        "temperature": 0.9,
        "messages": [
            {"role": "system", "content": "Yalnizca gecerli JSON dondur."},
            {"role": "user", "content": prompt}
        ]
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "yt"}
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    return d["choices"][0]["message"]["content"]


def _poll_get(prompt: str) -> str:
    """Call Pollinations GET endpoint."""
    q = urllib.parse.quote(prompt)
    url = f"https://text.pollinations.ai/{q}?model=openai"
    req = urllib.request.Request(url, headers={"User-Agent": "yt"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "ignore")


def uret(baslik: str) -> Dict[str, Any]:
    """
    Generate scenario from title (with robust fallback + validation).
    """
    prompt = PROMPT.format(baslik=baslik)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    
    yollar = []
    if key:
        yollar.append(("gemini", lambda: _gemini(prompt, key)))
    
    yollar += [
        ("poll_post", lambda: _poll_post(prompt)),
        ("poll_get", lambda: _poll_get(prompt))
    ]
    
    hatalar = []
    
    for ad, yol in yollar:
        denemeler = 4 if ad == "gemini" else 1
        
        for k in range(denemeler):
            try:
                ham = yol()
                json_str = _temizle_robust(ham)
                data = json.loads(json_str)
                
                # Validate output
                validated = _validate_output(data, baslik)
                
                print(f"✓ AI senaryo üretildi ({ad})")
                return validated
            
            except json.JSONDecodeError as e:
                msg = f"JSON parse error: {str(e)[:80]}"
                hatalar.append(f"{ad}#{k+1}: {msg}")
            
            except ValueError as e:
                msg = str(e)
                hatalar.append(f"{ad}#{k+1}: Validation: {msg[:80]}")
            
            except Exception as e:
                msg = str(e)
                hatalar.append(f"{ad}#{k+1}: {type(e).__name__}: {msg[:100]}")
                
                # Rate limit backoff
                if "429" in msg and k < denemeler - 1:
                    print(f"  ⏳ Rate limited, waiting 30s...")
                    time.sleep(30)
                else:
                    break
    
    import time as _t
    error_msg = " || ".join(hatalar)
    raise SystemExit(
        f"❌ AI senaryo uretilemedi @{_t.strftime('%H:%M:%S')}\n{error_msg}"
    )


if __name__ == "__main__":
    import sys
    
    baslik = sys.argv[1] if len(sys.argv) > 1 else "Gökyüzü neden mavidir?"
    
    try:
        scenario = uret(baslik)
        print(json.dumps(scenario, ensure_ascii=False, indent=2))
    except SystemExit as e:
        print(str(e), file=__import__('sys').stderr)
        sys.exit(1)
