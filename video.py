#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
  YOUTUBE NIŞ VIDEO ÜRETIM HATTI  (Faceless / Yüzsüz)
  Tek komutla: Metin -> Seslendirme + Alt Yazı + Görsel -> MP4
  Bağımlılık: python3, ffmpeg, edge-tts, Pillow   (hepsi ücretsiz)
============================================================

KULLANIM:
    python3 make_video.py --script script.txt
    python3 make_video.py --script script.txt --ses erkek
    python3 make_video.py --script script.txt --dikey        (Shorts 9:16)

Görsel kaynağı:
    - assets/ klasörüne .jpg/.png koyarsanız onları sırayla kullanır (Ken Burns zoom).
    - Klasör boşsa, metinden otomatik başlık kartları üretir (sıfır dış kaynak).
"""

import os, re, sys, glob, json, math, asyncio, argparse, subprocess, tempfile, shutil

# ----------------------------------------------------------
# AYARLAR  (istediğiniz gibi değiştirin)
# ----------------------------------------------------------
CONFIG = {
    "sesler": {
        "kadin": "tr-TR-EmelNeural",
        "erkek": "tr-TR-AhmetNeural",
    },
    "varsayilan_ses": "erkek",
    "konusma_hizi":   "+10%",        # örn "+10%" daha hızlı, "-10%" daha yavaş
    "yatay":  (1920, 1080),         # 16:9
    "dikey":  (1080, 1920),         # 9:16 Shorts
    "fps": 30,
    # Alt yazı stili (libass / ASS)
    "altyazi": {
        "font": "DejaVu Sans",      # sizin makinede "Arial" yazabilirsiniz
        "punto_yatay": 24,
        "punto_dikey": 17,
        "renk": "&H00FFFFFF",       # beyaz
        "kenar_renk": "&H00000000", # siyah kenarlık
        "kenar_kalinlik": 4,
        "alt_bosluk": 60,
    },
    "altyazi_max_kelime": 3,        # kelime kelime vurgulu (Shorts tarzı)
    "altyazi_max_sure": 4.0,        # bir alt yazı satırının max süresi (sn)
    "output_dir": "output",
    "assets_dir": "assets",
}

# ----------------------------------------------------------
# 0. YARDIMCI: Türkçe güvenli büyük harf (İ/ı bug'ı için)
# ----------------------------------------------------------
def tr_upper(s):
    tbl = str.maketrans({"i": "İ", "ı": "I", "ş": "Ş", "ğ": "Ğ",
                         "ü": "Ü", "ö": "Ö", "ç": "Ç"})
    return s.translate(tbl).upper()

# ----------------------------------------------------------
# 1. METİN OKUMA + CÜMLELERE AYIRMA
# ----------------------------------------------------------
def metni_oku(path):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    # yorum satırlarını (# ile başlayan) at
    lines = [l for l in raw.splitlines() if not l.strip().startswith("#")]
    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()
    # cümlelere ayır (. ! ? sonrası)
    cumleler = re.split(r"(?<=[.!?])\s+", text)
    cumleler = [c.strip() for c in cumleler if c.strip()]
    return text, cumleler

# ----------------------------------------------------------
# 2. SESLENDIRME + ZAMAN-SENKRON ALT YAZI (edge-tts)
#    Çıktı: narration.mp3  +  subtitle cue listesi
# ----------------------------------------------------------
async def _tts(text, voice, rate, mp3_path, pitch="+0Hz"):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    boundaries = []
    with open(mp3_path, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                boundaries.append({
                    "start": ch["offset"] / 1e7,           # 100ns -> sn
                    "dur":   ch["duration"] / 1e7,
                    "text":  ch["text"],
                })
    return boundaries

def seslendir(text, voice, rate, mp3_path, pitch="+0Hz"):
    return asyncio.run(_tts(text, voice, rate, mp3_path, pitch=pitch))

# ----------------------------------------------------------
# 2b. PROSODİK SESLENDIRME (cümle bazlı vurgu/tonlama)
#     Her cümle, türüne göre farklı hız+ton ile ayrı seslendirilir,
#     aralara doğal duraklama eklenir; monoton robot sesi kırılır.
# ----------------------------------------------------------
def _pct(s):
    return int(re.sub(r"[^\-+\d]", "", s) or 0)

def _hz(s):
    return int(re.sub(r"[^\-+\d]", "", s) or 0)

def _cumle_prosodi(i, n, cumle, base_rate, base_pitch):
    """Cümlenin türüne/konumuna göre (rate, pitch, sonraki duraklama sn) döndürür."""
    rate, pitch = base_rate, base_pitch
    pause = 0.28
    if i == 0:                                  # kanca: enerjik, biraz yüksek ton
        rate += 0; pitch += 5; pause = 0.40
    elif i == n - 1:                            # kapanış: yavaş, derin, düşündürücü
        rate -= 8; pitch -= 4; pause = 0.0
    elif cumle.rstrip().endswith("?"):          # soru: yükselen ton, sonrası nefes payı
        pitch += 6; pause = 0.42
    elif cumle.rstrip().endswith("!"):          # ünlem: enerjik ve hafif hızlı
        rate += 4; pitch += 4; pause = 0.32
    elif len(cumle.split()) <= 4:               # kısa vurucu cümle: yavaş ve vurgulu
        rate -= 6; pitch += 2; pause = 0.38
    else:                                       # normal anlatım: hafif dalgalanma
        pitch += (2 if i % 2 == 0 else -2)
    return rate, pitch, pause

def _mp3_to_pcm(mp3_path):
    """mp3 -> 24kHz mono s16le ham PCM baytları (ffmpeg)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", mp3_path,
                        "-f", "s16le", "-ac", "1", "-ar", "24000", "-"],
                       capture_output=True, check=True)
    return r.stdout

def seslendir_prosodik(cumleler, voice, rate, mp3_path, pitch="+0Hz"):
    """Cümle cümle farklı prosodi ile seslendirir, tek mp3'te birleştirir.
    Dönüş: zaman kaydırması yapılmış WordBoundary listesi (alt yazı senkronu korunur)."""
    base_rate, base_pitch = _pct(rate), _hz(pitch)
    tmp = tempfile.mkdtemp()
    SR, BPS = 24000, 2                      # 24 kHz, 16-bit mono
    pcm = bytearray()
    boundaries = []
    n = len(cumleler)
    for i, cumle in enumerate(cumleler):
        r, p, pause = _cumle_prosodi(i, n, cumle, base_rate, base_pitch)
        seg = os.path.join(tmp, f"seg{i:03d}.mp3")
        seg_bnd = asyncio.run(_tts(cumle, voice,
                                   f"{'+' if r >= 0 else ''}{r}%",
                                   seg,
                                   pitch=f"{'+' if p >= 0 else ''}{p}Hz"))
        data = _mp3_to_pcm(seg)
        offset = len(pcm) / (SR * BPS)      # bu segmentin başlangıç saniyesi
        for b in seg_bnd:
            boundaries.append({"start": b["start"] + offset,
                               "dur": b["dur"], "text": b["text"]})
        pcm.extend(data)
        if pause > 0 and i < n - 1:         # cümleler arası doğal nefes
            pcm.extend(b"\x00" * int(SR * BPS * pause))
    rawf = os.path.join(tmp, "full.pcm")
    with open(rawf, "wb") as f:
        f.write(bytes(pcm))
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-f", "s16le", "-ac", "1", "-ar", str(SR), "-i", rawf,
                    "-b:a", "128k", mp3_path], check=True)
    return boundaries

def cue_olustur(boundaries, max_kelime, max_sure):
    """WordBoundary listesini alt yazı cue'larına gruplar."""
    cues, buf = [], []
    def flush():
        if not buf:
            return
        start = buf[0]["start"]
        end   = buf[-1]["start"] + buf[-1]["dur"]
        txt   = " ".join(w["text"] for w in buf)
        cues.append({"start": start, "end": end, "text": txt})
        buf.clear()
    for w in boundaries:
        buf.append(w)
        cumle_sonu = w["text"].endswith((".", "!", "?", ":", ";", ","))
        sure = (buf[-1]["start"] + buf[-1]["dur"]) - buf[0]["start"]
        if len(buf) >= max_kelime or sure >= max_sure or cumle_sonu:
            flush()
    flush()
    return cues

# ----------------------------------------------------------
# 3. ALT YAZI DOSYASI (.ass) — profesyonel gömülü stil
# ----------------------------------------------------------
def _ass_zaman(t):
    h = int(t // 3600); t -= h*3600
    m = int(t // 60);   t -= m*60
    s = int(t)
    cs = int((t - s) * 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"

def ass_yaz(cues, path, cfg, dikey, kanca=None):
    a = cfg["altyazi"]
    punto = a["punto_dikey"] if dikey else a["punto_yatay"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {'1080' if dikey else '1920'}
PlayResY: {'1920' if dikey else '1080'}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Def,{a['font']},{punto*4},{a['renk']},{a['kenar_renk']},&H88000000,-1,{a['kenar_kalinlik']},1,2,80,80,{a['alt_bosluk']}
Style: Kanca,{a['font']},{int(punto*4*1.62)},&H0000DDFF,&H00000000,&H00000000,-1,7,2,8,70,70,{240 if dikey else 90}
Style: Abone,{a['font']},{int(punto*4*0.92)},&H00FFFFFF,&H002020E0,&H00000000,-1,6,0,2,60,60,{int((240 if dikey else 90)*1.15)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(head)
        if kanca:
            k = str(kanca).strip().replace("\n", " ")
            f.write(f"Dialogue: 1,0:00:00.00,0:00:02.60,Kanca,,0,0,0,,"
                    f"{{\\fad(100,320)}}{k}\n")
        for c in cues:
            txt = c["text"].replace("\n", " ")
            f.write(f"Dialogue: 0,{_ass_zaman(c['start'])},{_ass_zaman(c['end'])},Def,,0,0,0,,{txt}\n")
        # --- ABONE OL kartı: son ~1.8sn, alt-orta, seslendirmeye dokunmaz ---
        if cues:
            son = cues[-1]["end"]
            basla = max(0.0, son - 1.8)
            f.write(f"Dialogue: 2,{_ass_zaman(basla)},{_ass_zaman(son + 0.4)},Abone,,0,0,0,,"
                    f"{{\\fad(200,150)}}\u25B6 ABONE OL  \u2022  her ak\u015fam yeni tuzak\n")

# ----------------------------------------------------------
# 4. GÖRSELLER
#    a) assets/ doluysa -> resimleri kullan
#    b) boşsa -> metinden otomatik başlık kartı üret (Pillow)
# ----------------------------------------------------------
def gradient_kart(metin, boyut, idx, path):
    from PIL import Image, ImageDraw, ImageFont
    W, H = boyut
    img = Image.new("RGB", (W, H))
    # koyu degrade arkaplan (indekse göre ton değişir)
    tonlar = [(18,26,48),(30,20,44),(12,32,38),(40,26,22),(22,22,40)]
    c1 = tonlar[idx % len(tonlar)]
    c2 = tuple(max(0, v-14) for v in c1)
    for y in range(H):
        r = y / H
        col = tuple(int(c1[i]*(1-r)+c2[i]*r) for i in range(3))
        ImageDraw.Draw(img).line([(0,y),(W,y)], fill=col)
    d = ImageDraw.Draw(img)
    # font
    try:
        fs = int(H*0.055)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", fs)
    except Exception:
        font = ImageFont.load_default()
    # metni sar
    kelimeler = metin.split()
    satirlar, cur = [], ""
    maxw = W*0.82
    for k in kelimeler:
        test = (cur+" "+k).strip()
        if d.textlength(test, font=font) <= maxw:
            cur = test
        else:
            satirlar.append(cur); cur = k
    if cur: satirlar.append(cur)
    satirlar = satirlar[:6]
    lh = int(fs*1.35)
    ty = (H - lh*len(satirlar))//2
    for ln in satirlar:
        w = d.textlength(ln, font=font)
        d.text(((W-w)//2, ty), ln, font=font, fill=(240,240,245))
        ty += lh
    # ince alt vurgu çizgisi
    d.rectangle([W*0.35, H*0.5+lh*len(satirlar)*0.0, W*0.65, H*0.5+3], fill=(200,180,90))
    img.save(path, quality=90)

def gorselleri_hazirla(cumleler, boyut, tmp):
    mevcut = sorted(glob.glob(os.path.join(CONFIG["assets_dir"], "*.jpg")) +
                    glob.glob(os.path.join(CONFIG["assets_dir"], "*.jpeg")) +
                    glob.glob(os.path.join(CONFIG["assets_dir"], "*.png")))
    paths = []
    if mevcut:
        for i, src in enumerate(mevcut):
            dst = os.path.join(tmp, f"img_{i:03d}.jpg")
            _resize_cover(src, boyut, dst)
            paths.append(dst)
    else:
        # her ~2 cümlede bir kart
        gruplar = [" ".join(cumleler[i:i+2]) for i in range(0, len(cumleler), 2)]
        gruplar = gruplar or ["Video"]
        for i, g in enumerate(gruplar):
            dst = os.path.join(tmp, f"card_{i:03d}.jpg")
            gradient_kart(g, boyut, i, dst)
            paths.append(dst)
    return paths

def _resize_cover(src, boyut, dst):
    from PIL import Image
    W, H = boyut
    im = Image.open(src).convert("RGB")
    iw, ih = im.size
    scale = max(W/iw, H/ih)
    nw, nh = int(iw*scale), int(ih*scale)
    im = im.resize((nw, nh), Image.LANCZOS)
    left, top = (nw-W)//2, (nh-H)//2
    im = im.crop((left, top, left+W, top+H))
    im.save(dst, quality=90)

# ----------------------------------------------------------
# 5. FFMPEG İLE BİRLEŞTİRME
#    Ken Burns (yavaş zoom) + alt yazı gömme + ses
# ----------------------------------------------------------
# ----------------------------------------------------------
# AI GÖRSEL ÜRETİMİ (Pollinations — ücretsiz, anahtar gerektirmez)
# Her sahne için senaryoya uygun sevimli çocuk çizimi üretir.
# Başarısız olursa degrade karta düşer (video asla boş kalmaz).
# ----------------------------------------------------------
def gorsel_uret_ai(prompt, boyut, idx, path, cocuk=True, stil_ad="foto"):
    import urllib.parse, urllib.request
    W, H = boyut
    if cocuk:
        stil = ("children's book illustration, cute, colorful, cartoon, friendly, "
                "soft lighting, simple, no text")
    elif stil_ad == "illustrasyon":
        # Veritasium/editoryal animasyon tarzı: elle çizilmiş his
        stil = ("stylized editorial illustration, digital painting, painterly artwork, "
                "muted warm color palette, dramatic cinematic lighting, detailed character art, "
                "film still composition, hand drawn animation style, no text, no watermark")
    else:
        stil = ("professional photograph, photorealistic, cinematic, realistic, "
                "high detail, dramatic lighting, shallow depth of field, 4k, no text, no watermark")
    tam = f"{prompt}, {stil}"
    q = urllib.parse.quote(tam)
    model = "flux" if not cocuk else "flux"
    url = (f"https://image.pollinations.ai/prompt/{q}"
           f"?width={W}&height={H}&nologo=true&model={model}&seed={1000+idx}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "yt-otomasyon"})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
        ham = path + ".raw"
        with open(ham, "wb") as f:
            f.write(data)
        _resize_cover(ham, boyut, path)
        os.remove(ham)
        return True
    except Exception as e:
        print(f"      [görsel {idx} AI hatası, karta düşülüyor: {e}]")
        gradient_kart(prompt[:80], boyut, idx, path)
        return False


def _keys():
    """Tek secret (GEMINI_API_KEY yuvası) içinde JSON: {"pexels":..,"eleven":..}.
    Eski düz string ise pexels kabul edilir."""
    raw = (os.environ.get("YT_KEYS") or os.environ.get("GEMINI_API_KEY", "")).strip()
    try:
        d = json.loads(raw)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    return {"pexels": raw}


def _pexels_key():
    return (os.environ.get("PEXELS_API_KEY") or _keys().get("pexels", "")).strip()


def _google_key():
    return (os.environ.get("GOOGLE_TTS_KEY") or _keys().get("google", "")).strip()


def _google_seslendir(text, mp3_path):
    """Google Cloud TTS (nöral Türkçe) + kelime zamanlaması (SSML mark timepoints)."""
    import urllib.request, urllib.error, base64 as _b64, html
    key = _google_key()
    if not key:
        raise RuntimeError("Google TTS anahtarı yok")
    voice = os.environ.get("GOOGLE_TTS_VOICE", "").strip() or "tr-TR-Wavenet-E"
    words = text.split()
    ssml = "<speak>" + " ".join(f'<mark name="{i}"/>{html.escape(w)}'
                                for i, w in enumerate(words)) + "</speak>"
    body = {"input": {"ssml": ssml},
            "voice": {"languageCode": "tr-TR", "name": voice},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": 1.05, "pitch": 0.0},
            "enableTimePointing": ["SSML_MARK"]}
    url = f"https://texttospeech.googleapis.com/v1beta1/text:synthesize?key={key}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0 (compatible; ytbot/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as he:
        raise RuntimeError(f"{he.code}: {he.read().decode()[:450]}")
    with open(mp3_path, "wb") as f:
        f.write(_b64.b64decode(d["audioContent"]))
    dur = sure_al(mp3_path)
    tps = sorted(d.get("timepoints", []), key=lambda t: int(t["markName"]))
    boundaries = []
    for i, w in enumerate(words):
        s = tps[i]["timeSeconds"] if i < len(tps) else i * dur / max(1, len(words))
        e = tps[i + 1]["timeSeconds"] if i + 1 < len(tps) else dur
        boundaries.append({"start": s, "dur": max(0.05, e - s), "text": w})
    return boundaries


def _eleven_key():
    return (os.environ.get("ELEVEN_API_KEY") or _keys().get("eleven", "")).strip()


def _eleven_seslendir(text, mp3_path):
    """ElevenLabs ile gerçekçi seslendirme + kelime zamanlaması (alt yazı senkronu)."""
    import urllib.request, urllib.error, base64 as _b64
    key = _eleven_key()
    if not key:
        raise RuntimeError("ElevenLabs anahtarı yok")
    voice_id = os.environ.get("ELEVEN_VOICE_ID", "").strip() or "pNInz6obpgDQGcFmaJgB"  # Adam (tok/derin erkek)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
    body = {"text": text, "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8,
                               "style": 0.2, "use_speaker_boost": True}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as he:
        raise RuntimeError(f"{he.code}: {he.read().decode()[:200]}")
    with open(mp3_path, "wb") as f:
        f.write(_b64.b64decode(d["audio_base64"]))
    al = d.get("alignment") or d.get("normalized_alignment") or {}
    chars = al.get("characters", [])
    st = al.get("character_start_times_seconds", [])
    en = al.get("character_end_times_seconds", [])
    boundaries, cur, ws, we = [], "", None, None
    for ch, s, e in zip(chars, st, en):
        if ch.isspace():
            if cur:
                boundaries.append({"start": ws, "dur": max(0.05, we - ws), "text": cur})
                cur, ws = "", None
        else:
            if not cur:
                ws = s
            cur += ch; we = e
    if cur:
        boundaries.append({"start": ws, "dur": max(0.05, we - ws), "text": cur})
    return boundaries


def stok_video_ara(query, boyut, path, dikey=True):
    """Pexels'ten konuya uygun gerçek stok video indirir. Başarısızsa None."""
    import urllib.parse, urllib.request
    key = _pexels_key()
    if not key:
        return None
    try:
        q = " ".join(query.split()[:4]) or query
        url = ("https://api.pexels.com/videos/search?query=" + urllib.parse.quote(q)
               + "&per_page=8&orientation=" + ("portrait" if dikey else "landscape"))
        req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "Mozilla/5.0 (compatible; ytbot/1.0)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode())
        vids = d.get("videos", [])
        print(f"      [Pexels: {len(vids)} sonuç -> '{q}']")
        for vid in vids:
            files = [f for f in vid.get("video_files", []) if f.get("link")]
            files.sort(key=lambda f: abs((f.get("width") or 0) - boyut[0]))
            for f in files:
                try:
                    dreq = urllib.request.Request(
                        f["link"], headers={"User-Agent": "Mozilla/5.0 (compatible; ytbot/1.0)"})
                    with urllib.request.urlopen(dreq, timeout=90) as resp, open(path, "wb") as out:
                        out.write(resp.read())
                    if os.path.getsize(path) > 10000:
                        return path
                except Exception:
                    continue
        return None
    except urllib.error.HTTPError as he:
        print(f"      [Pexels {he.code}: {he.read().decode()[:150]}]")
        return None
    except Exception as e:
        print(f"      [Pexels hata: {str(e)[:80]}]")
        return None


def sahne_gorselleri_hazirla(sahneler, cumleler, boyut, tmp, cocuk=True, stil="stok"):
    """Her sahne için önce gerçek stok video (Pexels), yoksa fotogerçekçi AI görseli.
    ('video', yol) veya ('image', yol) listesi döndürür."""
    if sahneler:
        prompts = [s.get("gorsel") or s.get("metin") or "" for s in sahneler if s]
    else:
        prompts = [" ".join(cumleler[i:i+2]) for i in range(0, len(cumleler), 2)]
    prompts = [p for p in prompts if p.strip()] or ["colorful scene"]
    dikey = boyut[1] > boyut[0]
    gorseller = []
    for i, p in enumerate(prompts):
        vpath = os.path.join(tmp, f"sahne_{i:03d}.mp4")
        if stil == "stok" and not cocuk and stok_video_ara(p, boyut, vpath, dikey=dikey):
            gorseller.append(("video", vpath))
            print(f"      Sahne {i+1}/{len(prompts)}: gerçek stok video ✓")
        else:
            ipath = os.path.join(tmp, f"sahne_{i:03d}.jpg")
            gorsel_uret_ai(p, boyut, i, ipath, cocuk=cocuk, stil_ad=stil)
            gorseller.append(("image", ipath))
            print(f"      Sahne {i+1}/{len(prompts)}: AI görseli ({stil})")
    return gorseller


# ----------------------------------------------------------
# PROFESYONEL KEN BURNS: sahne başına farklı kamera hareketi
# (zoom in/out, sola/sağa/yukarı/aşağı kaydırma, diyagonal).
# Titremeyi önlemek için görsel önce büyütülür (sub-pixel akış).
# ----------------------------------------------------------
def _ken_burns_vf(i, W, H, frames, fps):
    """i. sahne için akıcı, çeşitlendirilmiş bir kamera hareketi filtresi üretir."""
    d = max(int(frames), 1)
    # merkez konumlandırma (zoom değişince görsel ortada kalsın)
    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"
    # 7 farklı sinematik hareket; sahneler arasında dönüşümlü kullanılır
    hareketler = [
        (f"1.0+0.26*on/{d}", cx, cy),                              # yavaş zoom-in (merkez)
        (f"1.26-0.26*on/{d}", cx, cy),                             # yavaş zoom-out (nefes alma)
        ("1.16", f"(iw-iw/zoom)*on/{d}", cy),                      # sağa kaydırma
        ("1.16", f"(iw-iw/zoom)*(1-on/{d})", cy),                  # sola kaydırma
        ("1.16", cx, f"(ih-ih/zoom)*(1-on/{d})"),                  # yukarı kaydırma
        ("1.16", cx, f"(ih-ih/zoom)*on/{d}"),                      # aşağı kaydırma
        (f"1.0+0.22*on/{d}", f"(iw-iw/zoom)*on/{d}",              # zoom-in + diyagonal
         f"(ih-ih/zoom)*on/{d}"),
    ]
    z, x, y = hareketler[i % len(hareketler)]
    # 3x ön-büyütme -> zoompan tam-piksel yuvarlamasından doğan titreşimi yok eder
    presc = "scale=iw*3:ih*3:flags=lanczos"
    zp = (f"zoompan=z='{z}':x='{x}':y='{y}':"
          f"d={d}:s={W}x{H}:fps={fps}")
    return f"{presc},{zp},format=yuv420p"


def video_uret_animasyon(gorseller, mp3, ass, cikti, boyut, fps, gecis=0.45,
                         max_sahne_sn=5.0):
    import math
    W, H = boyut
    toplam = sure_al(mp3)
    # normalize: düz string -> ("image", yol)
    gorseller = [g if isinstance(g, (tuple, list)) else ("image", g) for g in gorseller]
    n0 = len(gorseller) or 1
    # Gerçek videolar zaten hareketli; görsellerde tempo için gerekiyorsa çoğalt.
    seg = max(n0, math.ceil(toplam / max_sahne_sn))
    gorseller = [gorseller[i % n0] for i in range(seg)]
    n = len(gorseller)
    D = (toplam + (n - 1) * gecis) / n if n > 0 else toplam
    D = max(D, gecis + 0.6)
    frames = int(D * fps)
    tmp = tempfile.mkdtemp()
    klipler = []
    for i, (tip, g) in enumerate(gorseller):
        seg = os.path.join(tmp, f"k{i}.mp4")
        if tip == "video":
            off = (i * 1.7) % 4.0   # tekrar olursa farklı an
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},fps={fps},format=yuv420p")
            subprocess.run(["ffmpeg", "-y", "-ss", f"{off:.1f}", "-stream_loop", "-1",
                            "-i", g, "-t", f"{D:.3f}", "-vf", vf, "-r", str(fps), "-an",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", seg],
                           check=True, capture_output=True)
        else:
            vf = _ken_burns_vf(i, W, H, frames, fps)
            subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", g, "-t", f"{D:.3f}",
                            "-vf", vf, "-r", str(fps),
                            "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "22", seg], check=True, capture_output=True)
        klipler.append(seg)

    # çeşitli sinematik geçişler (sahneler arasında dönüşümlü)
    GECISLER = ["smoothleft", "smoothright", "fade", "slideup",
                "circleopen", "wiperight", "dissolve", "smoothup"]

    tmpv = os.path.join(tmp, "gorsel.mp4")
    if n == 1:
        shutil.copy(klipler[0], tmpv)
    else:
        inputs = []
        for k in klipler:
            inputs += ["-i", k]
        fc = ""
        prev = "0:v"
        for i in range(1, n):
            off = i * (D - gecis)
            out = f"v{i}"
            trans = GECISLER[(i - 1) % len(GECISLER)]
            fc += (f"[{prev}][{i}:v]xfade=transition={trans}:"
                   f"duration={gecis}:offset={off:.3f}[{out}];")
            prev = out
        fc = fc.rstrip(";")
        subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", fc,
                        "-map", f"[{prev}]", "-r", str(fps), "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                        tmpv], check=True, capture_output=True)

    # alt yazı göm + hafif sinematik renk düzeltmesi (canlılık + yumuşak vinyet) + ses
    ass_esc = ass.replace("\\", "/").replace(":", "\\:")
    grade = "eq=saturation=1.12:contrast=1.04:brightness=0.01,vignette=angle=PI/6"
    subprocess.run(["ffmpeg", "-y", "-i", tmpv, "-i", mp3,
                    "-vf", f"subtitles='{ass_esc}',{grade}",
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", cikti],
                   check=True, capture_output=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return toplam


def sure_al(mp3):
    out = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                          "-of","default=noprint_wrappers=1:nokey=1", mp3],
                         capture_output=True, text=True)
    return float(out.stdout.strip())

def video_uret(gorseller, mp3, ass, cikti, boyut, fps):
    W, H = boyut
    toplam = sure_al(mp3)
    n = len(gorseller)
    sure_her = max(2.0, toplam / n)
    tmp = tempfile.mkdtemp()
    parcalar = []
    for i, g in enumerate(gorseller):
        seg = os.path.join(tmp, f"seg_{i:03d}.mp4")
        d = sure_her
        frames = int(d*fps)
        # yavaş zoom-in (Ken Burns)
        zoom = f"zoompan=z='min(zoom+0.0008,1.12)':d={frames}:s={W}x{H}:fps={fps}"
        subprocess.run([
            "ffmpeg","-y","-loop","1","-i",g,"-t",f"{d:.3f}",
            "-vf", f"scale={W}:{H},{zoom},format=yuv420p",
            "-r",str(fps),"-c:v","libx264","-preset","veryfast","-crf","23",
            seg
        ], check=True, capture_output=True)
        parcalar.append(seg)
    # concat
    liste = os.path.join(tmp, "list.txt")
    with open(liste,"w") as f:
        for p in parcalar:
            f.write(f"file '{p}'\n")
    birlesik = os.path.join(tmp, "video_nosub.mp4")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",liste,
                    "-c","copy", birlesik], check=True, capture_output=True)
    # alt yazı göm + ses ekle
    ass_esc = ass.replace("\\","/").replace(":","\\:")
    subprocess.run([
        "ffmpeg","-y","-i",birlesik,"-i",mp3,
        "-vf", f"subtitles='{ass_esc}'",
        "-map","0:v","-map","1:a",
        "-c:v","libx264","-preset","veryfast","-crf","20",
        "-c:a","aac","-b:a","192k","-shortest",
        cikti
    ], check=True, capture_output=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return toplam

# ----------------------------------------------------------
# ANA AKIŞ
# ----------------------------------------------------------
def uret_video(script_path, cikti, ses="kadin", dikey=False, hiz="+0%",
               sahneler=None, animasyon=True, cocuk=True, tonlama="+0Hz",
               gorsel_stil="stok", kanca=None):
    """Orkestratör tarafından çağrılır: script -> mp4.
    sahneler verilirse (Gemini'den), her sahne için AI görsel üretir ve
    Ken Burns + çapraz geçişle animasyonlu montaj yapar.
    tonlama: ses tonu (örn '-12Hz' daha tok/derin erkek sesi)."""
    boyut = CONFIG["dikey"] if dikey else CONFIG["yatay"]
    voice = CONFIG["sesler"][ses]
    text, cumleler = metni_oku(script_path)
    tmp = tempfile.mkdtemp()
    mp3 = os.path.join(tmp, "narration.mp3")
    _gk=_google_key(); _pk=_pexels_key()
    print(f"      [anahtar: google={_gk[:6]}..len{len(_gk)}, pexels={_pk[:6]}..len{len(_pk)}]")
    boundaries = None
    if _google_key():
        try:
            boundaries = _google_seslendir(text, mp3)
            print("      Ses: Google TTS (nöral Türkçe)")
        except Exception as e:
            print(f"      Google TTS hata: {str(e)[:400]}")
            boundaries = None
    if boundaries is None and _eleven_key():
        try:
            boundaries = _eleven_seslendir(text, mp3)
            print("      Ses: ElevenLabs (gerçekçi insan sesi)")
        except Exception as e:
            print(f"      ElevenLabs hata ({str(e)[:90]}), edge-tts'e dönülüyor")
            boundaries = None
    if boundaries is None:
        try:
            boundaries = seslendir_prosodik(cumleler, voice, hiz, mp3, pitch=tonlama)
            print("      Ses: prosodik mod (cümle bazlı vurgu/tonlama)")
        except Exception as e:
            print(f"      Prosodik mod başarısız ({e}), tek parça seslendirmeye dönülüyor")
            boundaries = seslendir(text, voice, hiz, mp3, pitch=tonlama)
    cues = cue_olustur(boundaries, CONFIG["altyazi_max_kelime"], CONFIG["altyazi_max_sure"])
    ass = os.path.join(tmp, "sub.ass")
    ass_yaz(cues, ass, CONFIG, dikey, kanca=kanca)
    os.makedirs(os.path.dirname(cikti) or ".", exist_ok=True)
    if animasyon:
        gorseller = sahne_gorselleri_hazirla(sahneler, cumleler, boyut, tmp,
                                             cocuk=cocuk, stil=gorsel_stil)
        video_uret_animasyon(gorseller, mp3, ass, cikti, boyut, CONFIG["fps"])
    else:
        gorseller = gorselleri_hazirla(cumleler, boyut, tmp)
        video_uret(gorseller, mp3, ass, cikti, boyut, CONFIG["fps"])
    shutil.rmtree(tmp, ignore_errors=True)
    return cikti


def main():
    ap = argparse.ArgumentParser(description="Faceless YouTube video üretici")
    ap.add_argument("--script", required=True, help="Metin dosyası (.txt)")
    ap.add_argument("--ses", default=CONFIG["varsayilan_ses"], choices=["kadin","erkek"])
    ap.add_argument("--dikey", action="store_true", help="9:16 Shorts formatı")
    ap.add_argument("--hiz", default=CONFIG["konusma_hizi"], help="örn +10%%")
    args = ap.parse_args()

    boyut = CONFIG["dikey"] if args.dikey else CONFIG["yatay"]
    voice = CONFIG["sesler"][args.ses]
    os.makedirs(CONFIG["output_dir"], exist_ok=True)
    os.makedirs(CONFIG["assets_dir"], exist_ok=True)
    ad = os.path.splitext(os.path.basename(args.script))[0]

    print(f"[1/5] Metin okunuyor: {args.script}")
    text, cumleler = metni_oku(args.script)
    print(f"      {len(cumleler)} cümle, ~{len(text.split())} kelime")

    tmp = tempfile.mkdtemp()
    mp3 = os.path.join(tmp, "narration.mp3")
    print(f"[2/5] Seslendirme ({voice}) ...")
    boundaries = seslendir(text, voice, args.hiz, mp3)
    cues = cue_olustur(boundaries, CONFIG["altyazi_max_kelime"], CONFIG["altyazi_max_sure"])
    print(f"      {len(cues)} alt yazı satırı")

    ass = os.path.join(tmp, "sub.ass")
    ass_yaz(cues, ass, CONFIG, args.dikey)

    print(f"[3/5] Görseller hazırlanıyor ...")
    gorseller = gorselleri_hazirla(cumleler, boyut, tmp)
    print(f"      {len(gorseller)} görsel")

    cikti = os.path.join(CONFIG["output_dir"], f"{ad}.mp4")
    print(f"[4/5] Video birleştiriliyor (FFmpeg) ...")
    sure = video_uret(gorseller, mp3, ass, cikti, boyut, CONFIG["fps"])

    print(f"[5/5] TAMAM ✓  ->  {cikti}  ({sure:.0f} sn)")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()
