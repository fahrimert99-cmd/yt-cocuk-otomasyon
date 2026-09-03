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
  NVIDIA_KRITIK_MODEL  varsayılan mistralai/mistral-large-2-instruct (senaryo eleştirisi)
  NVIDIA_EMBED_MODEL   varsayılan nvidia/nv-embedqa-mistral-7b-v2 (anlamsal benzerlik)
  NVIDIA_BENZERLIK_ESIK varsayılan 0.90 (bu ve üstü kosinüs -> tekrar say)
"""
import os, re, json, math, urllib.request, urllib.error
import ai_script as A

# Senaryo eleştirisi için buffet'ten güçlü bir reasoning modeli.
KRITIK_MODEL = os.environ.get("NVIDIA_KRITIK_MODEL", "").strip() or "mistralai/mistral-large-2-instruct"
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
    if not isinstance(d.get("etiketler"), list) or not d["etiketler"]:
        d["etiketler"] = sen.get("etiketler", ["tuzak", "tüketici"])
    return d


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


# ---- Görsel üretim (image-gen: SDXL / FLUX) ---------------------------------
# NVIDIA genai görsel endpoint'i. Model NVIDIA_GORSEL_MODEL ile değiştirilebilir.
# Varsayılan flux.1-dev: hesap kontrolünde ERİŞİLEBİLİR çıkan tek görsel model
# (SDXL/SD3/turbo -> 404, schnell -> timeout). flux-dev daha çok adım ister (>=~30).
GORSEL_MODEL = os.environ.get("NVIDIA_GORSEL_MODEL", "").strip() or "black-forest-labs/flux.1-dev"


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
    """Model ailesine göre istek gövdesi. SDXL -> text_prompts; FLUX -> prompt."""
    m = model.lower()
    if "stable-diffusion" in m or "sdxl" in m:
        return {"text_prompts": [{"text": prompt, "weight": 1}],
                "cfg_scale": 5, "sampler": "K_EULER_ANCESTRAL", "seed": 0,
                "steps": 25, "width": w, "height": h}
    # FLUX: schnell guidance-distilled (4 adım); dev daha çok adım ister (>=~30).
    adim = 4 if "schnell" in m else 50
    return {"prompt": prompt, "width": w, "height": h, "steps": adim, "seed": 0}


def gorsel_uret(prompt, cikti, genislik=768, yukseklik=1344, timeout=None):
    # NOT: FLUX schnell yalnızca şu boyutları kabul eder: 768,832,896,960,1024,
    # 1088,1152,1216,1280,1344. 768x1344 = dikey 9:16'ya en yakın izinli oran.
    """NVIDIA image-gen ile görsel üretip `cikti`ya kaydeder. Yol|None döner
    (her hata/erişim sorunu None -> çağıran mevcut kapağa düşer)."""
    key = A._nvidia_key()
    if not key or not prompt:
        return None
    if timeout is None:
        try:
            timeout = int(os.environ.get("NVIDIA_GORSEL_TIMEOUT", "300") or "300")
        except Exception:
            timeout = 300
    url = f"https://ai.api.nvidia.com/v1/genai/{GORSEL_MODEL}"
    body = _gorsel_govde(GORSEL_MODEL, prompt, genislik, yukseklik)
    hdr = {"Content-Type": "application/json", "Accept": "application/json",
           "Authorization": f"Bearer {key}"}
    _log(f"model={GORSEL_MODEL} boyut={genislik}x{yukseklik} timeout={timeout}")
    try:
        d = _nvcf_iste(url, json.dumps(body).encode(), hdr, timeout)
    except urllib.error.HTTPError as he:
        govde = ""
        try:
            govde = he.read().decode()[:200]
        except Exception:
            pass
        _log(f"HTTP {he.code}: {govde}")
        print(f"      (NVIDIA görsel HTTP {he.code}: {govde[:160]})")
        return None
    except Exception as e:
        _log(f"HATA {type(e).__name__}: {str(e)[:140]}")
        print(f"      (NVIDIA görsel atlandı: {str(e)[:140]})")
        return None
    ham = _base64_cikar(d)
    if not ham:
        _log(f"base64 bulunamadı. yanıt anahtarları={list(d)[:8] if isinstance(d, dict) else type(d).__name__}")
        return None
    _log(f"BAŞARILI: {len(ham)} bayt görsel çözüldü")
    try:
        os.makedirs(os.path.dirname(cikti) or ".", exist_ok=True)
        with open(cikti, "wb") as f:
            f.write(ham)
        return cikti if os.path.getsize(cikti) > 1000 else None
    except Exception:
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
- The image MUST DEPICT the concrete real-world scene/objects of the topic, so a viewer instantly
  gets what it is about. Examples of mapping topic -> scene:
  buffet/restaurant -> a lavish restaurant buffet table full of plates and food under dramatic light;
  supermarket/market -> close-up of grocery shelves and products, a shopping cart full of items;
  bank/credit card -> close-up of credit cards, coins and cash on a dark table, an ATM keypad;
  subscription/app -> a smartphone glowing in the dark showing colorful app icons (NO readable words);
  discount/sale -> blank red price stickers and tags (NO readable words).
  Pick the scene that matches THIS title.
- Photorealistic, high detail, dramatic cinematic lighting, high contrast, moody, a subtle sense
  of a hidden trap/deception. Eye-catching for a thumbnail.
- ABSOLUTELY NO hooded figures, no ghosts, no random mysterious silhouettes, no abstract mood-only art.
- DO NOT describe ANY signs, storefront signage, neon signs, billboards, banners, menus, posters,
  screens with words, or any object bearing readable letters/numbers. Prefer a tight scene of
  physical objects (food, products, cards, coins, hands) instead of a shop entrance/sign.
- Keep the TOP THIRD of the frame dark, empty and uncluttered (a title will be overlaid on top).
- NO text, no words, no letters, no logos, no watermark anywhere in the image.
Return ONLY JSON: {{"prompt":"detailed photorealistic cinematic english image prompt, shows the topic, physical objects only, absolutely no text or signage"}}""",
        model=A.NVIDIA_MODEL)
    gpr = ""
    if isinstance(pr, dict):
        gpr = (pr.get("prompt") or "").strip()
    if not gpr:
        gpr = (f"photorealistic cinematic vertical thumbnail showing the real scene of a consumer "
               f"trap, dramatic high-contrast lighting, moody, detailed, eye-catching, relevant "
               f"real-world objects, no people close-up, theme: {baslik}")
    # güvenlik: konuyu göster + yazı/tabela yok kurallarını pekiştir (flux yazı ekleme
    # eğilimini bastır), üst alanı boş tut, soyut figürleri engelle.
    gpr += (", photorealistic, cinematic dramatic lighting, high detail, 9:16 vertical, "
            "dark empty space at the top, "
            "no text, no words, no letters, no numbers, no signage, no signboard, no neon sign, "
            "no billboard, no banner, no poster, no menu board, no logo, no watermark, "
            "no hooded figure, no ghost, no random silhouette")
    return gorsel_uret(gpr, cikti, genislik=768, yukseklik=1344)


if __name__ == "__main__":
    print("KRITIK_MODEL:", KRITIK_MODEL, "| EMBED_MODEL:", EMBED_MODEL,
          "| GORSEL_MODEL:", GORSEL_MODEL, "| NVIDIA key:", bool(A._nvidia_key()))
