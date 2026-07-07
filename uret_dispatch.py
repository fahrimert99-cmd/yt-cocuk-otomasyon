#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Make tarafindan tetiklenir (GitHub repository_dispatch, event: 'uret').
Make senaryosu Gemini ile JSON senaryo uretir, base64'leyip gonderir.
Bu betik base64'u cozer, JSON'u ayristirir, videoyu uretir ve YouTube'a yukler.

Ortam degiskenleri:
  RAW_B64 -> Make'in gonderdigi base64(Gemini JSON ciktisi)
  YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN  (GitHub Secrets)
Ayarlar: config.json (format, ses, gizlilik, kategori)
"""
import os, re, json, base64, tempfile
import video as V


def _temizle(txt):
    txt = txt.strip()
    txt = re.sub(r"^```(json)?", "", txt).strip()
    txt = re.sub(r"```$", "", txt).strip()
    return txt


def _icerik_al():
    b64 = os.environ.get("RAW_B64", "").strip()
    if b64:
        ham = base64.b64decode(b64).decode("utf-8")
        return json.loads(_temizle(ham))
    return {
        "script":   os.environ.get("SCRIPT", ""),
        "baslik":   os.environ.get("BASLIK", "Video"),
        "aciklama": os.environ.get("ACIKLAMA", ""),
        "etiketler": json.loads(os.environ.get("ETIKETLER", "[]") or "[]"),
    }


def main():
    cfg = {}
    if os.path.exists("config.json"):
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)

    veri = _icerik_al()
    script = (veri.get("script") or "").strip()
    if not script:
        raise SystemExit("Senaryo metni bos - Make'ten icerik gelmedi.")
    baslik   = (veri.get("baslik") or "Video")[:100]
    aciklama = veri.get("aciklama") or ""
    etiketler = veri.get("etiketler") or []
    if isinstance(etiketler, str):
        etiketler = [e.strip() for e in etiketler.split(",") if e.strip()]

    dikey    = str(cfg.get("format", "dikey")).lower() == "dikey"
    ses      = cfg.get("ses", "kadin")
    gizlilik = cfg.get("gizlilik", "private")
    kategori = str(cfg.get("kategori", "27"))
    cocuk = bool(cfg.get("cocuk_icerigi", False))
    animasyon = bool(cfg.get("animasyon", True))
    tonlama = str(cfg.get("tonlama", "+0Hz"))
    sahneler = veri.get("sahneler") or None

    print(f"[1/3] Icerik alindi ({len(script.split())} kelime). Baslik: {baslik}")

    tmp = tempfile.mkdtemp()
    sp = os.path.join(tmp, "script.txt")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(script)
    os.makedirs("output", exist_ok=True)
    cikti = "output/video.mp4"
    print("[2/3] Video uretiliyor (edge-tts + alt yazi + FFmpeg) ...")
    V.uret_video(sp, cikti, ses=ses, dikey=dikey,
                 sahneler=sahneler, animasyon=animasyon, cocuk=cocuk, tonlama=tonlama)
    print(f"      Cikti: {cikti}  ({os.path.getsize(cikti)//1024} KB)")

    print("[3/3] YouTube'a yukleniyor ...")
    import youtube_yukle as YT
    YT.yukle(cikti, baslik, aciklama, etiketler, gizlilik=gizlilik, kategori=kategori, cocuk_icerigi=cocuk)
    print("TAMAM :)")


if __name__ == "__main__":
    main()
