#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NVIDIA hesabının HANGİ modellere eriştiğini raporlar (YÜKLEMEZ, salt-okur).

1) GET integrate.api.nvidia.com/v1/models  -> hesabın erişebildiği TÜM modeller
   (OpenAI-uyumlu liste). Tam liste output/nvidia_modeller.txt'e yazılır.
2) Kullandığımız LLM'ler + embedding modeli listede mi, kontrol.
3) Bilinen GÖRSEL (image-gen) endpoint'lerini tek tek yoklar (kısa timeout) ve
   HTTP durumunu raporlar -> hangi görsel modeli GERÇEKTEN çalışıyor, görürüz.

Env: NVIDIA_API_KEY. Özet EN SONA basılır (log aracı yalnızca sonu döndürüyor).
"""
import os, re, json, urllib.request, urllib.error

KEY = re.sub(r"\s", "", os.environ.get("NVIDIA_API_KEY") or "")
OZET = []
def _o(m): OZET.append(str(m)); print(m)


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KEY}",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode()


def _post(url, body, timeout=25):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {KEY}",
                                          "Content-Type": "application/json",
                                          "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode()


def _durum(fn):
    try:
        st, gv = fn()
        return f"OK {st}"
    except urllib.error.HTTPError as he:
        try:
            det = json.loads(he.read().decode())
            msg = det.get("detail") or det.get("title") or det.get("message") or ""
        except Exception:
            msg = ""
        return f"HTTP {he.code} {str(msg)[:70]}"
    except Exception as e:
        return f"{type(e).__name__}: {str(e)[:60]}"


def main():
    print(f"NVIDIA anahtarı mevcut: {bool(KEY)}")
    if not KEY:
        _o("ANAHTAR YOK — NVIDIA_API_KEY secret'ı workflow'a verilmemiş.")
        return

    # 1) Tüm erişilebilir modeller (OpenAI-uyumlu liste)
    ids = []
    try:
        st, gv = _get("https://integrate.api.nvidia.com/v1/models")
        d = json.loads(gv)
        ids = sorted(m.get("id", "") for m in d.get("data", []) if m.get("id"))
    except Exception as e:
        _o(f"/v1/models alınamadı: {type(e).__name__}: {str(e)[:80]}")

    if ids:
        os.makedirs("output", exist_ok=True)
        with open("output/nvidia_modeller.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(ids))
        # kategoriler (isim sezgisi)
        def bul(*kelimeler):
            return [i for i in ids if any(k in i.lower() for k in kelimeler)]
        gorsel = bul("flux", "sdxl", "stable-diffusion", "sana", "consistory", "image", "sd3", "kandinsky", "picasso")
        embed = bul("embed", "embedqa")
        vision = bul("vila", "vision", "neva", "llava", "phi-3-vision", "nvila", "cosmos")
        # SOHBET/CHAT adayları: instruct/nemotron/chat/llama/qwen/mistral/mixtral/gemma
        chat = bul("instruct", "nemotron", "-chat", "llama-3", "qwen", "mistral",
                   "mixtral", "gemma", "deepseek", "phi-4")
        chat = [c for c in chat if c not in vision]   # görselleri ayıkla
        # YENİ KATEGORİLER (kanal için hedeflenen yetenekler)
        reasoning = bul("reason", "-r1", "-qwq", "thinker", "nemotron-super",
                        "nemotron-ultra", "o1", "deepseek-r", "-think")
        rerank = bul("rerank", "reranker", "rankqa")
        ceviri = bul("translate", "megatron", "seamless", "nllb", "gemma")
        _o(f"Toplam erişilebilir model: {len(ids)} (tam liste artifact'ta: nvidia_modeller.txt)")
        _o(f"  SOHBET/LLM ({len(chat)}):")
        for c in chat[:30]:
            _o(f"      - {c}")
        _o(f"  REASONING adayları ({len(reasoning)}): {', '.join(reasoning[:10]) or 'YOK'}")
        _o(f"  RERANK adayları ({len(rerank)}): {', '.join(rerank[:6]) or 'YOK'}")
        _o(f"  ÇEVİRİ/çok-dilli adayları ({len(ceviri)}): {', '.join(ceviri[:8]) or 'YOK'}")
        # VIDEO üretim adayları (isim sezgisi)
        video = bul("video", "svd", "cosmos-predict", "cosmos-transfer", "sora", "ltx",
                    "mochi", "hunyuan-video", "gen-3", "wan", "runway")
        _o(f"  EMBEDDING ({len(embed)}): {', '.join(embed[:6]) or 'YOK'}")
        _o(f"  VISION ({len(vision)}): {', '.join(vision[:8]) or 'YOK'}")
        _o(f"  GÖRSEL adayları /v1/models içinde ({len(gorsel)}): {', '.join(gorsel[:12]) or 'YOK (genai ayrı)'}")
        _o(f"  VIDEO adayları /v1/models içinde ({len(video)}): {', '.join(video[:12]) or 'YOK'}")
        # kullandığımız LLM'ler listede mi
        istedigimiz = ["meta/llama-3.3-70b-instruct", "deepseek-ai/deepseek-v3",
                       "qwen/qwen2.5-72b-instruct", "meta/llama-3.1-70b-instruct"]
        for m in istedigimiz:
            _o(f"  LLM {'✓' if m in ids else '✗'} {m}")

    # 2) LLM chat CANLI probe (varsayılan modelimiz gerçekten cevap veriyor mu)
    llm = _durum(lambda: _post(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        {"model": "meta/llama-3.3-70b-instruct", "max_tokens": 5,
         "messages": [{"role": "user", "content": "de ki: merhaba"}]}))
    _o(f"LLM canlı test (llama-3.3-70b): {llm}")

    # 3) GÖRSEL endpoint'leri tek tek yokla (kısa POST). 'chat/completions'
    #    döndürmeyen görsel modelleri ai.api.nvidia.com/v1/genai altında.
    gorsel_adaylar = [
        "black-forest-labs/flux.1-schnell",
        "black-forest-labs/flux.1-dev",
        "stabilityai/stable-diffusion-xl",
        "stabilityai/stable-diffusion-3-medium",
        "stabilityai/sdxl-turbo",
        "bria/bria-2.3",
    ]
    def _gorsel_govde(m):
        if "flux" in m:                      # FLUX: sade prompt gövdesi
            return {"prompt": "a red apple on a table", "width": 1024,
                    "height": 1024, "steps": 4, "seed": 0}
        return {"text_prompts": [{"text": "a red apple on a table", "weight": 1}],
                "cfg_scale": 5, "sampler": "K_EULER_ANCESTRAL", "seed": 0,
                "steps": 25, "width": 1024, "height": 1024}
    _o("GÖRSEL endpoint yoklaması (ai.api.nvidia.com/v1/genai, 1024x1024):")
    for m in gorsel_adaylar:
        durum = _durum(lambda mm=m: _post(
            f"https://ai.api.nvidia.com/v1/genai/{mm}", _gorsel_govde(mm), timeout=20))
        _o(f"  {durum:<34} {m}")

    # 4) VIDEO üretim endpoint'lerini yokla (bilinen NVIDIA genai video modelleri).
    #    404 = hesapta yok, 422 = erişilebilir (parametre), timeout = ağır/cold.
    #    Video için ayrı bir anahtar (NVIDIA_VIDEO_KEY) varsa onu kullan.
    vkey = re.sub(r"\s", "", os.environ.get("NVIDIA_VIDEO_KEY") or "") or KEY
    def _vpost(url, body, timeout=25):
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {vkey}",
                                              "Content-Type": "application/json",
                                              "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    def _vdurum(fn):
        try:
            fn(); return "OK 200"
        except urllib.error.HTTPError as he:
            try:
                det = json.loads(he.read().decode())
                msg = det.get("detail") or det.get("title") or det.get("message") or ""
            except Exception:
                msg = ""
            return f"HTTP {he.code} {str(msg)[:70]}"
        except Exception as e:
            return f"{type(e).__name__}: {str(e)[:60]}"
    video_adaylar = [
        # WAN (Alibaba) — build.nvidia.com'da video/animasyon modelleri
        "wan-ai/wan2.2-animate-2-14b",
        "alibaba/wan2.2-animate-2-14b",
        "wan-ai/wan2.2-t2v-a14b",
        "wan-ai/wan2.2-i2v-a14b",
        "wan-ai/wan2.1-t2v-14b",
        # Diğer bilinen video modelleri
        "stabilityai/stable-video-diffusion",
        "nvidia/cosmos-predict2-2b",
        "lightricks/ltx-video",
        "tencent/hunyuan-video",
    ]
    _o(f"VIDEO endpoint yoklaması (video anahtarı {'ayrı' if vkey != KEY else 'ana anahtar'}):")
    for m in video_adaylar:
        durum = _vdurum(lambda mm=m: _vpost(
            f"https://ai.api.nvidia.com/v1/genai/{mm}",
            {"prompt": "a busy supermarket aisle", "image": ""}, timeout=20))
        _o(f"  {durum:<34} {m}")

    # 5) VLM (görsel-anlama) CANLI probe — kapak/sahne denetimi için lazım.
    #    Vision modelleri OpenAI-uyumlu chat; küçük bir kırmızı piksel (PNG) +
    #    metin gönderip "cevap veriyor mu" bakarız. İlk birkaç vision adayını dener.
    KIRMIZI_PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1"
                   "HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    vlm_adaylar = (vision[:4] if ids else []) + [
        "meta/llama-3.2-11b-vision-instruct",
        "meta/llama-3.2-90b-vision-instruct",
        "microsoft/phi-3.5-vision-instruct",
        "nvidia/vila",
    ]
    gorulen = set()
    _o("VLM (görsel-anlama) canlı yoklaması:")
    for m in vlm_adaylar:
        if m in gorulen:
            continue
        gorulen.add(m)
        durum = _durum(lambda mm=m: _post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            {"model": m, "max_tokens": 8, "messages": [{"role": "user", "content": [
                {"type": "text", "text": "renk?"},
                {"type": "image_url", "image_url": {"url": KIRMIZI_PNG}}]}]}, timeout=25))
        _o(f"  {durum:<34} {m}")

    # 6) RERANK canlı probe — senaryo/trend seçimi sıralaması için.
    rerank_adaylar = (rerank[:3] if ids else []) + [
        "nvidia/llama-3.2-nv-rerankqa-1b-v2",
        "nvidia/nv-rerankqa-mistral-4b-v3",
    ]
    gorulen2 = set()
    _o("RERANK canlı yoklaması (integrate .../v1/ranking):")
    for m in rerank_adaylar:
        if m in gorulen2:
            continue
        gorulen2.add(m)
        durum = _durum(lambda mm=m: _post(
            "https://integrate.api.nvidia.com/v1/ranking",
            {"model": m, "query": {"text": "ucuz market tuzağı"},
             "passages": [{"text": "market fiyat etiketi hilesi"},
                          {"text": "hava durumu raporu"}]}, timeout=25))
        _o(f"  {durum:<34} {m}")

    # Tam yapılandırılmış raporu dosyaya da yaz (dala yayınlanır -> asistan okur).
    try:
        os.makedirs("output", exist_ok=True)
        with open("output/nvidia_rapor.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(OZET))
    except Exception:
        pass

    print("\n===== NVIDIA MODEL ERISIM OZETI =====")
    for s in OZET:
        print("  " + s)
    print("=====================================")


if __name__ == "__main__":
    main()
