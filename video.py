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
        "punto_dikey": 19,
        "renk": "&H00FFFFFF",       # beyaz
        "kenar_renk": "&H00000000", # siyah kenarlık
        "kenar_kalinlik": 4,
        "alt_bosluk": 560,   # Shorts: alttaki ~500px UI ile kapali
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
# ----------------------------------------------------------
# SES NORMALİZASYONU — TTS'in takıldığı sayı/yüzde/kısaltmaları
# seslendirmeden ÖNCE Türkçe okunuşa çevirir (telaffuz düzelir).
# Altyazı da bu metinden üretildiği için ses ile senkron kalır.
# ----------------------------------------------------------
_SAYI_BIR = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_SAYI_ON  = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
_SAYI_GRUP = ["", " bin", " milyon", " milyar", " trilyon", " katrilyon"]

def _uc_haneli_yazi(n):
    y, k = divmod(n, 100)
    o, b = divmod(k, 10)
    p = []
    if y:
        p.append("yüz" if y == 1 else _SAYI_BIR[y] + " yüz")
    if o:
        p.append(_SAYI_ON[o])
    if b:
        p.append(_SAYI_BIR[b])
    return " ".join(p)

def _sayi_yaziya(n):
    """Tam sayıyı Türkçe okunuşuna çevirir (0..katrilyon)."""
    if n == 0:
        return "sıfır"
    parca = []; grup = 0
    while n > 0 and grup < len(_SAYI_GRUP):
        n, r = divmod(n, 1000)
        if r:
            s = _uc_haneli_yazi(r)
            if grup == 1 and r == 1:   # "bin" ("bir bin" değil)
                s = ""
            parca.append((s + _SAYI_GRUP[grup]).strip())
        grup += 1
    return " ".join(reversed(parca)).strip()

# Sıra sayısı (ordinal) okunuşu: son sözcüğe Türkçe sıra eki eklenir.
_ORDINAL = {
    "bir": "birinci", "iki": "ikinci", "üç": "üçüncü", "dört": "dördüncü",
    "beş": "beşinci", "altı": "altıncı", "yedi": "yedinci", "sekiz": "sekizinci",
    "dokuz": "dokuzuncu", "on": "onuncu", "yirmi": "yirminci", "otuz": "otuzuncu",
    "kırk": "kırkıncı", "elli": "ellinci", "altmış": "altmışıncı",
    "yetmiş": "yetmişinci", "seksen": "sekseninci", "doksan": "doksanıncı",
    "yüz": "yüzüncü", "bin": "bininci", "milyon": "milyonuncu", "milyar": "milyarıncı",
}

def _sayi_sirali(n):
    """Tam sayının Türkçe SIRA sayısı okunuşu: 19 -> 'on dokuzuncu', 2 -> 'ikinci'."""
    parca = _sayi_yaziya(n).split()
    if parca:
        parca[-1] = _ORDINAL.get(parca[-1], parca[-1] + "inci")
    return " ".join(parca)

# Sık sorun çıkaran kısaltma/yabancı sözcükler -> Türkçe okunuş.
_SES_KISALTMA = {
    r"\bWi-?Fi\b": "vayfay",
    r"\bWIFI\b": "vayfay",
}

def _ses_normalize(metin):
    """Sayı, yüzde ve bazı kısaltmaları TTS'in doğru telaffuz edeceği hale getirir."""
    if not metin:
        return metin
    m = metin
    m = re.sub(r"%\s*(\d+)", r"yüzde \1", m)                 # %95 -> yüzde 95
    # saat: 19:00 -> "on dokuz", 19:30 -> "on dokuz otuz"  (iki nokta okunmasın)
    def _saat_rep(x):
        h, dk = int(x.group(1)), int(x.group(2))
        return _sayi_yaziya(h) if dk == 0 else f"{_sayi_yaziya(h)} {_sayi_yaziya(dk)}"
    m = re.sub(r"\b(\d{1,2}):([0-5]\d)\b", _saat_rep, m)
    # sıra sayısı: "19. filo" -> "on dokuzuncu filo" (nokta + boşluk + harf gelirse).
    # Cümle sonundaki sayı (19. <BÜYÜK harf/çıkış>) ordinal sayılmaz; sadece devam
    # eden sözcük varsa çevrilir. ≤3 haneyle sınırlı (yıl gibi 4 haneler hariç).
    m = re.sub(r"\b(\d{1,3})\.(?=\s+[^\W\d_])",
               lambda x: _sayi_sirali(int(x.group(1))), m)
    m = re.sub(r"(\d+),(\d+)", r"\1 virgül \2", m)           # 13,8 -> 13 virgül 8
    m = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", m)               # 1.000.000 -> 1000000
    m = re.sub(r"\d+", lambda x: _sayi_yaziya(int(x.group(0))), m)  # sayı -> yazı
    for pat, rep in _SES_KISALTMA.items():
        m = re.sub(pat, rep, m, flags=re.IGNORECASE)
    return m


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
Style: Def,{a['font']},{punto*4},{a['renk']},{a['kenar_renk']},&H88000000,-1,{a['kenar_kalinlik']},1,2,80,80,{a['alt_bosluk'] if dikey else 90}
Style: Kanca,{a['font']},{int(punto*4*1.80)},&H0000DDFF,&H00000000,&H00000000,-1,8,3,8,60,60,{220 if dikey else 80}
Style: Abone,{a['font']},{int(punto*4*0.98)},&H0000DDFF,&H00000000,&H00000000,-1,6,3,8,60,60,{640 if dikey else 200}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(head)
        if kanca:
            k = str(kanca).strip().replace("\n", " ")
            # GÜÇLÜ KANCA: ilk ~3.2sn, büyük + "pop" giriş animasyonu (dikkat çeker).
            # Pop: 118%'den 100%'e hızlı otur, sonra hafif nefes -> gözü ilk saniyede tutar.
            pop = ("\\t(0,160,\\fscx118\\fscy118)\\t(160,430,\\fscx100\\fscy100)"
                   "\\t(430,900,\\fscx105\\fscy105)\\t(900,1400,\\fscx100\\fscy100)")
            f.write(f"Dialogue: 1,0:00:00.00,0:00:03.20,Kanca,,0,0,0,,"
                    f"{{\\fad(80,300){pop}}}{k}\n")
        # Her alt yazı satırı küçük bir 'pop' ile girer (110%->100%, ~0.24sn) +
        # yumuşak fade -> enerjik/modern Shorts hissi, okunurluğu bozmadan.
        pop_c = ("\\fad(50,50)\\t(0,110,\\fscx110\\fscy110)"
                 "\\t(110,240,\\fscx100\\fscy100)")
        for c in cues:
            txt = c["text"].replace("\n", " ")
            f.write(f"Dialogue: 0,{_ass_zaman(c['start'])},{_ass_zaman(c['end'])},Def,,0,0,0,,"
                    f"{{{pop_c}}}{txt}\n")
        # --- ABONE OL: parlayan sarı buton (orta + son), seslendirmeye dokunmaz ---
        if cues:
            son = cues[-1]["end"]
            orta = son / 2.0
            btn = "\u25B6 ABONE OL  \u2022  her ak\u015fam yeni tuzak"
            # tek yumuşak "nefes": 100->108->100 (yumuşak, titremez)
            puls = "\\t(0,500,\\fscx108\\fscy108)\\t(500,1000,\\fscx100\\fscy100)\\t(1000,1500,\\fscx108\\fscy108)\\t(1500,2000,\\fscx100\\fscy100)"
            # BAS (erken): hook biter bitmez ~2.9sn belirir, orta CTA'ya carpmaz.
            # Amac: izleyici ilk saniyelerde abone ipucunu gorsun -> donusum artar.
            e_bas = 2.9
            e_bit = min(5.6, orta - 1.3, son - 0.5)
            if e_bit - e_bas >= 0.8:
                f.write(f"Dialogue: 2,{_ass_zaman(e_bas)},{_ass_zaman(e_bit)},Abone,,0,0,0,,"
                        f"{{\\fad(200,200){puls}}}{btn}\n")
            # ORTA: 2.2sn görünür
            o_bas, o_bit = orta - 1.1, orta + 1.1
            f.write(f"Dialogue: 2,{_ass_zaman(o_bas)},{_ass_zaman(o_bit)},Abone,,0,0,0,,"
                    f"{{\\fad(250,250){puls}}}{btn}\n")
            # SON: 2.6sn görünür
            s_bas, s_bit = max(o_bit + 0.4, son - 2.6), son + 0.4
            f.write(f"Dialogue: 2,{_ass_zaman(s_bas)},{_ass_zaman(s_bit)},Abone,,0,0,0,,"
                    f"{{\\fad(250,150){puls}}}{btn}\n")

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
    import base64 as _b64
    ar = "16:9" if W > H else ("9:16" if H > W else "1:1")
    key = _google_key()
    def _save(b):
        ham = path + ".raw"
        with open(ham, "wb") as f:
            f.write(b)
        _resize_cover(ham, boyut, path)
        os.remove(ham)
        return True
    denemeler = [("imagen-4.0-generate-001", "imagen"),
                 ("imagen-3.0-generate-002", "imagen"),
                 ("gemini-2.5-flash-image", "gemini"),
                 ("gemini-2.0-flash-preview-image-generation", "gemini")]
    for model, kind in denemeler:
        try:
            if kind == "imagen":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict?key={key}"
                body = {"instances": [{"prompt": tam}],
                        "parameters": {"sampleCount": 1, "aspectRatio": ar}}
            else:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                body = {"contents": [{"parts": [{"text": "Generate an image: " + tam}]}],
                        "generationConfig": {"responseModalities": ["IMAGE"]}}
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "User-Agent": "ytbot"})
            with urllib.request.urlopen(req, timeout=150) as r:
                d = json.loads(r.read().decode())
            b64 = None
            if kind == "imagen":
                preds = d.get("predictions") or []
                if preds:
                    b64 = preds[0].get("bytesBase64Encoded")
            else:
                for cand in d.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        if part.get("inlineData"):
                            b64 = part["inlineData"]["data"]; break
                    if b64: break
            if b64:
                print(f"      [görsel {idx}: {model} ✓]")
                return _save(_b64.b64decode(b64))
            print(f"      [görsel {idx} {model}: görsel yok]")
        except Exception as e:
            print(f"      [görsel {idx} {model} hata: {str(e)[:90]}]")
    print(f"      [görsel {idx}: tüm AI modelleri başarısız, karta düşülüyor]")
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


def _pixabay_key():
    return (os.environ.get("PIXABAY_API_KEY") or _keys().get("pixabay", "")).strip()


def _google_key():
    return (os.environ.get("GOOGLE_TTS_KEY") or _keys().get("google", "")).strip()


def _google_tts_uzun(words, voice, hizi, key, mp3_path):
    """Uzun metni <5000-bayt SSML parcalarina bolerek Google TTS ile seslendirir;
    ses parcalarini birlestirir, kelime timepoint'lerini kaydirarak birlestirir (altyazi senkronu)."""
    import urllib.request, urllib.error, base64 as _b64, html
    def _ssml(ws):
        return "<speak>" + " ".join(f'<mark name="{j}"/>{html.escape(w)}' for j, w in enumerate(ws)) + "</speak>"
    parcalar, cur = [], []
    for w in words:
        if cur and len(_ssml(cur + [w]).encode("utf-8")) > 4800:
            parcalar.append(cur); cur = [w]
        else:
            cur.append(w)
    if cur:
        parcalar.append(cur)
    tmp = tempfile.mkdtemp(); segler = []; boundaries = []; offset = 0.0
    url = f"https://texttospeech.googleapis.com/v1beta1/text:synthesize?key={key}"
    for ci, ws in enumerate(parcalar):
        body = {"input": {"ssml": _ssml(ws)},
                "voice": {"languageCode": "tr-TR", "name": voice},
                "audioConfig": {"audioEncoding": "MP3", "speakingRate": hizi, "pitch": 0.0},
                "enableTimePointing": ["SSML_MARK"]}
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": "Mozilla/5.0 (compatible; ytbot/1.0)"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read().decode())
        except urllib.error.HTTPError as he:
            raise RuntimeError(f"{he.code}: {he.read().decode()[:300]}")
        seg = os.path.join(tmp, f"tts{ci:03d}.mp3")
        with open(seg, "wb") as f:
            f.write(_b64.b64decode(d["audioContent"]))
        dur = sure_al(seg); segler.append(seg)
        tps = sorted(d.get("timepoints", []), key=lambda t: int(t["markName"]))
        if tps:
            for j, w in enumerate(ws):
                s = tps[j]["timeSeconds"] if j < len(tps) else j * dur / max(1, len(ws))
                e = tps[j + 1]["timeSeconds"] if j + 1 < len(tps) else dur
                boundaries.append({"start": offset + s, "dur": max(0.05, e - s), "text": w})
        else:
            agir = [max(1, len(w)) + 1 for w in ws]; tot = float(sum(agir)) or 1.0; t = 0.0
            for w, a in zip(ws, agir):
                pay = dur * (a / tot)
                boundaries.append({"start": offset + t, "dur": max(0.05, pay), "text": w}); t += pay
        offset += dur
    # GAPLESS birleştirme: concat FİLTRESİ (parçaları PCM'e çözüp birleştirir) ->
    # MP3'leri '-c copy' ile eklemekteki birleşim noktası çıtırtısı OLMAZ.
    if len(segler) == 1:
        shutil.copy(segler[0], mp3_path)
    else:
        inputs = []
        for s in segler:
            inputs += ["-i", s]
        fc = "".join(f"[{i}:a]" for i in range(len(segler))) + f"concat=n={len(segler)}:v=0:a=1[a]"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", fc,
                        "-map", "[a]", "-c:a", "libmp3lame", "-q:a", "2", mp3_path], check=True)
    print(f"    Ses: {voice} (uzun metin {len(parcalar)} parca, gapless birlestirme)")
    return boundaries


def _google_seslendir(text, mp3_path):
    """Google Cloud TTS (nöral Türkçe) + kelime zamanlaması (SSML mark timepoints)."""
    import urllib.request, urllib.error, base64 as _b64, html
    key = _google_key()
    if not key:
        raise RuntimeError("Google TTS anahtarı yok")
    voice = os.environ.get("GOOGLE_TTS_VOICE", "").strip() or "tr-TR-Wavenet-E"
    words = text.split()
    hizi = float(os.environ.get("GOOGLE_TTS_RATE", "") or 1.0)  # normal hiz - netlik oncelik
    chirp = "Chirp" in voice
    if not chirp:
        _probe = "<speak>" + " ".join(f'<mark name="{i}"/>{html.escape(w)}' for i, w in enumerate(words)) + "</speak>"
        if len(_probe.encode("utf-8")) > 4800:
            return _google_tts_uzun(words, voice, hizi, key, mp3_path)  # UZUN: 5000-bayt sinirini asma
    if chirp:
        # Chirp3-HD: SSML/mark desteklemez -> duz metin, zamanlama orantili hesaplanir
        body = {"input": {"text": text},
                "voice": {"languageCode": "tr-TR", "name": voice},
                "audioConfig": {"audioEncoding": "MP3", "speakingRate": hizi}}
    else:
        ssml = "<speak>" + " ".join(f'<mark name="{i}"/>{html.escape(w)}'
                                    for i, w in enumerate(words)) + "</speak>"
        body = {"input": {"ssml": ssml},
                "voice": {"languageCode": "tr-TR", "name": voice},
                "audioConfig": {"audioEncoding": "MP3", "speakingRate": hizi, "pitch": 0.0},
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
    if tps:
        for i, w in enumerate(words):
            s = tps[i]["timeSeconds"] if i < len(tps) else i * dur / max(1, len(words))
            e = tps[i + 1]["timeSeconds"] if i + 1 < len(tps) else dur
            boundaries.append({"start": s, "dur": max(0.05, e - s), "text": w})
        print(f"    Ses: {voice} (kelime zamanlamasi: gercek timepoint)")
    else:
        # Chirp3-HD gibi timepoint vermeyen sesler: harf uzunluguna gore oranti
        agirlik = [max(1, len(w)) + 1 for w in words]   # +1 = kelime arasi bosluk
        toplam = float(sum(agirlik)) or 1.0
        t = 0.0
        for w, a in zip(words, agirlik):
            pay = dur * (a / toplam)
            boundaries.append({"start": t, "dur": max(0.05, pay), "text": w})
            t += pay
        print(f"    Ses: {voice} (kelime zamanlamasi: orantili hesap)")
    return boundaries


def _eleven_key():
    return (os.environ.get("ELEVEN_API_KEY") or os.environ.get("ELEVENLABS_API_KEY")
            or _keys().get("eleven", "")).strip()


def _eleven_seslendir(text, mp3_path, voice_id=None):
    """ElevenLabs ile gerçekçi seslendirme + kelime zamanlaması (alt yazı senkronu).
    voice_id verilirse o kullanilir (pipeline'a ozel ses); yoksa ELEVEN_VOICE_ID
    env'i, o da yoksa varsayilan ses."""
    import urllib.request, urllib.error, base64 as _b64
    key = _eleven_key()
    if not key:
        raise RuntimeError("ElevenLabs anahtarı yok")
    voice_id = (voice_id or "").strip() or os.environ.get("ELEVEN_VOICE_ID", "").strip() or "dDcfsSsiSzmphdMGCECb"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
    body = {"text": text, "model_id": "eleven_multilingual_v2",
            # Daha PÜRÜZSÜZ ses: speaker_boost kapalı + style=0 (tiz/cızırtı
            # artefaktlarını azaltır), stability biraz yüksek, similarity ölçülü.
            "voice_settings": {"stability": 0.50, "similarity_boost": 0.75,
                               "style": 0.0, "use_speaker_boost": False}}
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


def _indir(link, path):
    """Verilen linki path'e indirir; dosya makul boyuttaysa path döner, yoksa None."""
    import urllib.request
    try:
        dreq = urllib.request.Request(
            link, headers={"User-Agent": "Mozilla/5.0 (compatible; ytbot/1.0)"})
        with urllib.request.urlopen(dreq, timeout=90) as resp, open(path, "wb") as out:
            out.write(resp.read())
        if os.path.getsize(path) > 10000:
            return path
    except Exception:
        pass
    return None


def _pexels_adaylar(query, boyut, dikey=True):
    """Pexels'te arar; (toplam_sonuc, [indirme_url'leri], onizleme_gorsel_url) döndürür.
    Adaylar API'nin alaka sırasını korur; her video içinde hedef genişliğe en yakın
    çözünürlük öne gelir. Önizleme, en alakalı (ilk) klibin thumbnail'ıdır (vision için).
    Anahtar yoksa / hata olursa (0, [], None)."""
    import urllib.parse, urllib.request, urllib.error
    key = _pexels_key()
    if not key:
        return (0, [], None)
    try:
        q = " ".join(query.split()[:4]) or query
        url = ("https://api.pexels.com/videos/search?query=" + urllib.parse.quote(q)
               + "&per_page=8&orientation=" + ("portrait" if dikey else "landscape"))
        req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "Mozilla/5.0 (compatible; ytbot/1.0)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode())
        vids = d.get("videos", [])
        total = int(d.get("total_results") or 0)
        print(f"      [Pexels: {len(vids)} klip / ~{total} toplam -> '{q}']")
        onizleme = vids[0].get("image") if vids else None
        adaylar = []
        for vid in vids:  # API zaten alaka sırasında döndürür
            files = [f for f in vid.get("video_files", []) if f.get("link")]
            files.sort(key=lambda f: abs((f.get("width") or 0) - boyut[0]))
            adaylar += [f["link"] for f in files]
        return (total, adaylar, onizleme)
    except urllib.error.HTTPError as he:
        print(f"      [Pexels {he.code}: {he.read().decode()[:150]}]")
        return (0, [], None)
    except Exception as e:
        print(f"      [Pexels hata: {str(e)[:80]}]")
        return (0, [], None)


def _pixabay_adaylar(query, boyut, dikey=True):
    """Pixabay'de arar; (toplam_sonuc, [indirme_url'leri], onizleme_gorsel_url) döndürür.
    Yönelime (dikey/yatay) uyan hitler öne alınır; her hit içinde hedef genişliğe en yakın
    çözünürlük öne gelir. Önizleme, en alakalı (ilk) hit'in thumbnail'ıdır (vision için).
    Anahtar yoksa / hata olursa (0, [], None)."""
    import urllib.parse, urllib.request, urllib.error
    key = _pixabay_key()
    if not key:
        return (0, [], None)
    try:
        q = " ".join(query.split()[:4]) or query
        url = ("https://pixabay.com/api/videos/?key=" + urllib.parse.quote(key)
               + "&q=" + urllib.parse.quote(q) + "&per_page=12&safesearch=true")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ytbot/1.0)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode())
        hits = d.get("hits", [])
        total = int(d.get("total") or d.get("totalHits") or 0)
        print(f"      [Pixabay: {len(hits)} klip / ~{total} toplam -> '{q}']")

        def _yonelim_uyar(h):
            w = h.get("width") or 0; ht = h.get("height") or 0
            if not w or not ht:
                return True
            return (ht > w) if dikey else (w >= ht)
        # alaka sırasını koru, sadece yönelime uymayanları sona at (stable sort)
        hits = sorted(hits, key=lambda h: 0 if _yonelim_uyar(h) else 1)

        def _thumb(h):  # bir hit'in ilk mevcut thumbnail'ını bul
            for f in (h.get("videos") or {}).values():
                if isinstance(f, dict) and f.get("thumbnail"):
                    return f["thumbnail"]
            return None
        onizleme = _thumb(hits[0]) if hits else None
        adaylar = []
        for h in hits:
            files = [f for f in (h.get("videos") or {}).values()
                     if isinstance(f, dict) and f.get("url")]
            files.sort(key=lambda f: abs((f.get("width") or 0) - boyut[0]))
            adaylar += [f["url"] for f in files]
        return (total, adaylar, onizleme)
    except urllib.error.HTTPError as he:
        print(f"      [Pixabay {he.code}: {he.read().decode()[:150]}]")
        return (0, [], None)
    except Exception as e:
        print(f"      [Pixabay hata: {str(e)[:80]}]")
        return (0, [], None)


def pexels_video_ara(query, boyut, path, dikey=True):
    """Pexels'ten konuya uygun gerçek stok video indirir. Başarısızsa None."""
    _, adaylar, _ = _pexels_adaylar(query, boyut, dikey)
    for link in adaylar:
        if _indir(link, path):
            return path
    return None


def pixabay_video_ara(query, boyut, path, dikey=True):
    """Pixabay'den konuya uygun gerçek stok video indirir. Başarısızsa None."""
    _, adaylar, _ = _pixabay_adaylar(query, boyut, dikey)
    for link in adaylar:
        if _indir(link, path):
            return path
    return None


def _vision_kaynak_sec(metin, thumb_pexels, thumb_pixabay):
    """İki aday thumbnail'ı bir vision modeline (Gemini) gösterip sahne metnine hangisinin
    daha uygun olduğunu sorar. 'pexels' | 'pixabay' döndürür; anahtar yok / thumbnail yok /
    hata olursa None (çağıran taraf sayısal vekile düşer)."""
    import urllib.request, base64 as _b64
    key = _google_key()
    if not key or not thumb_pexels or not thumb_pixabay:
        return None

    def _resim(u):
        try:
            rq = urllib.request.Request(u, headers={"User-Agent": "ytbot"})
            with urllib.request.urlopen(rq, timeout=20) as r:
                return _b64.b64encode(r.read()).decode()
        except Exception:
            return None
    a = _resim(thumb_pexels); b = _resim(thumb_pixabay)
    if not a or not b:
        return None
    talimat = (
        "Bir video sahnesi icin stok gorsel seciyoruz. Sahne konusu: '"
        + (metin or "")[:200] + "'. Asagida iki aday gorsel var: birincisi A, ikincisi B. "
        "Hangisi bu sahne konusuna gorsel olarak daha uygun ve alakali? "
        "SADECE tek harf yaz: A veya B.")
    body = {"contents": [{"parts": [
        {"text": talimat},
        {"inlineData": {"mimeType": "image/jpeg", "data": a}},
        {"text": "A"},
        {"inlineData": {"mimeType": "image/jpeg", "data": b}},
        {"text": "B"},
    ]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 5}}
    for model in ("gemini-2.5-flash", "gemini-2.0-flash"):
        try:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
                   f":generateContent?key={key}")
            rq = urllib.request.Request(url, data=json.dumps(body).encode(),
                                        headers={"Content-Type": "application/json", "User-Agent": "ytbot"})
            with urllib.request.urlopen(rq, timeout=40) as r:
                d = json.loads(r.read().decode())
            metinler = []
            for cand in d.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    if part.get("text"):
                        metinler.append(part["text"])
            cevap = (" ".join(metinler)).strip().upper()
            if cevap.startswith("A") or cevap == "A":
                return "pexels"
            if cevap.startswith("B") or cevap == "B":
                return "pixabay"
        except Exception as e:
            print(f"      [vision {model} hata: {str(e)[:70]}]")
    return None


def stok_video_ara(query, boyut, path, dikey=True, oncelik=None):
    """Her iki kaynağa da bakar ve KONUYA en uygun kaynağı seçer. Seçim önceliği:
    1) VISION: iki kaynağın en alakalı klibinin thumbnail'ını bir görüntü-anlama modeline
       (Gemini) gösterip sahne metnine hangisinin görsel olarak daha uygun olduğunu sorar.
    2) SAYISAL VEKİL: vision yoksa/başarısızsa, o sorgu için hangi kaynakta daha çok video
       varsa (daha iyi kapsam) onu önceler.
    Seçilen kaynakta indirme başarısızsa diğeri devreye girer. Zorunlu bir oran yoktur.
    ('pexels'|'pixabay', path) veya None. ('oncelik' verilirse yalnızca sayısal eşitlikte
    tercih olarak kullanılır.)"""
    px_total, px_adaylar, px_thumb = _pexels_adaylar(query, boyut, dikey)
    pb_total, pb_adaylar, pb_thumb = _pixabay_adaylar(query, boyut, dikey)
    sira = None
    # 1) Vision: yalnızca iki kaynakta da aday + thumbnail varsa denenir
    if px_adaylar and pb_adaylar:
        secim = _vision_kaynak_sec(query, px_thumb, pb_thumb)
        if secim:
            sira = ("pexels", "pixabay") if secim == "pexels" else ("pixabay", "pexels")
            print(f"      [seçim(vision): pexels~{px_total} / pixabay~{pb_total} -> önce {sira[0]}]")
    # 2) Sayısal vekil (vision yok/başarısız)
    if sira is None:
        esit_tercih = oncelik if oncelik in ("pexels", "pixabay") else "pexels"
        if px_total != pb_total:
            sira = ("pexels", "pixabay") if px_total > pb_total else ("pixabay", "pexels")
        else:
            sira = ("pexels", "pixabay") if esit_tercih == "pexels" else ("pixabay", "pexels")
        print(f"      [seçim(sayısal): pexels~{px_total} / pixabay~{pb_total} -> önce {sira[0]}]")
    adaylar = {"pexels": px_adaylar, "pixabay": pb_adaylar}
    for kaynak in sira:
        for link in adaylar[kaynak]:
            if _indir(link, path):
                return (kaynak, path)
    return None


def sahne_gorselleri_hazirla(sahneler, cumleler, boyut, tmp, cocuk=True, stil="stok"):
    """Her sahne için konuya en uygun gerçek stok videoyu seçer. Kaynak (Pexels/Pixabay)
    sahnenin KONUSUNA göre belirlenir: o sorgu için hangi kaynakta daha çok video varsa
    oradan alınır (zorunlu bir oran yoktur). Seçilen kaynakta indirme başarısızsa diğeri
    devreye girer; hiçbiri bulamazsa fotogerçekçi AI görseline düşülür.
    ('video', yol) veya ('image', yol) listesi döndürür."""
    if sahneler:
        prompts = [s.get("gorsel") or s.get("metin") or "" for s in sahneler if s]
    else:
        prompts = [" ".join(cumleler[i:i+2]) for i in range(0, len(cumleler), 2)]
    prompts = [p for p in prompts if p.strip()] or ["colorful scene"]
    dikey = boyut[1] > boyut[0]
    gorseller = []
    sayac = {"pexels": 0, "pixabay": 0, "ai": 0}
    for i, p in enumerate(prompts):
        vpath = os.path.join(tmp, f"sahne_{i:03d}.mp4")
        stok = (stok_video_ara(p, boyut, vpath, dikey=dikey)
                if (stil == "stok" and not cocuk) else None)
        if stok:
            kaynak = stok[0] if isinstance(stok, tuple) else "stok"
            sayac[kaynak] = sayac.get(kaynak, 0) + 1
            gorseller.append(("video", vpath))
            print(f"      Sahne {i+1}/{len(prompts)}: gerçek stok video ✓ ({kaynak})")
        else:
            ipath = os.path.join(tmp, f"sahne_{i:03d}.jpg")
            gorsel_uret_ai(p, boyut, i, ipath, cocuk=cocuk, stil_ad=stil)
            sayac["ai"] += 1
            gorseller.append(("image", ipath))
            print(f"      Sahne {i+1}/{len(prompts)}: AI görseli ({stil})")
    print(f"      [dağılım: pexels={sayac['pexels']}, pixabay={sayac['pixabay']}, "
          f"ai={sayac['ai']} / toplam {len(prompts)} sahne]")
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


def _sahne_sureleri(sahneler, boundaries, toplam):
    """Her sahnenin GERÇEK anlatım süresini (sn) hesaplar: sahne metinlerinin
    uzunluğuna göre kelime zaman damgalarına (boundaries) hizalar. Böylece görsel
    tam da o sahnenin metni konuşulurken görünür (uzunluk farkı olsa bile kaymaz).
    Hesaplanamazsa None döner -> çağıran taraf eşit-dağıtıma düşer."""
    n = len(sahneler or [])
    if n == 0 or not boundaries:
        return None
    W = len(boundaries)
    if W < n:
        return None
    # her sahnenin ağırlığı = metnindeki kelime sayısı (yoksa 1)
    agir = [max(1, len((s.get("metin") or "").split())) for s in sahneler]
    tw = sum(agir) or n
    # kümülatif kelime sınırları -> sahne başlangıç kelime indeksleri
    sinir = [0]; acc = 0
    for a in agir:
        acc += a
        sinir.append(min(W, round(acc / tw * W)))
    baslangic = [float(boundaries[min(sinir[i], W - 1)]["start"]) for i in range(n)]
    baslangic[0] = 0.0
    sureler = []
    for i in range(n):
        bit = baslangic[i + 1] if i + 1 < n else toplam
        sureler.append(max(0.6, bit - baslangic[i]))
    return sureler


def video_uret_animasyon(gorseller, mp3, ass, cikti, boyut, fps, gecis=0.28,
                         max_sahne_sn=3.5, sahne_sureleri=None):
    import math
    W, H = boyut
    toplam = sure_al(mp3)
    # normalize: düz string -> ("image", yol)
    gorseller = [g if isinstance(g, (tuple, list)) else ("image", g) for g in gorseller]
    n0 = len(gorseller) or 1
    _dikey = H > W
    klip_gorsel = []   # her klibin görseli
    klip_sure = []     # her klibin EKRAN (unique) süresi sn; None -> uniform hesaplanır
    if (not _dikey) and n0 > 1 and sahne_sureleri and len(sahne_sureleri) == n0:
        # TAM SENKRON (uzun/yatay): her sahne, seslendirmedeki GERÇEK süresi kadar
        # ekranda kalır; tempo için alt-parçalara bölünür (aynı görsel, farklı Ken Burns).
        for i in range(n0):
            dur_i = max(0.6, float(sahne_sureleri[i]))
            sub = max(1, int(round(dur_i / max_sahne_sn)))
            for _ in range(sub):
                klip_gorsel.append(gorseller[i]); klip_sure.append(dur_i / sub)
    elif (not _dikey) and n0 > 1:
        # Yatay ama senkron bilgisi yok: SIRAYLA eşit dağıtım (eski davranış), döngü YOK
        per = max(1, round((toplam / n0) / max_sahne_sn))
        for i in range(n0):
            for _ in range(per):
                klip_gorsel.append(gorseller[i]); klip_sure.append(None)
    else:
        # SHORTS (dikey): ENERJİK TEMPO -> daha sık kesme (retention). Sahne
        # başına ~2.6 sn hedef; görsel havuzu döngüyle doldurulur (tekrar eden
        # kliplerde Ken Burns yönü index'e bağlı değiştiği için aynı görünmez).
        hedef_sn = 2.6
        seg = max(n0, math.ceil(toplam / hedef_sn))
        for i in range(seg):
            klip_gorsel.append(gorseller[i % n0]); klip_sure.append(None)
    n = len(klip_gorsel)
    # None (uniform) süreler için tek tip D hesapla ve doldur (eski davranışla birebir)
    if any(s is None for s in klip_sure):
        D = (toplam + (n - 1) * gecis) / n if n > 0 else toplam
        D = max(D, gecis + 0.6)
        klip_sure = [(D - gecis) if s is None else s for s in klip_sure]
    tmp = tempfile.mkdtemp()
    klipler = []
    for i, (tip, g) in enumerate(klip_gorsel):
        u = max(0.3, klip_sure[i])
        L = u + gecis                 # ENCODE uzunluğu = ekran süresi + geçiş payı
        frames = int(L * fps)
        seg = os.path.join(tmp, f"k{i}.mp4")
        if tip == "video":
            off = (i * 1.7) % 4.0   # tekrar olursa farklı an
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},fps={fps},format=yuv420p")
            subprocess.run(["ffmpeg", "-y", "-ss", f"{off:.1f}", "-stream_loop", "-1",
                            "-i", g, "-t", f"{L:.3f}", "-vf", vf, "-r", str(fps), "-an",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", seg],
                           check=True, capture_output=True)
        else:
            vf = _ken_burns_vf(i, W, H, frames, fps)
            subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", g, "-t", f"{L:.3f}",
                            "-vf", vf, "-r", str(fps),
                            "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "22", seg], check=True, capture_output=True)
        klipler.append(seg)

    # MODERN geçiş seti: hızlı/temiz olanlar (dated 'circleopen/wiperight' çıkarıldı).
    # Kısa süreli (gecis) uygulanınca snappy his verir.
    GECISLER = ["fade", "dissolve", "smoothleft", "smoothright", "slideup", "smoothup"]

    tmpv = os.path.join(tmp, "gorsel.mp4")
    if n == 1:
        shutil.copy(klipler[0], tmpv)
    else:
        inputs = []
        for k in klipler:
            inputs += ["-i", k]
        fc = ""
        prev = "0:v"
        off = 0.0
        for i in range(1, n):
            off += max(0.3, klip_sure[i - 1])   # kümülatif EKRAN süresi = xfade offset
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
    grade = ("eq=saturation=1.20:contrast=1.07:brightness=0.012,"
             "unsharp=5:5:0.5:5:5:0.0,vignette=angle=PI/6")
    subprocess.run(["ffmpeg", "-y", "-i", tmpv, "-i", mp3,
                    "-vf", f"subtitles='{ass_esc}',{grade}",
                    # SES: kırpılma (clipping) çıtırtısını önle -> sabit örnekleme + tepe sınırlayıcı
                    "-af", "aresample=44100,alimiter=limit=0.95",
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest", cikti],
                   check=True, capture_output=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return toplam


def sure_al(mp3):
    out = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                          "-of","default=noprint_wrappers=1:nokey=1", mp3],
                         capture_output=True, text=True)
    return float(out.stdout.strip())


# ----------------------------------------------------------
# ARKA FON MÜZİĞİ (telifsiz / CC0) — konuşma altında otomatik kısılma (ducking)
# ----------------------------------------------------------
def _muzik_cfg():
    """config.json'dan arka fon müziği ayarlarını okur (yoksa güvenli varsayılan)."""
    cfg = {}
    try:
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        pass
    return {
        "acik": bool(cfg.get("arka_muzik", False)),
        "ses": float(cfg.get("arka_muzik_ses", 0.11)),
        "kaynaklar": cfg.get("arka_muzik_kaynaklar") or {},
    }


def _muzik_sec(kaynaklar, tema):
    """Temaya uygun bir CC0 müzik URL'si seçer (yoksa 'genel' havuzuna düşer)."""
    import random
    if isinstance(kaynaklar, list):        # düz liste de desteklenir
        return random.choice(kaynaklar) if kaynaklar else None
    havuz = kaynaklar.get(tema) or kaynaklar.get("genel") or []
    # tek string verilmişse listeye çevir
    if isinstance(havuz, str):
        havuz = [havuz]
    return random.choice(havuz) if havuz else None


def _muzik_yerel_sec(tema):
    """assets/muzik/ içindeki YEREL parçalardan (ör. ElevenLabs ile üretilmiş
    set) temaya uygun birini seçer. Öncelik: <tema>*.mp3 -> genel*.mp3 -> *.mp3.
    Yoksa None (o zaman URL'den indirilir)."""
    import glob, random
    d = "assets/muzik"
    if not os.path.isdir(d):
        return None
    for pat in (f"{tema}*", "genel*", "*"):
        hits = sorted(glob.glob(os.path.join(d, pat + ".mp3")) +
                      glob.glob(os.path.join(d, pat + ".MP3")))
        if hits:
            return random.choice(hits)
    return None


def _muzik_ekle(narration_mp3, tmp, tema=None):
    """Anlatım sesine arka fon müziğini DUCKING ile karıştırır.
    Kaynak önceliği: (1) YEREL assets/muzik/ (ElevenLabs ile üretilmiş set,
    indirme yok), (2) config.arka_muzik_kaynaklar'daki telifsiz (CC0) URL.
    Müzik konuşma varken otomatik kısılır (sidechaincompress), konuşma bitince
    hafifçe yükselir. Herhangi bir hata olursa orijinal anlatım sesi aynen
    döner (video akışı asla bozulmaz).
    Dönüş: karıştırılmış mp3 yolu (veya değişmeden narration_mp3)."""
    mc = _muzik_cfg()
    if not mc["acik"]:
        return narration_mp3
    tema = tema or "genel"
    try:
        # 1) YEREL set (ElevenLabs) — indirme yok
        muzik_ham = _muzik_yerel_sec(tema)
        kaynak = "yerel"
        # 2) Yereli yoksa CC0 URL'den indir
        if not muzik_ham:
            url = _muzik_sec(mc["kaynaklar"], tema)
            if not url:
                return narration_mp3
            import urllib.request
            muzik_ham = os.path.join(tmp, "bgm_src.mp3")
            req = urllib.request.Request(url, headers={"User-Agent": "yt-otomasyon/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r, open(muzik_ham, "wb") as f:
                shutil.copyfileobj(r, f)
            kaynak = "CC0-URL"
        if not os.path.exists(muzik_ham) or os.path.getsize(muzik_ham) < 20000:
            return narration_mp3
        vol = max(0.02, min(0.5, mc["ses"]))
        out = os.path.join(tmp, "narration_muzikli.mp3")
        # narration = 0:a: asplit ile ikiye ayrılır -> [v0] mikse, [sc] yan-zincir
        # tetiğe (aynı pad iki filtreye doğrudan giremez). müzik = 1:a (sonsuz
        # döngü -> anlatım boyunca sürer, amix duration=first ile kesilir).
        # Gain-staging: müzik makeup düşük + miks çıkışı 0.89'a sınırlanır (final
        # mux'taki 0.95 limiter'ın ALTINDA -> çift limitleme/cızırtı önlenir).
        # Müzikte lowpass 11k: konuşma tizinde yer açar (netlik).
        fc = (f"[0:a]asplit=2[v0][sc];"
              f"[1:a]volume={vol:.3f},highpass=f=90,lowpass=f=11000[m];"
              f"[m][sc]sidechaincompress=threshold=0.09:ratio=2.5:attack=25:release=240:makeup=1[md];"
              f"[v0][md]amix=inputs=2:duration=first:normalize=0,"
              f"aresample=44100,alimiter=limit=0.89[a]")
        subprocess.run(
            ["ffmpeg", "-y", "-i", narration_mp3, "-stream_loop", "-1", "-i", muzik_ham,
             "-filter_complex", fc, "-map", "[a]",
             "-ac", "2", "-ar", "44100", "-b:a", "192k", out],
            check=True, capture_output=True)
        if os.path.exists(out) and os.path.getsize(out) > 20000:
            print(f"      Arka fon müziği eklendi ({kaynak}: {os.path.basename(muzik_ham)}, "
                  f"ses %{int(vol*100)}, ducking).")
            return out
    except Exception as e:
        print(f"      Arka fon müziği atlandı: {str(e)[:120]}")
    return narration_mp3

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
        "-af", "aresample=44100,alimiter=limit=0.95",  # clipping çıtırtısını önle
        "-map","0:v","-map","1:a",
        "-c:v","libx264","-preset","veryfast","-crf","20",
        "-c:a","aac","-b:a","192k","-ar","44100","-shortest",
        cikti
    ], check=True, capture_output=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return toplam

# ----------------------------------------------------------
# ANA AKIŞ
# ----------------------------------------------------------
def uret_video(script_path, cikti, ses="kadin", dikey=False, hiz="+0%",
               sahneler=None, animasyon=True, cocuk=True, tonlama="+0Hz",
               gorsel_stil="stok", kanca=None, eleven_once=False, eleven_voice_id=None,
               muzik_tema=None):
    """Orkestratör tarafından çağrılır: script -> mp4.
    sahneler verilirse (Gemini'den), her sahne için AI görsel üretir ve
    Ken Burns + çapraz geçişle animasyonlu montaj yapar.
    tonlama: ses tonu (örn '-12Hz' daha tok/derin erkek sesi).
    eleven_once=True: seslendirmede ElevenLabs (daha gerçekçi) önce denenir;
    başarısız olursa Google TTS, o da olmazsa edge-tts'e düşülür."""
    boyut = CONFIG["dikey"] if dikey else CONFIG["yatay"]
    voice = CONFIG["sesler"][ses]
    text, cumleler = metni_oku(script_path)
    # SES NORMALİZASYONU: sayı/yüzde/kısaltmaları seslendirmeden önce Türkçe
    # okunuşa çevir (TTS telaffuz hatalarını önler). Altyazı da bu metinden üretilir.
    text = _ses_normalize(text)
    cumleler = [_ses_normalize(c) for c in cumleler]
    tmp = tempfile.mkdtemp()
    mp3 = os.path.join(tmp, "narration.mp3")
    _gk=_google_key(); _pk=_pexels_key(); _xk=_pixabay_key()
    print(f"      [anahtar: google={_gk[:6]}..len{len(_gk)}, pexels={_pk[:6]}..len{len(_pk)}, pixabay={_xk[:6]}..len{len(_xk)}]")
    boundaries = None
    # Seslendirme saglayici sirasi. eleven_once=True (uzun videolar) ise
    # ElevenLabs (daha gercekci insan sesi) once denenir; degilse mevcut
    # davranis korunur (Google TTS once, ElevenLabs yedek).
    _eleven = ("eleven", _eleven_seslendir, "ElevenLabs (gerçekçi insan sesi)")
    _google = ("google", _google_seslendir, "Google TTS (nöral Türkçe)")
    sira = ([_eleven, _google] if eleven_once else [_google, _eleven])
    for _ad, _fn, _etiket in sira:
        if boundaries is not None:
            break
        if _ad == "eleven" and not _eleven_key():
            continue
        if _ad == "google" and not _google_key():
            continue
        try:
            boundaries = (_fn(text, mp3, eleven_voice_id) if _ad == "eleven"
                          else _fn(text, mp3))
            print(f"      Ses: {_etiket}")
        except Exception as e:
            print(f"      {_ad} TTS hata ({str(e)[:200]}), sonraki saglayiciya geciliyor")
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
    # ARKA FON MÜZİĞİ: anlatım sesine CC0 müzik (ducking ile) karıştır. Alt yazı
    # zamanlaması yukarıda GERÇEK anlatım sesinden çıkarıldığı için müziği burada
    # ekliyoruz (senkron bozulmaz). Kapalıysa/başarısızsa mp3 değişmeden döner.
    mp3 = _muzik_ekle(mp3, tmp, muzik_tema)
    if animasyon:
        gorseller = sahne_gorselleri_hazirla(sahneler, cumleler, boyut, tmp,
                                             cocuk=cocuk, stil=gorsel_stil)
        # UZUN (yatay) videolarda görselleri seslendirmeye TAM senkronla:
        # her sahne, metninin konuşulduğu gerçek zaman aralığında görünür.
        _ss = _sahne_sureleri(sahneler, boundaries, sure_al(mp3)) if (not dikey and sahneler) else None
        video_uret_animasyon(gorseller, mp3, ass, cikti, boyut, CONFIG["fps"],
                             sahne_sureleri=_ss)
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
