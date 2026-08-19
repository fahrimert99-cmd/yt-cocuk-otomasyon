#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Uzun (yatay 16:9) GİZEM kapağı (1280x720): sinematik dramatik zemin +
alt karartma gradyanı + dev iki-renkli (beyaz/sarı) merak-odaklı başlık.
Ucuz köşe 'play butonu' süsleri kaldırıldı — belgesel/merak estetiği (CTR odaklı)."""
import os, re, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import PIL.ImageStat as S

W, H = 1280, 720
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SARI = (255, 209, 0); BEYAZ = (255, 255, 255)
# Merak/gizem VURGU kelimeleri (sarı vurgulanır) — göz bunlara takılsın.
VURGU = ["GİZEM", "GİZEMİ", "SIR", "SIRRI", "SIRLARI", "GERÇEK", "GERÇEKTE", "KAYIP",
         "NEDEN", "NASIL", "KİM", "ESRAR", "ESRARENGİZ", "LANET", "LANETİ", "BİLİNMEYEN",
         "TUHAF", "GİZLİ", "YOK", "KEŞFEDİL", "ÇÖZÜLEME", "EFSANE", "FACİA", "DEV",
         "YAŞIYOR", "SAKLI", "OLUYOR", "OLDU", "İÇİNDE", "ALTINDA", "PATLA", "GÖMÜLDÜ"]

def _upper(s):
    return s.translate(str.maketrans({"i": "İ", "ı": "I", "ş": "Ş", "ğ": "Ğ",
                                      "ü": "Ü", "ö": "Ö", "ç": "Ç"})).upper()

def _sure(v):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nokey=1:noprint_wrappers=1", v],
                       capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except: return 5.0

def _kare(video, frame):
    """Videodan en canlı/dengeli kareyi seç (kapak zemini)."""
    best = None; bs = -1
    for p in (0.2, 0.35, 0.5, 0.65, 0.8):
        f = f"/tmp/_k{int(p*100)}.jpg"
        subprocess.run(["ffmpeg", "-y", "-ss", f"{max(0.4,_sure(video)*p):.2f}", "-i", video,
                        "-frames:v", "1", f], capture_output=True)
        try:
            im = Image.open(f).convert("RGB")
            m = S.Stat(im.convert("L")).mean[0]; sat = S.Stat(im.convert("HSV")).mean[1]
            sc = sat * 0.8 + (70 - abs(m - 130))
            if sc > bs: bs = sc; best = f
        except: pass
    if best: subprocess.run(["cp", best, frame])
    return os.path.exists(frame)

def _dikey_gradyan(renk, noktalar):
    """Tek kanallı alfa gradyanı: noktalar=[(y_orani, alfa),...] arası lineer."""
    g = Image.new("L", (1, H), 0); px = g.load()
    noktalar = sorted(noktalar)
    for y in range(H):
        r = y / H; a = noktalar[0][1]
        for i in range(len(noktalar) - 1):
            y0, a0 = noktalar[i]; y1, a1 = noktalar[i + 1]
            if y0 <= r <= y1:
                t = (r - y0) / (y1 - y0 + 1e-9); a = a0 + (a1 - a0) * t; break
            if r > y1: a = a1
        px[0, y] = int(max(0, min(255, a)))
    g = g.resize((W, H))
    kat = Image.new("RGBA", (W, H), renk + (255,)); kat.putalpha(g)
    return kat

def kapak_uret(video_path, baslik, cikti="output/uzun_kapak.jpg"):
    os.makedirs(os.path.dirname(cikti) or ".", exist_ok=True)
    frame = "/tmp/_ku.jpg"
    if not _kare(video_path, frame): Image.new("RGB", (W, H), (12, 12, 18)).save(frame)
    try: bg = Image.open(frame).convert("RGB")
    except: bg = Image.new("RGB", (W, H), (12, 12, 18))
    sc = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * sc), int(bg.height * sc)), Image.LANCZOS)
    l = (bg.width - W) // 2; t = (bg.height - H) // 2; bg = bg.crop((l, t, l + W, t + H))

    # SİNEMATİK grade: canlı ama koyu, güçlü kontrast.
    bg = ImageEnhance.Color(bg).enhance(1.32)
    bg = ImageEnhance.Contrast(bg).enhance(1.30)
    bg = ImageEnhance.Brightness(bg).enhance(0.70)
    # Güçlü vignette (kenarlar kararır, merkez öne çıkar)
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse([-170, -400, W + 170, H + 250], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(210))
    bg = Image.composite(bg, ImageEnhance.Brightness(bg).enhance(0.36), vig)
    base = bg.convert("RGBA")

    # ALT karartma gradyanı: başlık HER zaman net okunur.
    base = Image.alpha_composite(base, _dikey_gradyan((5, 6, 12), [(0.0, 0), (0.40, 0), (0.62, 120), (1.0, 238)]))
    # ÜST hafif karartma: denge + olası üst yazılar için nefes.
    base = Image.alpha_composite(base, _dikey_gradyan((5, 6, 12), [(0.0, 130), (0.28, 0), (1.0, 0)]))
    d = ImageDraw.Draw(base, "RGBA")

    # ---- DEV İKİ-RENKLİ BAŞLIK (alt) ----
    metin = _upper(re.sub(r"[^\w\sğüşiöçİĞÜŞÖÇ?!.,'-]", "", baslik, flags=re.UNICODE).strip())
    kel = metin.split()
    fs = 92
    for _fs in (140, 128, 116, 104, 94, 84):
        font = ImageFont.truetype(FB, _fs); maxw = W - 130; sat = []; cur = ""
        for k in kel:
            if d.textlength((cur + " " + k).strip(), font=font) <= maxw:
                cur = (cur + " " + k).strip()
            else:
                sat.append(cur); cur = k
        if cur: sat.append(cur)
        fs = _fs
        if len(sat) <= 4: break
    font = ImageFont.truetype(FB, fs)
    lh = int(fs * 1.04); blok = lh * len(sat); ty = H - blok - 44

    def ciz(x, y, word, renk, font, o):
        # kalın siyah kontur (okunabilirlik) + renk
        for dx in range(-o, o + 1, 2):
            for dy in range(-o, o + 1, 2):
                d.text((x + dx, y + dy), word, font=font, fill=(0, 0, 0, 255))
        d.text((x, y), word, font=font, fill=renk)

    def _vurgu_mu(w):
        w2 = w.strip(".,!?'-")
        return any(w2.startswith(v) or v in w2 for v in VURGU)

    for ln in sat:
        w = d.textlength(ln, font=font); tx = (W - w) // 2; o = max(6, fs // 11); cx = tx
        for word in ln.split():
            renk = SARI if _vurgu_mu(word) else BEYAZ
            ciz(cx, ty, word, renk, font, o)
            cx += d.textlength(word + " ", font=font)
        ty += lh

    base.convert("RGB").save(cikti, quality=92)
    return cikti

if __name__ == "__main__":
    import sys
    print(kapak_uret(sys.argv[1] if len(sys.argv) > 1 else "in.mp4",
                     sys.argv[2] if len(sys.argv) > 2 else "BERMUDA ŞEYTAN ÜÇGENİNDE GERÇEKTE NE OLUYOR?"))
