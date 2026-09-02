#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KURGU ÖNİZLEME — YouTube'a YÜKLEMEZ.

Gerçek montaj yolunu (animasyon=True + gerçek sahneler + stok video + ElevenLabs
ses + arka fon müziği + güncel kurgu ayarları) kullanarak TAM bir Short üretir ve
artifact olarak sunar. Böylece kurgu değişiklikleri kanala hiçbir şey yüklemeden
görülüp onaylanır.

KONU env verilirse senaryolar.json'da başlığı eşleşen senaryo; yoksa rastgele bir
'tuzak' senaryosu kullanılır.
"""
import os, json, tempfile, random
import video as V


def _senaryo_sec():
    with open("senaryolar.json", encoding="utf-8") as f:
        d = json.load(f)
    konu = os.environ.get("KONU", "").strip().lower()
    if konu:
        for s in d:
            if konu in s.get("baslik", "").lower():
                return s
    tuzak = [s for s in d if s.get("tema") == "tuzak"] or d
    return random.choice(tuzak)


def main():
    cfg = {}
    if os.path.exists("config.json"):
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)
    s = _senaryo_sec()
    print(f"[önizleme] Senaryo: {s.get('baslik')}  ({len(s.get('sahneler', []))} sahne)")
    tmp = tempfile.mkdtemp()
    sp = os.path.join(tmp, "script.txt")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(s["script"])
    os.makedirs("output", exist_ok=True)
    cikti = "output/onizleme.mp4"
    ses_id = str(cfg.get("kisa_ses_id", "")).strip() or None
    print("[önizleme] Gerçek montaj üretiliyor (stok video + ElevenLabs ses + "
          "müzik + yeni kurgu) ...")
    V.uret_video(sp, cikti, ses=cfg.get("ses", "erkek"), dikey=True,
                 hiz=str(cfg.get("hiz", "+6%")), sahneler=s.get("sahneler"),
                 animasyon=True, cocuk=bool(cfg.get("cocuk_icerigi", False)),
                 tonlama=str(cfg.get("tonlama", "+0Hz")),
                 gorsel_stil=str(cfg.get("gorsel_stil", "stok")), kanca=s.get("kanca"),
                 eleven_once=bool(cfg.get("kisa_eleven", True)),
                 eleven_voice_id=ses_id, muzik_tema="genel")
    print(f"ÖNİZLEME TAMAM ✓  {cikti}  ({os.path.getsize(cikti)//1024} KB)")
    print("Bu video YouTube'a YÜKLENMEDİ; çalışmanın 'Artifacts' bölümünden "
          "onizleme.zip olarak indirilir.")


if __name__ == "__main__":
    main()
