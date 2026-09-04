#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NVIDIA NIM (build.nvidia.com) tabanlı KALİTE araçları — hepsi NON-FATAL.

Herhangi bir hata / erişim sorunu / anahtar yokluğunda sistem ESKİ davranışına
düşer (None ya da orijinal veri döner; ASLA patlamaz). Böylece bu araçlar
sistemi yalnızca İYİLEŞTİRİR, hiçbir koşulda bozamaz.

Araçlar:
  senaryo_iyilestir(sen)  -> senaryoyu ikinci bir güçlü modele eleştirtip
                             hook/netlik/CTA açısından GÜÇLENDİRİR (dict|None).
  benzer_var_mi(baslik, mevcut) -> embedding ile ANLAMSAL tekrar tespiti (bool).

Env (opsiyonel):
  NVIDIA_KRITIK_MODEL  varsayılan deepseek-ai/deepseek-v4-flash-0731 (senaryo eleştirisi)
  NVIDIA_EMBED_MODEL   varsayılan nvidia/nv-embedqa-mistral-7b-v2 (anlamsal benzerlik)
  NVIDIA_BENZERLIK_ESIK varsayılan 0.90 (bu ve üstü kosinüs -> tekrar say)
"""
import os, re, json, math, subprocess, tempfile, urllib.request, urllib.error
import ai_script as A

# Senaryo eleştirisi için buffet'ten güçlü bir reasoning modeli.
# DeepSeek-v4-pro: güçlü akıl yürütme -> senaryo eleştirisi/güçlendirmesi için ideal.
# deepseek-v4-flash: pro kadar güçlü akıl yürütme ama ~2x hızlı -> senaryo başına
# eleştiri/güçlendirme süresi yarıya iner (pro'ya NVIDIA_KRITIK_MODEL ile dönülebilir).
KRITIK_MODEL = os.environ.get("NVIDIA_KRITIK_MODEL", "").strip() or "deepseek-ai/deepseek-v4-flash-0731"
# Anlamsal benzerlik için embedding modeli.
EMBED_MODEL = os.environ.get("NVIDIA_EMBED_MODEL", "").strip() or "nvidia/nv-embedqa-mistral-7b-v2"


def _nvidia_json(prompt, model=None):
    """NVIDIA chat -> JSON dict. HER hata None döner (asla fırlatmaz)."""
    key = A._nvidia_key()
    if not key:
        return None
    try:
        ham = A._nvidia(prompt, key, model=model)
        return json.loads(A._temizle(ham))
    except Exception:
        return None


IYILESTIR_PROMPT = """Sen "TUZAK AVCISI" Türk YouTube Shorts kanalının KIDEMLİ senaryo editörüsün.
Aşağıda bir tüketici-tuzağı senaryosu var. Görevin onu DAHA VURUCU hale getirmek:
- İLK CÜMLE ilk 2 saniyede kaydırmayı durduracak kadar şok/merak dolu olsun.
- Tuzak net anlatılsın; izleyiciye pratik bir KORUNMA ipucu versin.
- Sonda kısa bir ABONE çağrısı + bir sonraki videoya merak bırakan TEASER olsun.
- Uydurma istatistik YOK. Emoji/başlık/madde YOK; düz paragraf. ~100-120 kelime.
- 6 sahne; her sahne için İNGİLİZCE sinematik görsel tarifi.
- TÜRKÇE İMLÂ KUSURSUZ: ç,ğ,ı,İ,ö,ş,ü harflerini eksiksiz kullan; ASCII'ye sadeleştirme.
Anlam/konu AYNI kalsın; sadece güçlendir. Zaten güçlüyse küçük rötuşla iyileştir.

MEVCUT SENARYO (JSON):
{mevcut}

SADECE geçerli JSON döndür, AYNI şema, başka hiçbir şey yazma:
{{"baslik":"...","aciklama":"2-3 cümle","etiketler":["tuzak","tüketici","e3","e4","e5"],
"kanca":"...","script":"...","sahneler":[{{"metin":"...","gorsel":"cinematic english"}}],
"tema":"tuzak"}}"""


def senaryo_iyilestir(sen):
    """Senaryoyu güçlü bir modele eleştirtip güçlendirilmiş sürümü döner.
    Başarısızlıkta None (çağıran orijinali kullanır). Şema/başlık korunur."""
    if not isinstance(sen, dict) or not sen.get("script"):
        return None
    try:
        mevcut = json.dumps({k: sen.get(k) for k in
                             ("baslik", "kanca", "aciklama", "etiketler", "script", "sahneler")},
                            ensure_ascii=False)
    except Exception:
        return None
    d = _nvidia_json(IYILESTIR_PROMPT.format(mevcut=mevcut[:6000]), model=KRITIK_MODEL)
    if not isinstance(d, dict) or not d.get("script"):
        return None
    # Kimlik alanlarını KORU: başlık/kanca/tema orijinalden gelsin (editör bunları
    # değiştirmesin; havuz determinizmi ve marka tutarlılığı için).
    d["baslik"] = sen.get("baslik") or d.get("baslik")
    d["kanca"] = sen.get("kanca") or d.get("kanca")
    d["tema"] = "tuzak"
    # None-güvenli: iyileştirilmiş sürüm etiketleri düşürürse orijinaldekini KORU
    # (sen.get(..., default) None değeri varken default'u DÖNMEZ -> or ile çözülür).
    if not isinstance(d.get("etiketler"), list) or not d["etiketler"]:
        d["etiketler"] = (sen.get("etiketler") if isinstance(sen.get("etiketler"), list)
                          and sen.get("etiketler") else ["tuzak", "tüketici"])
    return d


# ---- Çeviri (TR -> EN) : İngilizce sürüm / kardeş kanal için -----------------
# Senaryoyu doğal, vurucu ABD İngilizcesine çevirir (seslendirme + ekran metni
# için). Görsel promptları zaten İngilizce -> DEĞİŞMEDEN korunur. NON-FATAL.
CEVIRI_MODEL = (os.environ.get("NVIDIA_CEVIRI_MODEL", "").strip()
                or "mistralai/mistral-large-2-instruct")

CEVIRI_PROMPT = """You are a professional TR->EN localizer for a viral YouTube Shorts channel about
consumer traps and money scams. Translate the Turkish scenario below into natural, punchy US English
suitable for spoken narration and on-screen text. Make it idiomatic and engaging, NOT word-for-word.
Keep the same meaning, hook energy, structure and number of scenes. Do NOT invent statistics.
The "gorsel" fields are ENGLISH image prompts already — copy each one UNCHANGED.
Return ONLY valid JSON, SAME schema, nothing else:
{{"baslik":"catchy English title","aciklama":"2-3 sentence English description","etiketler":["english","tags"],
"kanca":"short English hook","script":"English narration ~100-120 words","sahneler":[{{"metin":"English scene text","gorsel":"unchanged english image prompt"}}],"tema":"tuzak"}}

TURKISH SCENARIO (JSON):
{mevcut}"""


def senaryo_cevir(sen):
    """Senaryoyu İngilizceye çevirir (dict|None). 'gorsel' alanları orijinalden
    korunur. Başarısızlıkta None (çağıran İngilizce sürümü atlar). NON-FATAL."""
    if not isinstance(sen, dict) or not sen.get("script"):
        return None
    try:
        mevcut = json.dumps({k: sen.get(k) for k in
                             ("baslik", "kanca", "aciklama", "etiketler", "script", "sahneler")},
                            ensure_ascii=False)
    except Exception:
        return None
    d = _nvidia_json(CEVIRI_PROMPT.format(mevcut=mevcut[:6000]), model=CEVIRI_MODEL)
    if not isinstance(d, dict) or not d.get("script"):
        return None
    d["tema"] = "tuzak"
    # Görsel promptlarını orijinalden GARANTİ ET (model değiştirmiş olabilir).
    try:
        orij = sen.get("sahneler") or []
        for i, s in enumerate(d.get("sahneler") or []):
            if i < len(orij) and (orij[i] or {}).get("gorsel"):
                s["gorsel"] = orij[i]["gorsel"]
    except Exception:
        pass
    # Etiketler güvenceleri (None/boş gelmesin)
    if not isinstance(d.get("etiketler"), list) or not d["etiketler"]:
        d["etiketler"] = ["consumer traps", "scams", "money", "saving", "shopping tips"]
    return d


# ---- Reasoning ile kanca/açılış güçlendirme (nemotron reasoning) ------------
# Havuz doldururken (trend.py) YENİ senaryonun ilk 2 saniyesini bir REASONING
# modeline tasarlatır: hangi merak boşluğu/şok kaydırmayı durdurur diye adım adım
# düşünüp en vurucu kanca + açılış cümlesini üretir. Video yükleme yolunda DEĞİL,
# havuz üretiminde çalışır -> reasoning'in yavaşlığı sorun olmaz. NON-FATAL.
REASONING_MODEL = (os.environ.get("NVIDIA_REASONING_MODEL", "").strip()
                   or "nvidia/llama-3.1-nemotron-ultra-253b-v1")


def _reasoning_json(prompt, sistem="detailed thinking on", model=None):
    """Reasoning modeline sorar; <think>...</think> bloğunu ayıklar; JSON dict
    döndürür. Her hata None (asla fırlatmaz)."""
    key = A._nvidia_key()
    if not key:
        return None
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    body = {"model": model or REASONING_MODEL, "temperature": 0.6,
            "max_tokens": 4096,
            "messages": [{"role": "system", "content": sistem},
                         {"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            d = json.loads(r.read().decode())
        txt = d["choices"][0]["message"]["content"] or ""
        txt = re.sub(r"(?is)<think>.*?</think>", "", txt)   # düşünme bloğunu at
        return json.loads(A._temizle(txt))
    except Exception:
        return None


KANCA_PROMPT = """Sen viral Türk YouTube Shorts uzmanısın. Aşağıdaki tüketici-tuzağı videosu için
İZLEYİCİYİ İLK 2 SANİYEDE DURDURAN en vurucu açılışı tasarla. Adım adım düşün: hangi merak
boşluğu, hangi şok, hangi kişisel tehdit ("senin paran/hakkın") en çok kaydırmayı durdurur?

BAŞLIK: {baslik}
MEVCUT KANCA: {kanca}
METİN: {script}

Kurallar: Türkçe, KUSURSUZ imlâ (ç,ğ,ı,İ,ö,ş,ü; ASCII'ye sadeleştirme). Uydurma sayı/istatistik
YOK. Küfür/abartılı iddia YOK. Konu AYNI kalsın.
- "kanca": kapakta/açılışta kullanılacak EN FAZLA 3 KELİMELİK (2-3 kelime) MERAK/ŞOK ifadesi. 3 kelimeyi ASLA geçme.
- "ilk_cumle": seslendirmenin İLK cümlesi; kurulum DEĞİL, doğrudan şok/twist; en fazla 18 kelime.
SADECE JSON döndür, başka hiçbir şey yazma: {{"kanca":"...","ilk_cumle":"..."}}"""


def _reasoning_acik():
    return (os.environ.get("NVIDIA_REASONING", "1").strip() not in ("0", "false", ""))


def kanca_guclendir(sen):
    """Reasoning modeliyle senaryonun KANCA'sını ve AÇILIŞ cümlesini güçlendirir.
    Dönen alanlar geçerliyse uygular; başarısızsa/kapalıysa orijinali korur.
    Girdiyi yerinde değiştirip döner (NON-FATAL, başlık/konu korunur)."""
    if not _reasoning_acik() or not isinstance(sen, dict) or not sen.get("script"):
        return sen
    d = _reasoning_json(KANCA_PROMPT.format(
        baslik=(sen.get("baslik") or "")[:120],
        kanca=(sen.get("kanca") or "")[:80],
        script=(sen.get("script") or "")[:1600]))
    if not isinstance(d, dict):
        return sen
    yeni_kanca = (d.get("kanca") or "").strip()
    yeni_ilk = (d.get("ilk_cumle") or "").strip()
    # ÜÇ KELİME KURALI: kanca en fazla 3 kelime olmalı (kapak/açılış kısa-vurucu).
    # Model daha uzun döndürürse İLK 3 kelimeye kırp; boşsa orijinali koru.
    if yeni_kanca:
        kelimeler = yeni_kanca.split()
        if len(kelimeler) > 3:
            yeni_kanca = " ".join(kelimeler[:3])
        if 1 <= len(yeni_kanca.split()) <= 3:
            sen["kanca"] = yeni_kanca
    # Açılış cümlesini değiştir: metnin İLK cümlesini yenisiyle değiştir, kalanı koru.
    if yeni_ilk and 3 <= len(yeni_ilk.split()) <= 24:
        eski = sen.get("script") or ""
        m = re.search(r"[.!?]\s", eski)
        kalan = eski[m.end():] if m else eski
        yeni_script = (yeni_ilk.rstrip(".!?") + ". " + kalan).strip()
        if len(yeni_script.split()) >= 55:      # güvenlik: metni kısaltıp bozma
            sen["script"] = yeni_script
    return sen


# ---- Anlamsal benzerlik (embedding) -----------------------------------------
def _embed(metinler, input_type="query"):
    """NVIDIA embeddings -> vektör listesi. Hata None döner (asla fırlatmaz)."""
    key = A._nvidia_key()
    if not key or not metinler:
        return None
    url = "https://integrate.api.nvidia.com/v1/embeddings"
    body = {"input": list(metinler), "model": EMBED_MODEL,
            "input_type": input_type, "encoding_format": "float", "truncate": "END"}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
        return [row["embedding"] for row in d.get("data", [])]
    except Exception:
        return None


def _kosinus(a, b):
    if not a or not b:
        return 0.0
    nokta = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return nokta / (na * nb) if na and nb else 0.0


def benzer_var_mi(baslik, mevcut_basliklar, esik=None):
    """baslik, mevcut başlıklardan biriyle ANLAMSAL olarak (embedding kosinüs)
    yeterince benziyorsa True. Erişim/hata halinde False (tekrarı engelleme
    görevini düz-metin dedup'a bırakır -> asla yanlışlıkla fikir atmaz)."""
    if esik is None:
        try:
            esik = float(os.environ.get("NVIDIA_BENZERLIK_ESIK", "0.90") or "0.90")
        except Exception:
            esik = 0.90
    liste = [b for b in (mevcut_basliklar or []) if b][-60:]   # maliyet: son 60
    if not baslik or not liste:
        return False
    vekt = _embed([baslik] + liste)
    if not vekt or len(vekt) != len(liste) + 1:
        return False
    aday, digerleri = vekt[0], vekt[1:]
    return any(_kosinus(aday, v) >= esik for v in digerleri)


# ---- Görsel üretim (image-gen: SDXL / FLUX / DiffusionGemma) -----------------
# NVIDIA genai görsel endpoint'i. Model NVIDIA_GORSEL_MODEL ile değiştirilebilir.
# Varsayılan flux.1-dev: hesap kontrolünde ERİŞİLEBİLİR çıkan görsel model
# (SDXL/SD3/turbo -> 404, schnell -> timeout). flux-dev daha çok adım ister (>=~30).
GORSEL_MODEL = os.environ.get("NVIDIA_GORSEL_MODEL", "").strip() or "black-forest-labs/flux.1-dev"
# YEDEK görsel modeli: flux başarısız/timeout olursa denenir (hesapta /v1/models
# içinde görünen image-gen). Boş bırakılırsa yedek denenmez.
GORSEL_YEDEK = os.environ.get("NVIDIA_GORSEL_YEDEK", "google/diffusiongemma-26b-a4b-it").strip()


def _base64_cikar(d):
    """NVIDIA görsel yanıtının farklı şemalarından base64 metnini çıkarır."""
    import base64
    aday = None
    if isinstance(d, dict):
        if isinstance(d.get("artifacts"), list) and d["artifacts"]:
            aday = d["artifacts"][0].get("base64") or d["artifacts"][0].get("b64_json")
        elif isinstance(d.get("data"), list) and d["data"]:
            aday = d["data"][0].get("b64_json") or d["data"][0].get("base64")
        else:
            aday = d.get("image") or d.get("b64_json") or d.get("base64")
    if not aday or not isinstance(aday, str):
        return None
    if "," in aday and aday.strip().startswith("data:"):
        aday = aday.split(",", 1)[1]      # "data:image/png;base64,...." önekini at
    try:
        return base64.b64decode(aday)
    except Exception:
        return None


# Teşhis kayıtları — kapak_test.py bunları EN SON basar (log aracı yalnızca son
# pencereyi döndürüyor; erken basılan hatalar kesiliyordu).
SON_TESHIS = []


def _log(m):
    SON_TESHIS.append(str(m))


def _nvcf_iste(url, data, hdr, timeout):
    """NVIDIA genai POST — SENKRON (200) ya da ASYNC (202 + NVCF-REQID -> poll)
    yanıtı işler. cold-start'ta endpoint 202 döner; status endpoint'i sonuç
    hazır olana dek yoklanır. JSON döner (hata fırlatır -> çağıran yakalar)."""
    import time as _t
    req = urllib.request.Request(url, data=data, headers=hdr)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        status = getattr(r, "status", 200)
        reqid = r.headers.get("NVCF-REQID") or r.headers.get("nvcf-reqid")
        govde = r.read().decode()
    _log(f"POST status={status} reqid={'var' if reqid else 'yok'} "
         f"govde_uzunluk={len(govde)} bas={govde[:70]!r}")
    son = _t.time() + timeout
    yoklama = 0
    while status == 202 and reqid and _t.time() < son:
        _t.sleep(5)
        yoklama += 1
        s = urllib.request.Request(
            f"https://api.nvidia.com/v2/nvcf/exec/status/{reqid}", headers=hdr)
        with urllib.request.urlopen(s, timeout=timeout) as sr:
            status = getattr(sr, "status", 200)
            govde = sr.read().decode()
        _log(f"poll#{yoklama} status={status} govde_uzunluk={len(govde)}")
    return json.loads(govde)


def _gorsel_govde(model, prompt, w, h):
    """Model ailesine göre istek gövdesi. SDXL -> text_prompts; FLUX/diğer -> prompt."""
    m = model.lower()
    if "stable-diffusion" in m or "sdxl" in m:
        return {"text_prompts": [{"text": prompt, "weight": 1}],
                "cfg_scale": 5, "sampler": "K_EULER_ANCESTRAL", "seed": 0,
                "steps": 25, "width": w, "height": h}
    if "diffusiongemma" in m or "gemma" in m:
        # DiffusionGemma: sade prompt gövdesi (kesin şema bilinmiyor -> guarded).
        return {"prompt": prompt, "width": w, "height": h, "seed": 0}
    # FLUX: schnell guidance-distilled (4 adım); dev daha çok adım ister (>=~30).
    adim = 4 if "schnell" in m else 50
    return {"prompt": prompt, "width": w, "height": h, "steps": adim, "seed": 0}


def _gorsel_tek(model, prompt, cikti, w, h, timeout):
    """TEK model ile görsel dener. Yol|None döner (hata -> None + teşhis logu)."""
    key = A._nvidia_key()
    url = f"https://ai.api.nvidia.com/v1/genai/{model}"
    body = _gorsel_govde(model, prompt, w, h)
    hdr = {"Content-Type": "application/json", "Accept": "application/json",
           "Authorization": f"Bearer {key}"}
    _log(f"model={model} boyut={w}x{h} timeout={timeout}")
    try:
        d = _nvcf_iste(url, json.dumps(body).encode(), hdr, timeout)
    except urllib.error.HTTPError as he:
        govde = ""
        try:
            govde = he.read().decode()[:200]
        except Exception:
            pass
        _log(f"{model} HTTP {he.code}: {govde}")
        print(f"      (NVIDIA görsel [{model}] HTTP {he.code}: {govde[:140]})")
        return None
    except Exception as e:
        _log(f"{model} HATA {type(e).__name__}: {str(e)[:120]}")
        print(f"      (NVIDIA görsel [{model}] atlandı: {str(e)[:120]})")
        return None
    ham = _base64_cikar(d)
    if not ham:
        _log(f"{model} base64 yok. anahtarlar={list(d)[:8] if isinstance(d, dict) else type(d).__name__}")
        return None
    try:
        os.makedirs(os.path.dirname(cikti) or ".", exist_ok=True)
        with open(cikti, "wb") as f:
            f.write(ham)
        if os.path.getsize(cikti) > 1000:
            _log(f"{model} BAŞARILI: {len(ham)} bayt")
            return cikti
    except Exception:
        pass
    return None


def gorsel_uret(prompt, cikti, genislik=768, yukseklik=1344, timeout=None):
    # NOT: FLUX yalnızca şu boyutları kabul eder: 768,832,896,960,1024,1088,1152,
    # 1216,1280,1344. 768x1344 = dikey 9:16'ya en yakın izinli oran.
    """NVIDIA image-gen ile görsel üretir. Önce GORSEL_MODEL (flux), başarısızsa
    GORSEL_YEDEK (diffusiongemma) denenir. Yol|None döner (hepsi başarısızsa None
    -> çağıran mevcut kapağa/stok'a düşer)."""
    key = A._nvidia_key()
    if not key or not prompt:
        return None
    if timeout is None:
        try:
            timeout = int(os.environ.get("NVIDIA_GORSEL_TIMEOUT", "300") or "300")
        except Exception:
            timeout = 300
    modeller = [GORSEL_MODEL] + ([GORSEL_YEDEK] if (GORSEL_YEDEK and GORSEL_YEDEK != GORSEL_MODEL) else [])
    for model in modeller:
        yol = _gorsel_tek(model, prompt, cikti, genislik, yukseklik, timeout)
        if yol:
            return yol
    return None


def kapak_arkaplani(baslik, kanca="", cikti="output/ai_kapak_bg.jpg"):
    """Türkçe başlıktan sinematik İngilizce bir görsel prompt üretip (LLM),
    NVIDIA image-gen ile dikey (9:16) kapak ARKA PLANI oluşturur. Yol|None.
    Metin/marka üstüne kapak.py tarafından basılır -> görsel sade/dramatik olmalı."""
    key = A._nvidia_key()
    if not key:
        return None
    # 1) Başlıktan güçlü bir görsel prompt kur. EN ÖNEMLİ KURAL: görsel KONUYU
    #    GÖSTERSİN (soyut/gizemli figür DEĞİL). Metin/yazı içermesin; kapak.py yazar.
    pr = _nvidia_json(
        f"""You write image-generation prompts for a Turkish consumer-TRAP YouTube Shorts channel.
Video title (Turkish): "{baslik}". Hook: "{kanca}".

TASK: Write ONE vivid, PHOTOREALISTIC, cinematic image prompt (in English) for a VERTICAL (9:16)
thumbnail background that CLEARLY SHOWS the real subject/setting of THIS specific consumer trap.

CRITICAL RULES:
- MUST be an EXTREME CLOSE-UP / MACRO shot that FILLS THE FRAME with the physical OBJECTS of the
  topic. Shallow depth of field, dramatic light. This leaves NO room for any sign or wall.
  Topic -> close-up object scene:
  buffet/restaurant -> overhead extreme close-up of plates piled with food on a table;
  supermarket/market -> macro close-up of grocery products packed on a shelf, or a cart full of items;
  bank/credit card -> extreme close-up of credit cards fanned out with coins and cash on a dark table;
  subscription/app -> close-up of a hand holding a smartphone whose screen glows with colorful app icons;
  discount/sale -> macro close-up of blank red price tags and stickers on products.
  Pick the close-up that matches THIS title.
- Photorealistic, high detail, dramatic cinematic lighting, high contrast, moody, a subtle sense
  of a hidden trap/deception. Eye-catching for a thumbnail.
- ABSOLUTELY FORBIDDEN: any storefront, shop entrance, building facade, wall, glass door, room
  interior wide shot, sign, signboard, neon sign, billboard, banner, menu board, poster, or any
  flat surface that could carry writing. NO hooded figures, ghosts or mysterious silhouettes.
- NO text, words, letters, numbers, logos or watermark anywhere. Do NOT put the title on a sign.
- Keep the very TOP of the frame darker so an overlaid title stays readable.
Return ONLY JSON: {{"prompt":"extreme close-up photorealistic cinematic image prompt filling the frame with the topic's objects, shallow depth of field, absolutely no signs walls text or storefront"}}""",
        model=A.NVIDIA_MODEL)
    gpr = ""
    if isinstance(pr, dict):
        gpr = (pr.get("prompt") or "").strip()
    if not gpr:
        gpr = (f"extreme close-up macro photo filling the frame with the objects of a consumer "
               f"trap, shallow depth of field, dramatic high-contrast lighting, moody, detailed, "
               f"no storefront, no wall, no sign, theme: {baslik}")
    # güvenlik: MAKRO/yakın-çekim + yazı/tabela/vitrin yok (flux yazı ekleme eğilimini
    # yapısal olarak engelle: kadrajı nesne doldursun, düz yüzey/tabela kalmasın).
    gpr += (", extreme close-up, macro shot, fills the frame, shallow depth of field, "
            "photorealistic, cinematic dramatic lighting, high detail, 9:16 vertical, "
            "no storefront, no shop entrance, no building, no wall, no glass door, "
            "no text, no words, no letters, no numbers, no signage, no signboard, no neon sign, "
            "no billboard, no banner, no poster, no menu board, no logo, no watermark, "
            "no hooded figure, no ghost, no random silhouette")
    # VLM görsel-denetimi: bozuk yazı/tabela ya da konu-dışı görseli reddedip
    # yeniden ürettir (en görünür yer kapak olduğu için burada her zaman açık).
    return gorsel_uret_denetimli(gpr, cikti, konu=baslik, genislik=768, yukseklik=1344)


# ---- VLM görsel-denetimi (llama-3.2-vision) ---------------------------------
# Üretilen kapak/sahne görselini İKİNCİ bir modele (VLM) baktırıp bozuk yazı/
# tabela var mı, konuya uygun mu diye denetler. flux zaman zaman kadraja anlamsız
# yazı/tabela sızdırabiliyor; bu kapı onu yakalayıp yeniden ürettirir. NON-FATAL:
# VLM erişilemezse ya da hata olursa denetimsiz kabul edilir (eski davranış).
# 11b: yazı/konu denetimi için fazlasıyla yeterli VE 90b'den çok daha HIZLI
# (90b cold-start 60 sn'yi aşıp timeout veriyordu -> denetim atlanıyordu). Daha
# güçlü denetim istenirse NVIDIA_VLM_MODEL=meta/llama-3.2-90b-vision-instruct.
VLM_MODEL = os.environ.get("NVIDIA_VLM_MODEL", "").strip() or "meta/llama-3.2-11b-vision-instruct"


def _kucuk_jpg(path):
    """VLM'e göndermek için görseli ~384px'e küçültür (inline base64 < 180KB
    olsun; NVIDIA VLM daha büyük görseli reddeder). ffmpeg ile; başarısızsa
    orijinali döner (boyut kontrolü çağıran tarafta)."""
    try:
        out = os.path.join(tempfile.gettempdir(),
                           "vlm_" + os.path.basename(path) + ".jpg")
        subprocess.run(["ffmpeg", "-y", "-i", path, "-vf", "scale=384:-2",
                        "-q:v", "7", out], capture_output=True, timeout=30)
        if os.path.exists(out) and os.path.getsize(out) > 500:
            return out
    except Exception:
        pass
    return path


def _vlm_json(image_path, prompt, model=None):
    """Görsel + metni VLM'e (OpenAI-uyumlu chat) gönderip JSON dict döndürür.
    Her hata None (asla fırlatmaz)."""
    import base64
    key = A._nvidia_key()
    if not key or not image_path or not os.path.exists(image_path):
        return None
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
    except Exception:
        return None
    if len(b64) > 180_000:      # inline sınırı aşılırsa güvenli tarafta atla
        _log(f"VLM: görsel çok büyük ({len(b64)} b64) -> denetim atlandı")
        return None
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    body = {"model": model or VLM_MODEL, "max_tokens": 120, "temperature": 0.0,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode())
        txt = d["choices"][0]["message"]["content"]
        return json.loads(A._temizle(txt))
    except Exception as e:
        _log(f"VLM hata: {type(e).__name__}: {str(e)[:80]}")
        return None


DENETIM_PROMPT = (
    "You are a strict QA checker for a YouTube thumbnail/scene BACKGROUND image. "
    "Look at the image carefully and answer STRICTLY as JSON: "
    "{{\"yazi\": true or false, \"uygun\": true or false}}. "
    "\"yazi\" = true if the image contains ANY readable or garbled text, letters, "
    "words, numbers, a sign, signboard, logo, menu board, price label with writing, "
    "banner, poster or watermark anywhere (even small, partial or nonsensical). "
    "\"uygun\" = true if the image is a clear, photorealistic scene related to this "
    "topic: \"{konu}\". Be strict about \"yazi\". Return ONLY the JSON, nothing else.")


def gorsel_denetle(image_path, konu):
    """VLM ile görseli denetler. dict {yazi:bool, uygun:bool} | None (VLM yok/
    hata -> None; çağıran denetimsiz kabul eder). NON-FATAL."""
    if not image_path or not os.path.exists(image_path):
        return None
    kucuk = _kucuk_jpg(image_path)
    d = _vlm_json(kucuk, DENETIM_PROMPT.format(konu=(konu or "a consumer trap")[:120]))
    if kucuk != image_path:
        try:
            os.remove(kucuk)
        except Exception:
            pass
    if not isinstance(d, dict):
        return None
    return {"yazi": bool(d.get("yazi")), "uygun": bool(d.get("uygun", True))}


def _denetim_acik():
    return (os.environ.get("NVIDIA_GORSEL_DENETIM", "1").strip() not in ("0", "false", ""))


def _deneme_sayisi():
    try:
        return max(1, int(os.environ.get("NVIDIA_DENETIM_DENEME", "2") or "2"))
    except Exception:
        return 2


def gorsel_uret_denetimli(prompt, cikti, konu, genislik=768, yukseklik=1344):
    """Görsel üretir; VLM ile denetler; bozuk yazı VAR ya da konuya UYGUN DEĞİLSE
    (deneme sınırınca) prompt'u güçlendirip yeniden üretir; kabul edilebilir olanı
    döner. VLM erişilemezse ya da denetim kapalıysa TEK üretimle döner (eski yol).
    Hepsi denetimden kalırsa yine de son üretileni döner (siyah ekrandan iyidir)."""
    if not _denetim_acik():
        return gorsel_uret(prompt, cikti, genislik, yukseklik)
    en_iyi, pr = None, prompt
    for i in range(_deneme_sayisi()):
        yol = gorsel_uret(pr, cikti, genislik, yukseklik)
        if not yol:
            continue
        en_iyi = yol
        rapor = gorsel_denetle(yol, konu)
        if rapor is None:                       # VLM yok -> denetimsiz kabul
            return yol
        if not rapor["yazi"] and rapor["uygun"]:
            _log(f"VLM denetim OK (deneme {i+1})")
            return yol
        _log(f"VLM denetim RED (deneme {i+1}): yazi={rapor['yazi']} uygun={rapor['uygun']}")
        # yeniden üretimde yazı yasağını daha da vurgula
        pr = prompt + (", absolutely no text, no letters, no signage, no logo anywhere; "
                       "pure photographic scene, clean surfaces only")
    return en_iyi


def sahne_gorsel(prompt, cikti, dikey=True):
    """Bir SAHNE için NVIDIA flux ile fotogerçekçi görsel üretir (sahnenin
    İngilizce 'gorsel' tarifiyle). Yol|None döner (başarısızsa çağıran stok/
    eski-AI görsele düşer). Boyut flux'ın kabul ettiği en yakın dikey/yatay.
    """
    key = A._nvidia_key()
    if not key or not (prompt or "").strip():
        return None
    # flux kabul edilen boyutlar: 768..1344 (64 katı). Dikey 9:16 -> 768x1344,
    # yatay 16:9 -> 1344x768.
    if dikey:
        w, h = 768, 1344
    else:
        w, h = 1344, 768
    gpr = (prompt.strip() +
           ", photorealistic, cinematic dramatic lighting, high detail, sharp focus, "
           "no text, no words, no letters, no watermark, no caption, no subtitle")
    # VLM görsel-denetimi (kapaktaki ile aynı kapı); sahne tarifi 'konu' olur.
    return gorsel_uret_denetimli(gpr, cikti, konu=prompt.strip()[:120],
                                 genislik=w, yukseklik=h)


if __name__ == "__main__":
    print("KRITIK_MODEL:", KRITIK_MODEL, "| EMBED_MODEL:", EMBED_MODEL,
          "| GORSEL_MODEL:", GORSEL_MODEL, "| NVIDIA key:", bool(A._nvidia_key()))
