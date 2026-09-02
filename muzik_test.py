#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Arka fon müziği TESTİ — YouTube'a YÜKLEMEZ.

Kısa (sesli + CC0 arka fon müziği + ducking) bir dikey klip üretir
(output/test_muzik.mp4) ve GitHub Actions'ta workflow artifact olarak alınır.
İş akışına YT secret'ları verilmediği için (bkz. muzik_test.yml) kanala hiçbir
şey yüklenemez. Amaç: müziği/ducking'i indirip DİNLEMEK ve seviyeyi ayarlamak.

MUZIK_SES env'i verilirse config'teki arka_muzik_ses geçici olarak ezilir
(ör. 0.15 ile daha belirgin denemek için).
"""
import os, json, tempfile
import video as V

# ~20 sn'lik örnek anlatım (kanal tarzı: tüketici tuzağı + CTA/teaser).
SCRIPT = (
    "Dikkat! Marketteki o cazip indirim aslında bir tuzak olabilir. "
    "Rafın göz hizasındaki ürünler her zaman en ucuzu değildir. "
    "Fiyat etiketindeki birim fiyatı okumadan sepete atma. "
    "Bir sonraki videoda kasada seni bekleyen tuzağı anlatacağım. "
    "Abone ol, çünkü bu tuzakları herkesin bilmesi gerek."
)


def main():
    cfg = {}
    if os.path.exists("config.json"):
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)

    # İsteğe bağlı: müzik sesini env ile geçici ez (config'i değiştirmeden dene).
    _ov = os.environ.get("MUZIK_SES", "").strip()
    if _ov:
        try:
            cfg["arka_muzik_ses"] = float(_ov)
        except Exception:
            pass
        # video.py config.json'u kendi okuyor; bu yüzden geçici bir kopya yaz.
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print(f"[test] Müzik sesi geçici olarak {cfg['arka_muzik_ses']} yapıldı.")

    tmp = tempfile.mkdtemp()
    sp = os.path.join(tmp, "script.txt")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(SCRIPT)
    os.makedirs("output", exist_ok=True)
    cikti = "output/test_muzik.mp4"
    ses_id = str(cfg.get("kisa_ses_id", "")).strip() or None

    print("[test] Klip üretiliyor (ElevenLabs ses + CC0 müzik + ducking) ...")
    V.uret_video(sp, cikti, ses=cfg.get("ses", "erkek"), dikey=True,
                 hiz=str(cfg.get("hiz", "+6%")), sahneler=None, animasyon=False,
                 cocuk=bool(cfg.get("cocuk_icerigi", False)),
                 tonlama=str(cfg.get("tonlama", "+0Hz")),
                 gorsel_stil="stok", kanca=None,
                 eleven_once=bool(cfg.get("kisa_eleven", True)),
                 eleven_voice_id=ses_id, muzik_tema="genel")
    print(f"TEST TAMAM ✓  {cikti}  ({os.path.getsize(cikti)//1024} KB)")
    print("Bu video YouTube'a YÜKLENMEDİ; Actions çalışmasının 'Artifacts' "
          "bölümünden test-muzik.zip olarak indirilir.")


if __name__ == "__main__":
    main()
