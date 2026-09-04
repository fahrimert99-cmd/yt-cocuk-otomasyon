#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""İNGİLİZCE SÜRÜM ÜRETİCİ (YÜKLEMEZ).

Bir 'tuzak' senaryosunu NVIDIA ile İngilizceye çevirip (nvidia_araclar.senaryo_cevir)
gerçek montaj yoluyla (stok/AI sahne + ElevenLabs ses + müzik) TAM bir English Short
üretir. Kanala YÜKLEMEZ; çıktıyı artifact + 'ingilizce-video' dalına bırakır ki
kalite görülüp dinlenebilsin.

NOT: Gerçek, otomatik bir İngilizce KANAL için AYRI bir YouTube kanalı ve o kanala
ait ayrı OAuth kimliği (YT_REFRESH_TOKEN vb. secret) gerekir. Bu araç yalnızca
İngilizce üretim YETENEĞİNİ uçtan uca kanıtlar; yükleme yapmaz.

KONU env verilirse başlığı eşleşen senaryo; yoksa rastgele bir 'tuzak' senaryosu.
"""
import os, json, tempfile, random
import video as V
import nvidia_araclar as NA


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
    print(f"[EN] Kaynak senaryo (TR): {s.get('baslik')}")
    en = NA.senaryo_cevir(s)
    if not en or not en.get("script"):
        raise SystemExit("Çeviri başarısız (NVIDIA erişimi/model?). İngilizce sürüm üretilemedi.")
    print(f"[EN] Translated title: {en.get('baslik')!r}  (hook: {en.get('kanca')!r})")
    print(f"[EN] Scenes: {len(en.get('sahneler') or [])}  | model: {NA.CEVIRI_MODEL}")

    tmp = tempfile.mkdtemp()
    sp = os.path.join(tmp, "script.txt")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(en["script"])
    os.makedirs("output", exist_ok=True)
    cikti = "output/ingilizce.mp4"
    ses_id = str(cfg.get("kisa_ses_id", "")).strip() or None   # Bill: İngilizce premade ses
    print("[EN] Gerçek montaj üretiliyor (ElevenLabs İngilizce ses + müzik + kurgu) ...")
    V.uret_video(sp, cikti, ses=cfg.get("ses", "erkek"), dikey=True,
                 hiz=str(cfg.get("hiz", "+6%")), sahneler=en.get("sahneler"),
                 animasyon=True, cocuk=bool(cfg.get("cocuk_icerigi", False)),
                 tonlama=str(cfg.get("tonlama", "+0Hz")),
                 gorsel_stil=str(cfg.get("gorsel_stil", "stok")), kanca=en.get("kanca"),
                 eleven_once=bool(cfg.get("kisa_eleven", True)),
                 eleven_voice_id=ses_id, muzik_tema="genel",
                 ai_sahne=bool(cfg.get("ai_sahne", False)))
    print(f"[EN] TAMAM ✓  {cikti}  ({os.path.getsize(cikti)//1024} KB)")
    print("Bu video YouTube'a YÜKLENMEDİ. Gerçek İngilizce kanal için ayrı OAuth "
          "kimliği gerekir.")


if __name__ == "__main__":
    main()
