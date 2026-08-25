#!/usr/bin/env python3
"""50/50 STOK DAĞILIM TESTİ — YouTube'a DOKUNMAZ.

senaryolar.json'dan sıradaki (henüz yapılmamış) gerçek konuyu alır, sahnelerinin
görsellerini GERÇEK Pexels + Pixabay anahtarlarıyla indirir ve hangi sahnenin hangi
kaynaktan geldiğini + toplam dağılımı log'a yazar. Ses/altyazı/render/yükleme YOK.

GitHub Actions'ta 'Dagilim Testi (50/50)' workflow'u ile elle tetiklenir.
YT secret'ları bu workflow'a verilmez -> yükleme fiziksel olarak mümkün değildir.
"""
import json
import os
import tempfile

import video

SENARYOLAR = "senaryolar.json"
DURUM = "durum.json"


def _sirada_ki_senaryo():
    with open(SENARYOLAR, encoding="utf-8-sig") as f:
        senaryolar = json.load(f)
    yapilan = set()
    if os.path.exists(DURUM):
        with open(DURUM, encoding="utf-8-sig") as f:
            yapilan = set(json.load(f).get("yapilan", []))
    kalan = [s for s in senaryolar if s.get("baslik") not in yapilan]
    return (kalan or senaryolar)[0]


def main():
    pk = video._pexels_key()
    xk = video._pixabay_key()
    print(f"[anahtarlar] pexels={pk[:6]}..len{len(pk)}  pixabay={xk[:6]}..len{len(xk)}")
    if not pk:
        print("UYARI: PEXELS_API_KEY yok -> tüm sahneler Pixabay'e düşer.")
    if not xk:
        print("UYARI: PIXABAY_API_KEY yok -> tüm sahneler Pexels'e düşer.")

    sc = _sirada_ki_senaryo()
    sahneler = sc.get("sahneler") or []
    print(f"\nSıradaki konu: {sc.get('baslik', '(başlıksız)')}")
    print(f"Sahne sayısı: {len(sahneler)}")
    print("Görsel tarifleri:")
    for i, s in enumerate(sahneler):
        print(f"  {i}: {s.get('gorsel') or s.get('metin', '')[:60]}")

    boyut = (1080, 1920)  # dikey / Shorts
    dikey = boyut[1] > boyut[0]
    tmp = tempfile.mkdtemp(prefix="dagilim_")
    print(f"\n[çıktı klasörü: {tmp}]\n{'=' * 60}")

    # Yalnızca stok seçim/dağılımını sınar (AI-kart yedeğine hiç girilmez).
    # sahne_gorselleri_hazirla ile AYNI kural: çift indeks Pexels, tek indeks Pixabay.
    prompts = [s.get("gorsel") or s.get("metin") or "" for s in sahneler if s]
    prompts = [p for p in prompts if p.strip()] or ["colorful scene"]
    sayac = {"pexels": 0, "pixabay": 0, "bulunamadi": 0}
    for i, p in enumerate(prompts):
        vpath = os.path.join(tmp, f"sahne_{i:03d}.mp4")
        oncelik = "pexels" if i % 2 == 0 else "pixabay"
        stok = video.stok_video_ara(p, boyut, vpath, dikey=dikey, oncelik=oncelik)
        if stok:
            kaynak = stok[0]
            sayac[kaynak] += 1
            tercih = "tercih" if kaynak == oncelik else "yedek"
            print(f"  Sahne {i + 1}/{len(prompts)} (öncelik={oncelik}): ✓ {kaynak} ({tercih})")
        else:
            sayac["bulunamadi"] += 1
            print(f"  Sahne {i + 1}/{len(prompts)} (öncelik={oncelik}): stok bulunamadı "
                  f"-> gerçek üretimde AI görseline düşer")

    print("=" * 60)
    print(f"DAĞILIM: pexels={sayac['pexels']}  pixabay={sayac['pixabay']}  "
          f"bulunamadi={sayac['bulunamadi']}  / toplam {len(prompts)} sahne")
    if sayac["pexels"] and sayac["pixabay"]:
        print("✓ Video her iki kaynaktan da klip içeriyor (karışım sağlandı).")
    print("YouTube'a hiçbir şey yüklenmedi.")


if __name__ == "__main__":
    main()
