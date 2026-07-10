#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Çarpıcı YouTube kapak (thumbnail) üretici.
Videodan bir kare alır, 1280x720'ye getirir, kontrastı artırır ve
üzerine BÜYÜK, kalın, dikkat çekici başlık yazısı basar.
"""
import os, re, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

W, H = 1280, 720
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _tr_upper(s):
    tbl = str.maketrans({"i":"İ","ı":"I","ş":"Ş","ğ":"Ğ","ü":"Ü","ö":"Ö","ç":"Ç"})
    return s.translate(tbl).upper()


def _sure(video):
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                        "-of","default=noprint_wrappers=1:nokey=1", video],
                       capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except: return 5.0


def kapak_uret(video_path, baslik, cikti="output/kapak.jpg"):
    os.makedirs(os.path.dirname(cikti) or ".", exist_ok=True)
    # 1) videodan net bir kare al (ortadan)
    frame = "/tmp/_kapak_frame.jpg"
    t = max(0.5, _sure(video_path) * 0.45)
    subprocess.run(["ffmpeg","-y","-ss",f"{t:.2f}","-i",video_path,"-frames:v","1",frame],
                   capture_output=True)
    try:
        bg = Image.open(frame).convert("RGB")
    except Exception:
        bg = Image.new("RGB", (W, H), (20, 24, 48))

    # 2) 1280x720'yi kaplayacak şekilde ölçekle + kırp
    scale = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width*scale), int(bg.height*scale)), Image.LANCZOS)
    left = (bg.width - W)//2; top = (bg.height - H)//2
    bg = bg.crop((left, top, left+W, top+H))
    # canlılık + hafif karartma (yazı okunsun)
    bg = ImageEnhance.Color(bg).enhance(1.25)
    bg = ImageEnhance.Contrast(bg).enhance(1.15)
    # alt kısma koyu degrade (yazı zemini)
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        grad.putpixel((0, y), int(200 * (y / H) ** 1.4))
    alpha = grad.resize((W, H))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    bg = Image.composite(dark, bg, alpha)

    d = ImageDraw.Draw(bg)

    # 3) başlık metni: emojiyi at, BÜYÜK harf, sar
    metin = re.sub(r"[^\w\sğüşiöçİĞÜŞÖÇ?!.,'-]", "", baslik, flags=re.UNICODE).strip()
    metin = _tr_upper(metin)
    # font boyutunu satır sayısına göre ayarla
    for fs in (110, 96, 84, 74, 64):
        font = ImageFont.truetype(FONT_BOLD, fs)
        kelimeler = metin.split()
        satirlar, cur = [], ""
        maxw = W - 120
        for k in kelimeler:
            test = (cur + " " + k).strip()
            if d.textlength(test, font=font) <= maxw: cur = test
            else: satirlar.append(cur); cur = k
        if cur: satirlar.append(cur)
        if len(satirlar) <= 4: break

    lh = int(fs * 1.12)
    toplam = lh * len(satirlar)
    ty = H - toplam - 55           # alta hizala
    for ln in satirlar:
        w = d.textlength(ln, font=font)
        tx = (W - w)//2
        # kalın siyah kenarlık
        o = max(4, fs//14)
        for dx in range(-o, o+1, 2):
            for dy in range(-o, o+1, 2):
                d.text((tx+dx, ty+dy), ln, font=font, fill=(0,0,0))
        # sarı dolgu
        d.text((tx, ty), ln, font=font, fill=(255, 221, 0))
        ty += lh

    # 4) üstte kırmızı vurgu şeridi
    d.rectangle([0, 0, W, 14], fill=(230, 30, 45))

    bg.convert("RGB").save(cikti, quality=88)
    return cikti


if __name__ == "__main__":
    import sys
    v = sys.argv[1] if len(sys.argv) > 1 else "output/video.mp4"
    b = sys.argv[2] if len(sys.argv) > 2 else "TEST BAŞLIK ÇOK ÇARPICI!"
    print(kapak_uret(v, b))
