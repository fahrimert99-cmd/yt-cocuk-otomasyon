#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub-native otomasyon (AI BAĞIMLILIĞI YOK).
senaryolar.json'daki önceden hazırlanmış senaryolardan sıradakini alır ->
video üretir -> YouTube'a yükler -> sırayı ilerletir.
Hiçbir API anahtarı/kota gerektirmez. Ayarlar: config.json
"""
import os, json, tempfile
import video as V

SENARYOLAR = "senaryolar.json"
DURUM = "durum.json"


def _senaryolar():
    with open(SENARYOLAR, encoding="utf-8-sig") as f:
        return json.load(f)


def _durum():
    if os.path.exists(DURUM):
        with open(DURUM, encoding="utf-8-sig") as f:
            return json.load(f)
    return {"sonraki": 0}


def main():
    with open("config.json", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    senaryolar = _senaryolar()
    durum = _durum()
    n = len(senaryolar)
    yapilan = set(durum.get("yapilan", []))
    # ASLA TEKRAR ETME: sıradaki YAPILMAMIŞ konuyu bul
    idx = durum.get("sonraki", 0) % n
    denendi = 0
    while senaryolar[idx]["baslik"] in yapilan and denendi < n:
        idx = (idx + 1) % n
        denendi += 1
    if denendi >= n:
        print("✓ Tüm konular yayınlanmış! Tekrar üretilmedi. "
              "Yeni içerik için senaryolar.json'a konu ekleyin.")
        return
    veri = senaryolar[idx]
    print(f"[1/3] Senaryo ({idx+1}/{n}): {veri['baslik']}")

    tmp = tempfile.mkdtemp()
    sp = os.path.join(tmp, "script.txt")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(veri["script"])
    os.makedirs("output", exist_ok=True)
    cikti = "output/video.mp4"
    print("[2/3] Video üretiliyor (ses + görsel + alt yazı) ...")
    V.uret_video(sp, cikti,
                 ses=cfg.get("ses", "erkek"),
                 dikey=(cfg.get("format", "dikey") == "dikey"),
                 hiz=str(cfg.get("hiz", "+15%")),
                 sahneler=veri.get("sahneler"),
                 animasyon=bool(cfg.get("animasyon", True)),
                 cocuk=bool(cfg.get("cocuk_icerigi", False)),
                 tonlama=str(cfg.get("tonlama", "+0Hz")))
    print(f"      Çıktı: {cikti}  ({os.path.getsize(cikti)//1024} KB)")

    # Çarpıcı kapak fotoğrafı üret
    kapak_yolu = None
    try:
        import kapak as K
        kapak_yolu = K.kapak_uret(cikti, veri["baslik"], "output/kapak.jpg")
        print(f"      Kapak: {kapak_yolu}")
    except Exception as e:
        print(f"      Kapak üretilemedi (atlanıyor): {str(e)[:120]}")

    # Prime time zamanlı yayın: config'te yayin_saati_utc varsa, videoyu o saate planla
    yayin_zamani = None
    saat = cfg.get("yayin_saati_utc")
    if saat:
        from datetime import datetime, timezone, timedelta
        hh, mm = map(int, str(saat).split(":"))
        now = datetime.now(timezone.utc)
        hedef = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if hedef <= now + timedelta(minutes=10):
            hedef += timedelta(days=1)
        yayin_zamani = hedef.strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"      Prime time yayın: {yayin_zamani} UTC")

    print("[3/3] YouTube'a yükleniyor ...")
    import youtube_yukle as YT
    YT.yukle(cikti, veri["baslik"], veri.get("aciklama", ""),
             veri.get("etiketler", []),
             gizlilik=cfg.get("gizlilik", "private"),
             kategori=str(cfg.get("kategori", "28")),
             cocuk_icerigi=bool(cfg.get("cocuk_icerigi", False)),
             kapak=kapak_yolu, yayin_zamani=yayin_zamani)

    # Yayınlanan başlığı kaydet (bir daha asla üretilmez)
    yapilan.add(veri["baslik"])
    durum["yapilan"] = sorted(yapilan)
    durum["sonraki"] = (idx + 1) % n
    with open(DURUM, "w", encoding="utf-8") as f:
        json.dump(durum, f, ensure_ascii=False, indent=2)
    print(f"TAMAM ✓  (yapılan: {len(yapilan)}/{n}, sıradaki: {durum['sonraki']})")


if __name__ == "__main__":
    import traceback, subprocess
    try:
        main()
    except BaseException:
        open("hata.log", "w", encoding="utf-8").write(traceback.format_exc())
        for c in (["git","config","user.name","bot"],
                  ["git","config","user.email","bot@users.noreply.github.com"],
                  ["git","add","hata.log"], ["git","commit","-m","hata"], ["git","push"]):
            subprocess.run(c, check=False)
        raise
