#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI KAPAK ÖNİZLEME (YÜKLEMEZ). NVIDIA image-gen ile örnek bir kapak üretir;
kaliteyi görüp beğenirsen config.json'da ai_kapak:true yaparız. Kanala DOKUNMAZ.

Çıktılar (workflow artifact olarak alınır):
  output/ai_kapak_bg.jpg   -> ham AI arka plan (üzerinde yazı yok)
  output/kapak_test.jpg    -> markalı/yazılı NİHAİ kapak (yayınlanacak hali)

Env: NVIDIA_API_KEY (image-gen için). BASLIK ile örnek başlık verilebilir.
"""
import os, json
import nvidia_araclar as NA
import kapak as K


def _ornek_baslik():
    b = os.environ.get("BASLIK", "").strip()
    if b:
        return b, ""
    try:
        with open("senaryolar.json", encoding="utf-8-sig") as f:
            hav = json.load(f)
        for s in hav:
            if s.get("baslik"):
                return s["baslik"], s.get("kanca", "")
    except Exception:
        pass
    return "MARKETTE BÜYÜK PAKET TUZAĞI", "daha pahalı"


def main():
    os.makedirs("output", exist_ok=True)
    baslik, kanca = _ornek_baslik()
    print(f"Örnek başlık: {baslik!r}  (kanca: {kanca!r})")
    print(f"NVIDIA anahtarı: {bool(NA.A._nvidia_key())} | görsel model: {NA.GORSEL_MODEL}")

    bg = NA.kapak_arkaplani(baslik, kanca, "output/ai_kapak_bg.jpg")
    if bg:
        print(f"✓ AI arka plan üretildi: {bg} ({os.path.getsize(bg)//1024} KB)")
    else:
        print("✗ AI arka plan ÜRETİLEMEDİ (anahtar/endpoint/model erişimi?). "
              "Nihai kapak düz zemine düşer; endpoint/model adını kontrol edelim.")

    # Video yok -> kapak_uret AI arka planı kullanır; yoksa düz zemine düşer.
    cikti = K.kapak_uret("__yok__.mp4", baslik, "output/kapak_test.jpg", arka_plan=bg)
    print(f"✓ Nihai kapak: {cikti} ({os.path.getsize(cikti)//1024} KB)")
    print("\nArtifact'ı indirip output/kapak_test.jpg'e bak. Beğenirsen "
          "config.json -> \"ai_kapak\": true yaparız; canlıda otomatik devreye girer.")
    # TEŞHİS SON: log aracı yalnızca çıktının SONUNU döndürüyor -> en sona bas.
    print("\n===== NVIDIA GORSEL TESHIS =====")
    for satir in NA.SON_TESHIS:
        print("  " + satir)
    print("================================")


if __name__ == "__main__":
    main()
