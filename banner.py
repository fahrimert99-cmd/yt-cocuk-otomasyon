#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube kanal banner'ı (2560x1440) — TUZAK AVCISI altın-kırmızı marka kimliği.
Kapak (kapak.py) ile AYNI dil: dramatik koyu zemin + altın kelime-marka +
kırmızı 'play' motifi + altın çerçeve. Kritik metin, tüm cihazlarda görünen
GÜVENLİ ALAN (merkezde 1546x423) içinde tutulur.

Kullanım:  python3 banner.py            -> output/banner.png
Ayarlar config.json'dan okunur: marka_ad, marka_renk, marka_slogan.
"""
import os, json, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 2560, 1440
# Güvenli alan (YouTube tüm cihaz): merkezde 1546x423
SAFE_W, SAFE_H = 1546, 423
SX0, SY0 = (W - SAFE_W) // 2, (H - SAFE_H) // 2
SX1, SY1 = SX0 + SAFE_W, SY0 + SAFE_H

FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _cfg():
    try:
        with open("config.json", encoding="utf-8-sig") as f:
            c = json.load(f)
    except Exception:
        c = {}
    renk = c.get("marka_renk", [255, 195, 30])
    try:
        renk = tuple(int(x) for x in renk)[:3]
    except Exception:
        renk = (255, 195, 30)
    return {
        "ad": str(c.get("marka_ad", "TUZAK AVCISI") or "TUZAK AVCISI").strip(),
        "renk": renk,
        "slogan": str(c.get("marka_slogan", "Her gün yeni bir tüketici tuzağı") or "").strip(),
    }


def _up(s):
    return s.translate(str.maketrans({"i": "İ", "ı": "I", "ş": "Ş", "ğ": "Ğ",
                                       "ü": "Ü", "ö": "Ö", "ç": "Ç"})).upper()


def _play(size, kirmizi=(230, 20, 30)):
    """Kapaktaki 3D kırmızı 'play' öğesinin aynısı (marka tutarlılığı)."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = int(size * 0.22)
    for y in range(size):
        f = y / size
        d.line([(0, y), (size, y)],
               fill=(int(kirmizi[0] - 40 * f), int(kirmizi[1]), int(kirmizi[2]), 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    im.putalpha(mask)
    d = ImageDraw.Draw(im)
    cx, cy, sp = size * 0.54, size * 0.5, size * 0.26
    d.polygon([(cx - sp * 0.7, cy - sp), (cx - sp * 0.7, cy + sp), (cx + sp, cy)],
              fill=(255, 255, 255, 255))
    d.rounded_rectangle([1, 1, size - 2, size - 2], radius=r, outline=(120, 0, 10, 180), width=3)
    return im


def _hedef(size, altin):
    """Altın nişangah/hedef motifi ('avcı' vurgusu)."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = size // 2
    lw = max(4, size // 26)
    for rr, a in ((0.46, 255), (0.30, 220)):
        r = int(size * rr)
        d.ellipse([c - r, c - r, c + r, c + r], outline=altin + (a,), width=lw)
    # nişangah çizgileri
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        d.line([(c + dx * int(size * 0.20), c + dy * int(size * 0.20)),
                (c + dx * int(size * 0.5), c + dy * int(size * 0.5))],
               fill=altin + (255,), width=lw)
    d.ellipse([c - lw, c - lw, c + lw, c + lw], fill=altin + (255,))
    return im


def _yazi_boyu(d, metin, font):
    b = d.textbbox((0, 0), metin, font=font)
    return b[2] - b[0], b[3] - b[1]


def uret(cikti="output/banner.png"):
    cfg = _cfg()
    altin = cfg["renk"]
    ad = _up(cfg["ad"])
    os.makedirs(os.path.dirname(cikti) or ".", exist_ok=True)

    # --- Zemin: koyu, sıcak kırmızıya çalan degrade ---
    base = Image.new("RGB", (W, H), (12, 8, 10))
    top = (34, 12, 14)
    bot = (8, 6, 9)
    d = ImageDraw.Draw(base)
    for y in range(H):
        f = y / H
        col = (int(top[0] * (1 - f) + bot[0] * f),
               int(top[1] * (1 - f) + bot[1] * f),
               int(top[2] * (1 - f) + bot[2] * f))
        d.line([(0, y), (W, y)], fill=col)
    base = base.convert("RGBA")

    # --- Merkezde sıcak altın parıltı ---
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W * 0.28, H * 0.18, W * 0.72, H * 0.82],
                                 fill=(altin[0], altin[1], altin[2], 46))
    base = Image.alpha_composite(base, glow.filter(ImageFilter.GaussianBlur(240)))

    # --- Dekoratif 'play' motifleri (güvenli alan DIŞINDA, kenarlarda) ---
    def _paste(prop, xy, ang):
        p = prop.rotate(ang, expand=True, resample=Image.BICUBIC)
        g = Image.new("RGBA", base.size, (0, 0, 0, 0))
        a = p.split()[3].point(lambda v: int(v * 0.8))
        t = Image.new("RGBA", p.size, (255, 40, 40, 0)); t.putalpha(a)
        g.paste(t, (xy[0] - p.width // 2, xy[1] - p.height // 2), t)
        base.alpha_composite(g.filter(ImageFilter.GaussianBlur(30)))
        base.alpha_composite(p, (xy[0] - p.width // 2, xy[1] - p.height // 2))

    pb = _play(230)
    _paste(pb, (230, 250), 14)
    _paste(pb, (W - 230, 250), -14)
    _paste(_play(200), (300, H - 250), -12)
    _paste(_play(200), (W - 300, H - 250), 12)

    # --- Altın hedef/nişangah motifi (marka adının solunda, güvenli alan içinde) ---
    hedef = _hedef(300, altin)
    hy = SY0 + 30
    base.alpha_composite(hedef, (SX0 + 6, (H - 300) // 2 - 40))

    d = ImageDraw.Draw(base, "RGBA")

    # --- KELİME-MARKA: 'TUZAK AVCISI' altın, kırmızı-siyah gölge ---
    tx_left = SX0 + 330  # hedef motifinin sağından başla
    maxw = SX1 - tx_left - 10
    font = ImageFont.truetype(FB, 190)
    for fs in (200, 190, 176, 160, 148, 132):
        font = ImageFont.truetype(FB, fs)
        if _yazi_boyu(d, ad, font)[0] <= maxw:
            break
    tw, th = _yazi_boyu(d, ad, font)
    tx = tx_left
    ty = (H - th) // 2 - 60
    # gölge (kırmızı + siyah), 3D his
    for off in range(10, 0, -2):
        d.text((tx + off, ty + off), ad, font=font, fill=(120, 0, 8, 255))
    o = max(6, fs // 18)
    for dx in range(-o, o + 1, 2):
        for dy in range(-o, o + 1, 2):
            d.text((tx + dx, ty + dy), ad, font=font, fill=(0, 0, 0, 255))
    d.text((tx, ty), ad, font=font, fill=altin + (255,))

    # altın alt-çizgi
    ly = ty + th + 26
    d.rectangle([tx, ly, tx + tw, ly + 12], fill=altin + (255,))

    # --- Slogan (beyaz) ---
    if cfg["slogan"]:
        sf = ImageFont.truetype(FB, 58)
        sl = cfg["slogan"]
        sw, sh = _yazi_boyu(d, sl, sf)
        sx, sy = tx, ly + 34
        for dx in (-2, 0, 2):
            for dy in (-2, 0, 2):
                d.text((sx + dx, sy + dy), sl, font=sf, fill=(0, 0, 0, 255))
        d.text((sx, sy), sl, font=sf, fill=(245, 245, 245, 255))

    # --- Yayın saatleri rozeti (altın) ---
    rozet = "PZT–PAZ · 12:00 & 20:00"
    rf = ImageFont.truetype(FB, 44)
    rw, rh = _yazi_boyu(d, rozet, rf)
    rx, ry = tx, SY1 - rh - 26
    pad = 22
    d.rounded_rectangle([rx - pad, ry - pad // 2, rx + rw + pad, ry + rh + pad], radius=18,
                        fill=(0, 0, 0, 140), outline=altin + (255,), width=3)
    d.text((rx, ry), rozet, font=rf, fill=altin + (255,))

    # --- Vinyet (kenarları karart) ---
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse([-260, -260, W + 260, H + 260], fill=255)
    base = Image.composite(base, ImageEnhance_darken(base), vig.filter(ImageFilter.GaussianBlur(300)))

    # --- Altın ince çerçeve ---
    d = ImageDraw.Draw(base, "RGBA")
    for i in range(6):
        d.rectangle([i, i, W - 1 - i, H - 1 - i], outline=altin + (255,))

    base.convert("RGB").save(cikti, quality=95)
    return cikti


def ImageEnhance_darken(im):
    from PIL import ImageEnhance
    return ImageEnhance.Brightness(im).enhance(0.42)


def avatar(cikti="output/avatar.png", boyut=800):
    """Profil fotoğrafı (kare, YouTube daireye kırpar). Aynı marka dili:
    koyu zemin + altın nişangah + kırmızı play (avcı + video motifi birleşik)."""
    cfg = _cfg()
    altin = cfg["renk"]
    B = boyut
    os.makedirs(os.path.dirname(cikti) or ".", exist_ok=True)

    base = Image.new("RGBA", (B, B), (0, 0, 0, 0))
    # dairesel koyu zemin (kırmızıya çalan radyal)
    d = ImageDraw.Draw(base)
    c = B // 2
    for r in range(c, 0, -1):
        f = r / c
        col = (int(46 * (1 - f) + 12 * f), int(14 * (1 - f) + 8 * f),
               int(16 * (1 - f) + 10 * f), 255)
        d.ellipse([c - r, c - r, c + r, c + r], fill=col)
    # merkez altın parıltı
    glow = Image.new("RGBA", (B, B), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([B * 0.22, B * 0.22, B * 0.78, B * 0.78],
                                 fill=(altin[0], altin[1], altin[2], 70))
    base = Image.alpha_composite(base, glow.filter(ImageFilter.GaussianBlur(60)))

    # altın nişangah (büyük, ortada)
    h = _hedef(int(B * 0.72), altin)
    base.alpha_composite(h, ((B - h.width) // 2, (B - h.height) // 2))

    # merkeze kırmızı play üçgeni (video + avcı birleşik motif)
    d = ImageDraw.Draw(base, "RGBA")
    s = int(B * 0.14)
    cx, cy = c + int(s * 0.12), c
    d.polygon([(cx - s * 0.7, cy - s), (cx - s * 0.7, cy + s), (cx + s, cy)],
              fill=(230, 20, 30, 255))
    d.polygon([(cx - s * 0.7, cy - s), (cx - s * 0.7, cy + s), (cx + s, cy)],
              outline=(255, 255, 255, 230))

    # altın dış halka (daire kenarına)
    ring = max(8, B // 60)
    d.ellipse([ring // 2, ring // 2, B - ring // 2, B - ring // 2],
              outline=altin + (255,), width=ring)

    # daire dışını şeffaf yap (kare köşeler görünmesin)
    mask = Image.new("L", (B, B), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, B - 1, B - 1], fill=255)
    out = Image.new("RGBA", (B, B), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    out.save(cikti)
    return cikti


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "avatar":
        print(avatar())
    else:
        print(uret())

