#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub-native otomasyon (AI BAĞIMLILIĞI YOK).
senaryolar.json'daki hazır senaryolardan sıradakini alır -> video üretir ->
YouTube'a yükler -> sırayı ilerletir. Ayarlar: config.json
"""
import os, json, tempfile, io, sys
import video as V

SENARYOLAR = "senaryolar.json"
DURUM = "durum.json"
LOG = io.StringIO()


def _senaryolar():
    with open(SENARYOLAR, encoding="utf-8-sig") as f:
        return json.load(f)


def _durum():
    if os.path.exists(DURUM):
        with open(DURUM, encoding="utf-8-sig") as f:
            return json.load(f)
    return {"sonraki": 0}


def _durum_yaz(durum):
    durum["son_rapor"] = LOG.getvalue()[-1800:]
    with open(DURUM, "w", encoding="utf-8") as f:
        json.dump(durum, f, ensure_ascii=False, indent=2)


def main():
    with open("config.json", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    senaryolar = _senaryolar()
    durum = _durum()
    n = len(senaryolar)
    yapilan = set(durum.get("yapilan", []))
    idx = durum.get("sonraki", 0) % n
    denendi = 0
    while senaryolar[idx]["baslik"] in yapilan and denendi < n:
        idx = (idx + 1) % n
        denendi += 1
    if denendi >= n:
        print("✓ Tüm konular yayınlanmış! Yeni içerik için senaryolar.json'a konu ekleyin.")
        _durum_yaz(durum)
        return
    veri = senaryolar[idx]
    print(f"[1/3] Senaryo ({idx+1}/{n}): {veri['baslik']}")

    tmp = tempfile.mkdtemp()
    sp = os.path.join(tmp, "script.txt")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(veri["script"])
    os.makedirs("output", exist_ok=True)
    cikti = "output/video.mp4"
    print("[2/3] Video üretiliyor ...")
    V.uret_video(sp, cikti,
                 ses=cfg.get("ses", "erkek"),
                 dikey=(cfg.get("format", "dikey") == "dikey"),
                 hiz=str(cfg.get("hiz", "+15%")),
                 sahneler=veri.get("sahneler"),
                 animasyon=bool(cfg.get("animasyon", True)),
                 cocuk=bool(cfg.get("cocuk_icerigi", False)),
                 tonlama=str(cfg.get("tonlama", "+0Hz")),
                 gorsel_stil=str(cfg.get("gorsel_stil", "stok")))
    print(f"      Çıktı: {cikti}  ({os.path.getsize(cikti)//1024} KB)")

    kapak_yolu = None
    try:
        import kapak as K
        kapak_yolu = K.kapak_uret(cikti, veri["baslik"], "output/kapak.jpg")
        print(f"      Kapak: {kapak_yolu}")
    except Exception as e:
        print(f"      Kapak üretilemedi: {str(e)[:120]}")

    if cfg.get("yukleme_atla"):
        print("[3/3] ÖNİZLEME MODU — yükleme atlandı (kanal kirlenmez)")
        try:
            import shutil, subprocess
            shutil.copy(cikti, "onizleme.mp4")
            if kapak_yolu and os.path.exists(kapak_yolu):
                shutil.copy(kapak_yolu, "onizleme_kapak.jpg")
            for c in (["git","config","user.name","bot"],
                      ["git","config","user.email","bot@users.noreply.github.com"],
                      ["git","add","onizleme.mp4","onizleme_kapak.jpg"],
                      ["git","commit","-m","onizleme"], ["git","push"]):
                subprocess.run(c, check=False)
            print("      onizleme.mp4 repoya kaydedildi — indirip izleyebilirsin")
        except Exception as e:
            print(f"      Önizleme kaydedilemedi: {str(e)[:100]}")
        _durum_yaz(durum)
        print("TANI TAMAM ✓")
        return

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

    # TikTok/Reels icin: videoyu + kapagi repoya kaydet (elle indirilebilsin)
    try:
        import shutil, subprocess
        shutil.copy(cikti, "son_video.mp4")
        if kapak_yolu and os.path.exists(kapak_yolu):
            shutil.copy(kapak_yolu, "son_kapak.jpg")
        for c in (["git","config","user.name","bot"],
                  ["git","config","user.email","bot@users.noreply.github.com"],
                  ["git","add","son_video.mp4","son_kapak.jpg"],
                  ["git","commit","-m",f"son video: {veri['baslik'][:40]}"],
                  ["git","push"]):
            subprocess.run(c, check=False)
        print("      son_video.mp4 repoya kaydedildi (TikTok/Reels icin indirilebilir)")
    except Exception as e:
        print(f"      Video repoya kaydedilemedi: {str(e)[:100]}")

    yapilan.add(veri["baslik"])
    durum["yapilan"] = sorted(yapilan)
    durum["sonraki"] = (idx + 1) % n
    _durum_yaz(durum)
    print(f"TAMAM ✓  (yapılan: {len(yapilan)}/{n}, sıradaki: {durum['sonraki']})")


if __name__ == "__main__":
    import traceback, subprocess
    class Tee:
        def __init__(self, *s): self.s = s
        def write(self, x):
            for st in self.s:
                try: st.write(x)
                except Exception: pass
        def flush(self):
            for st in self.s:
                try: st.flush()
                except Exception: pass
    sys.stdout = Tee(sys.__stdout__, LOG)
    sys.stderr = Tee(sys.__stderr__, LOG)
    try:
        main()
    except BaseException:
        LOG.write("\n" + traceback.format_exc())
        try:
            d = _durum(); d["son_rapor"] = LOG.getvalue()[-1800:]
            open(DURUM, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2))
        except Exception: pass
        open("hata.log", "w", encoding="utf-8").write(traceback.format_exc())
        for c in (["git","config","user.name","bot"],
                  ["git","config","user.email","bot@users.noreply.github.com"],
                  ["git","add","-A"], ["git","commit","-m","tani/hata"], ["git","push"]):
            subprocess.run(c, check=False)
        raise
