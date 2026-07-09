#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub-native otomasyon (Make'siz).
basliklar.txt'ten sıradaki başlığı alır -> AI senaryo -> video -> YouTube -> sırayı ilerletir.
durum.json sırayı hatırlar (workflow commit'ler).
Ayarlar: config.json
"""
import os, json, tempfile
import ai_script
import video as V

BASLIKLAR = "basliklar.txt"
DURUM = "durum.json"


def _basliklar():
    with open(BASLIKLAR, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def _durum():
    if os.path.exists(DURUM):
        with open(DURUM, encoding="utf-8") as f:
            return json.load(f)
    return {"sonraki": 0}


def main():
    with open("config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    basliklar = _basliklar()
    durum = _durum()
    idx = durum["sonraki"] % len(basliklar)
    baslik = basliklar[idx]
    print(f"[1/4] Başlık ({idx+1}/{len(basliklar)}): {baslik}")

    print("[2/4] AI senaryo yazılıyor ...")
    veri = ai_script.uret(baslik)
    print(f"      Başlık: {veri.get('baslik')}")

    tmp = tempfile.mkdtemp()
    sp = os.path.join(tmp, "script.txt")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(veri["script"])
    os.makedirs("output", exist_ok=True)
    cikti = "output/video.mp4"
    print("[3/4] Video üretiliyor (AI görsel + hareket + alt yazı) ...")
    V.uret_video(sp, cikti,
                 ses=cfg.get("ses", "erkek"),
                 dikey=(cfg.get("format", "dikey") == "dikey"),
                 sahneler=veri.get("sahneler"),
                 animasyon=bool(cfg.get("animasyon", True)),
                 cocuk=bool(cfg.get("cocuk_icerigi", False)),
                 tonlama=str(cfg.get("tonlama", "+0Hz")))
    print(f"      Çıktı: {cikti}  ({os.path.getsize(cikti)//1024} KB)")

    print("[4/4] YouTube'a yükleniyor ...")
    import youtube_yukle as YT
    etiketler = veri.get("etiketler") or []
    YT.yukle(cikti, veri.get("baslik", baslik), veri.get("aciklama", ""),
             etiketler, gizlilik=cfg.get("gizlilik", "private"),
             kategori=str(cfg.get("kategori", "28")),
             cocuk_icerigi=bool(cfg.get("cocuk_icerigi", False)))

    durum["sonraki"] = idx + 1
    with open(DURUM, "w", encoding="utf-8") as f:
        json.dump(durum, f, ensure_ascii=False, indent=2)
    print(f"TAMAM ✓  (sıradaki: {durum['sonraki']})")


if __name__ == "__main__":
    import traceback, subprocess
    try:
        main()
    except BaseException:
        tb = traceback.format_exc()
        open("hata.log", "w", encoding="utf-8").write(tb)
        for c in (["git","config","user.name","bot"],
                  ["git","config","user.email","bot@users.noreply.github.com"],
                  ["git","add","hata.log"],
                  ["git","commit","-m","hata logu"],
                  ["git","push"]):
            subprocess.run(c, check=False)
        raise
