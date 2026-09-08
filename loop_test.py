#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEAMLESS LOOP (dikişsiz döngü) TESTİ — YouTube'a YÜKLEMEZ.

Kısa bir DİKEY (Shorts) test klibi üretir (output/test_loop.mp4). config.json'daki
seamless_loop açıkken:
  1) anlatım sesinin SONUNDAKİ ölü hava kırpılır (dikiş sıkılaşır),
  2) son ~1.2 sn'de açılış kancası TEKRAR gösterilir (merak döngüsü).
Amaç: klibi indirip Shorts gibi arka arkaya oynatınca döngünün kesintisiz
hissedip hissetmediğini GÖRMEK. İş akışına YT secret'ları verilmez -> yükleme yok.
"""
import os, json, tempfile
import video as V

# Kanca (≤3 kelime kuralı) + soruyla biten, döngüye uygun ~18 sn anlatım.
KANCA = "İNDİRİM TUZAĞI"
SCRIPT = (
    "Marketteki o büyük indirim yazısı aslında bir tuzak olabilir. "
    "Rafın göz hizasındaki ürünler neredeyse hiçbir zaman en ucuzu değildir. "
    "Asıl ucuz ürünler en alt rafa, eğilmen gereken yere saklanır. "
    "Peki sen bu tuzağa kaç kez düştün?"
)


def main():
    cfg = {}
    if os.path.exists("config.json"):
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)

    # TEST İÇİN seamless'i ZORLA AÇ (config'te üretim güvenliği için kapalı durur;
    # video.py config.json'u kendi okuduğu için geçici olarak dosyaya yazıyoruz).
    cfg["seamless_loop"] = True
    cfg["seamless_kanca_tekrar"] = True
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print("[test] seamless_loop=True  seamless_kanca_tekrar=True (test için zorlandı)")

    tmp = tempfile.mkdtemp()
    sp = os.path.join(tmp, "script.txt")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(SCRIPT)
    os.makedirs("output", exist_ok=True)
    cikti = "output/test_loop.mp4"
    ses_id = str(cfg.get("kisa_ses_id", "")).strip() or None

    print("[test] DİKEY klip üretiliyor (seamless loop açık) ...")
    V.uret_video(sp, cikti, ses=cfg.get("ses", "erkek"), dikey=True,
                 hiz=str(cfg.get("hiz", "+6%")), sahneler=None, animasyon=True,
                 cocuk=bool(cfg.get("cocuk_icerigi", False)),
                 tonlama=str(cfg.get("tonlama", "+0Hz")),
                 gorsel_stil="stok", kanca=KANCA,
                 eleven_once=bool(cfg.get("kisa_eleven", True)),
                 eleven_voice_id=ses_id, muzik_tema="genel")
    print(f"TEST TAMAM ✓  {cikti}  ({os.path.getsize(cikti)//1024} KB)")
    print("Bu video YouTube'a YÜKLENMEDİ; 'loop-test-video' dalından çekilebilir.")


if __name__ == "__main__":
    main()
