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
    "altyazi_max_kelime": 8,        # bir alt yazı satırındaki max kelime
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

def ass_yaz(cues, path, cfg, dikey):
    a = cfg["altyazi"]
    punto = a["punto_dikey"] if dikey else a["punto_yatay"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {'1080' if dikey else '1920'}
PlayResY: {'1920' if dikey else '1080'}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Def,{a['font']},{punto*4},{a['renk']},{a['kenar_renk']},&H88000000,-1,{a['kenar_kalinlik']},1,2,80,80,{a['alt_bosluk']}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(head)
        for c in cues:
            txt = c["text"].replace("\n", " ")
            f.write(f"Dialogue: 0,{_ass_zaman(c['start'])},{_ass_zaman(c['end'])},Def,,0,0,0,,{txt}\n")

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
def gorsel_uret_ai(prompt, boyut, idx, path, cocuk=True):
    import urllib.parse, urllib.request
    W, H = boyut
    stil = ("children's book illustration, cute, colorful, cartoon, friendly, "
            "soft lighting, simple, no text") if cocuk else \
           ("cinematic scientific illustration, detailed, dramatic lighting, realistic, educational, high quality, no text")
    tam = f"{prompt}, {stil}"
    q = urllib.parse.quote(tam)
    url = (f"https://image.pollinations.ai/prompt/{q}"
           f"?width={W}&height={H}&nologo=true&seed={1000+idx}")
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


def sahne_gorselleri_hazirla(sahneler, cumleler, boyut, tmp, cocuk=True):
    """sahneler: [{'gorsel': 'ingilizce görsel tarifi'}, ...] (Gemini'den).
    Yoksa cümlelerden türetir. Her sahne için AI görsel üretir."""
    if sahneler:
        prompts = [s.get("gorsel") or s.get("metin") or "" for s in sahneler if s]
    else:
        # sahne yoksa ~2 cümlede bir görsel
        prompts = [" ".join(cumleler[i:i+2]) for i in range(0, len(cumleler), 2)]
    prompts = [p for p in prompts if p.strip()] or ["colorful happy scene"]
    paths = []
    for i, p in enumerate(prompts):
        dst = os.path.join(tmp, f"sahne_{i:03d}.jpg")
        gorsel_uret_ai(p, boyut, i, dst, cocuk=cocuk)
        paths.append(dst)
    return paths


# ----------------------------------------------------------
# ANİMASYONLU MONTAJ: Ken Burns (yavaş zoom) + çapraz geçiş
# ----------------------------------------------------------
def video_uret_animasyon(gorseller, mp3, ass, cikti, boyut, fps, gecis=0.7):
    W, H = boyut
    toplam = sure_al(mp3)
    n = len(gorseller)
    # her sahnenin süresi: geçiş paylarını da hesaba katarak sesi tam kaplasın
    # toplam = n*D - (n-1)*gecis  ->  D = (toplam + (n-1)*gecis) / n
    D = (toplam + (n - 1) * gecis) / n if n > 0 else toplam
    D = max(D, gecis + 0.6)
    tmp = tempfile.mkdtemp()
    klipler = []
    for i, g in enumerate(gorseller):
        seg = os.path.join(tmp, f"k{i}.mp4")
        yon = 0.0009 if i % 2 == 0 else 0.0007
        zoom = f"zoompan=z='min(zoom+{yon},1.15)':d={int(D*fps)}:s={W}x{H}:fps={fps}"
        subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", g, "-t", f"{D:.3f}",
                        "-vf", f"scale={W}:{H},{zoom},format=yuv420p",
                        "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "23", seg], check=True, capture_output=True)
        klipler.append(seg)

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
            fc += (f"[{prev}][{i}:v]xfade=transition=fade:"
                   f"duration={gecis}:offset={off:.3f}[{out}];")
            prev = out
        fc = fc.rstrip(";")
        subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", fc,
                        "-map", f"[{prev}]", "-r", str(fps), "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                        tmpv], check=True, capture_output=True)

    # alt yazı göm + ses ekle
    ass_esc = ass.replace("\\", "/").replace(":", "\\:")
    subprocess.run(["ffmpeg", "-y", "-i", tmpv, "-i", mp3,
                    "-vf", f"subtitles='{ass_esc}'",
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
               sahneler=None, animasyon=True, cocuk=True, tonlama="+0Hz"):
    """Orkestratör tarafından çağrılır: script -> mp4.
    sahneler verilirse (Gemini'den), her sahne için AI görsel üretir ve
    Ken Burns + çapraz geçişle animasyonlu montaj yapar.
    tonlama: ses tonu (örn '-12Hz' daha tok/derin erkek sesi)."""
    boyut = CONFIG["dikey"] if dikey else CONFIG["yatay"]
    voice = CONFIG["sesler"][ses]
    text, cumleler = metni_oku(script_path)
    tmp = tempfile.mkdtemp()
    mp3 = os.path.join(tmp, "narration.mp3")
    boundaries = seslendir(text, voice, hiz, mp3, pitch=tonlama)
    cues = cue_olustur(boundaries, CONFIG["altyazi_max_kelime"], CONFIG["altyazi_max_sure"])
    ass = os.path.join(tmp, "sub.ass")
    ass_yaz(cues, ass, CONFIG, dikey)
    os.makedirs(os.path.dirname(cikti) or ".", exist_ok=True)
    if animasyon:
        gorseller = sahne_gorselleri_hazirla(sahneler, cumleler, boyut, tmp, cocuk=cocuk)
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
