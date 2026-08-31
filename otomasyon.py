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
    return {"yapilan": []}


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
    # ÖNCELİK: analizde en çok tutan/kanıtlı temalar (market, sinema, fiyat, reklam,
    # kasa, otel, akaryakıt, çocuk...) önce yayınlansın; kanal büyürken en güçlü
    # konular öne çıksın. Yapılanlar başlıkla atlanır (tekrar yok), sıra determenistik.
    ONCELIK = ("market", "kasa", "sinema", "otel", "reklam", "paket", "fiyat", "indirim",
               "istasyon", "akaryak", "kart", "kredi", "taksit", "abonelik", "çocuk", "cocuk",
               "oyun", "telefon", "fatura", "restoran", "kahve", "avm", "kargo", "site",
               "uygulama", "banka", "market", "tuzak")

    def _oncelik_skoru(baslik):
        bl = baslik.lower()
        return sum(1 for k in ONCELIK if k in bl)

    # OKYANUS ÖNCELİĞİ: kanalda en çok tutan format okyanus/deniz gizemi
    # ("Okyanusun Dibinde", "Bermuda" patladı). Gizem havuzunda su/deniz temalı
    # konular EN ÖNE gelsin; trend sıcakken bu damardan besle.
    OKYANUS = ("okyanus", "deniz", "derin", "dalga", "balina", "köpekbalığı", "megalodon",
               "kraken", "denizaltı", "batık", "girdap", "mercan", "mariana", "marıana",
               "çukur", "titanik", "bermuda", "su altı", "sualtı", "buzul", "kutup",
               "canavar", "adası", "mavi del", "hayalet gemi", "bloop", "çember")

    def _tr_lower(s):
        # Türkçe İ/I küçültme: "DENİZ".lower() -> "deni̇z" (birleşen nokta) olur ve
        # "deniz" alt dizisiyle eşleşmez. İ->i, I->ı ile önce düzelt.
        return s.replace("İ", "i").replace("I", "ı").lower()

    def _okyanus_mu(baslik):
        bl = _tr_lower(baslik)
        return any(k in bl for k in OKYANUS)

    # ÇEŞİTLİLİK (P4): benzer konular arka arkaya gelmesin -> izleyici yorgunluğu azalsın.
    # Her konuyu bir kategoriye ata; bir ÖNCEKİ videonun kategorisinden FARKLI bir
    # kategori tercih et. Böylece market->market->market yerine market->finans->dijital...
    KATEGORI = {
        "market": ("market", "kasa", "raf", "reyon", "sepet", "büfe", "labirent", "koku",
                   "müzik", "ışık", "vitrin", "manken", "boş raf", "sağa", "parfüm"),
        "finans": ("kart", "kredi", "banka", "faiz", "taksit", "puan", "hediye kart",
                   "nakit", "bozuk para", "kampanya", "9 ile", "9️⃣"),
        "dijital": ("uygulama", "internet", "telefon", "site", "oyun", "sosyal", "çerez",
                    "wifi", "kod", "sanal", "hesap", "ilk ay", "ilk model", "yeni model"),
        "psikoloji": ("reklam", "ünlü", "sana özel", "yeni", "sınırlı", "bedava", "kupon",
                      "karşılık", "çapa", "yıldız", "yorum"),
        "yeme": ("menü", "restoran", "kahve", "fast food", "mısır", "su", "büyük boy",
                 "orta", "açık büfe", "sinema"),
        "hizmet": ("kuaför", "berber", "otopark", "taksi", "garanti", "danışman", "iade",
                   "kargo", "düğün", "otel", "tatil", "havaalan", "spor salon", "abonelik",
                   "istasyon", "benzin", "wifi"),
    }

    def _kategori(baslik):
        bl = baslik.lower()
        for kat, kws in KATEGORI.items():
            if any(k in bl for k in kws):
                return kat
        return "diger"

    def _tema(s):
        # Tema: "tuzak" (tuketici tuzagi), "gizem" (gizem/gercek olaylar) ya da
        # "cesitlilik" (eski: tasarruf/'biliyor muydun'). Alan yoksa "tuzak".
        return s.get("tema", "tuzak")

    kalan = [(i, s) for i, s in enumerate(senaryolar) if s["baslik"] not in yapilan]
    if not kalan:
        print("✓ Tüm konular yayınlanmış! Yeni içerik için senaryolar.json'a konu ekleyin.")
        _durum_yaz(durum)
        return
    # GİZEM GEÇİŞİ (2 hafta): Shorts DEVAM eder ama tema yavaşça "tuzak" -> "gizem"
    # kayar (kanal, uzun videolarla aynı gizem konseptinde netleşsin).
    #   Faz1 (gün 0-3):  2 tuzak + 1 gizem
    #   Faz2 (gün 4-7):  yarı yarıya
    #   Faz3 (gün 8-11): 2 gizem + 1 tuzak
    #   Faz4 (gün 12+):  tamamen gizem
    # Başlangıç tarihi durum.json'a BİR KEZ yazılır (kalıcı). İstenen tema havuzu
    # boşsa diğer ana temaya düşer (crash yok).
    from datetime import date as _date
    if not durum.get("gizem_gecis_baslangic"):
        durum["gizem_gecis_baslangic"] = _date.today().isoformat()
    try:
        _gun = (_date.today() - _date.fromisoformat(durum["gizem_gecis_baslangic"])).days
    except Exception:
        _gun = 0
    sirada_no = len(yapilan) + 1  # bu uretilecek videonun sira numarasi (1-based)
    if _gun <= 3:
        istenen_tema = "gizem" if sirada_no % 3 == 0 else "tuzak"
    elif _gun <= 7:
        istenen_tema = "gizem" if sirada_no % 2 == 0 else "tuzak"
    elif _gun <= 11:
        istenen_tema = "tuzak" if sirada_no % 3 == 0 else "gizem"
    else:
        istenen_tema = "gizem"
    tema_havuz = [t for t in kalan if _tema(t[1]) == istenen_tema]
    if not tema_havuz:  # o tema bitmişse diğer ana temaya düş
        _diger = "tuzak" if istenen_tema != "tuzak" else "gizem"
        tema_havuz = [t for t in kalan if _tema(t[1]) == _diger] or kalan
    print(f"      Gizem geçişi: gün {_gun}, {sirada_no}. video -> '{istenen_tema}' "
          f"(gizem kalan: {sum(1 for t in kalan if _tema(t[1])=='gizem')})")
    son_kat = durum.get("son_kategori")
    # Önce bir önceki videodan FARKLI kategorideki konulara bak; yoksa tüm havuza.
    havuz = [t for t in tema_havuz if _kategori(t[1]["baslik"]) != son_kat] or tema_havuz
    # Sıralama: (1) okyanus/deniz temalı gizem konuları EN ÖNE (patlayan format),
    # (2) sonra öncelik skoru yüksek olanlar, (3) eşitlikte dosya sırası (deterministik).
    # Okyanus önceliği yalnızca gizem havuzunu etkiler: tuzak başlıkları su kelimesi
    # içermez, o yüzden tuzak fazında hiçbir değişiklik olmaz.
    havuz.sort(key=lambda t: (0 if _okyanus_mu(t[1]["baslik"]) else 1,
                              -_oncelik_skoru(t[1]["baslik"]), t[0]))
    idx = havuz[0][0]
    veri = senaryolar[idx]
    durum["son_kategori"] = _kategori(veri["baslik"])
    print(f"[1/3] Senaryo ({idx+1}/{n}) [{durum['son_kategori']}]: {veri['baslik']}")

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
                 gorsel_stil=str(cfg.get("gorsel_stil", "stok")),
                 kanca=veri.get("kanca"),
                 eleven_once=bool(cfg.get("kisa_eleven", True)),
                 eleven_voice_id=str(cfg.get("kisa_ses_id", "")).strip() or None)
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
    # --- Bekleyen yorum: onceki gunun videosu artik public, yorumu simdi at ---
    _bek = durum.get("bekleyen_yorum")
    if _bek and _bek.get("video_id"):
        try:
            YT.yorum_at(_bek["video_id"], _bek["metin"])
            print("✓ Onceki videoya abone yorumu eklendi: " + _bek["video_id"])
            durum["bekleyen_yorum"] = None
        except Exception as _e:
            print("! Yorum eklenemedi: " + str(_e)[:160])

    _vid = YT.yukle(cikti, veri["baslik"], veri.get("aciklama", ""),
             veri.get("etiketler", []),
             gizlilik=cfg.get("gizlilik", "private"),
             kategori=str(cfg.get("kategori", "28")),
             cocuk_icerigi=bool(cfg.get("cocuk_icerigi", False)),
             kapak=kapak_yolu, yayin_zamani=yayin_zamani)
    # Yorum, video public olduktan SONRA atilir (ozel videoya yorum yasak).
    # Video ID + yorum metni durum.json'a yazilir; yorum.yml 19:15'te gonderir.
    durum["bekleyen_yorum"] = {
        "video_id": _vid,
        "metin": (f"{veri.get('kanca','Bu tuzağı biliyor muydun?')}\n\n"
                  "Sen bu tuzağa hiç düştün mü? Yorumla \U0001F447\n"
                  "\U0001F514 Her akşam 19:00'da yeni bir tüketici tuzağı — ABONE OL, kaçırma!"),
    }
    # TikTok/Reels icin: videoyu + kapagi calisma dizinine kopyala.
    # NOT: Repoya COMMIT EDILMEZ — 18MB'lik mp4'ler git gecmisini sisiriyordu.
    # Workflow bu dosyalari "artifact" olarak yukler; oradan indirilebilir.
    try:
        import shutil
        shutil.copy(cikti, "son_video.mp4")
        if kapak_yolu and os.path.exists(kapak_yolu):
            shutil.copy(kapak_yolu, "son_kapak.jpg")
        print("      son_video.mp4 / son_kapak.jpg kaydedildi (workflow artifact olarak alinir)")
    except Exception as e:
        print(f"      Video kopyalanamadi: {str(e)[:100]}")

    yapilan.add(veri["baslik"])
    durum["yapilan"] = sorted(yapilan)
    _durum_yaz(durum)
    print(f"TAMAM ✓  (yapılan: {len(yapilan)}/{n})")


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
        # Basarili calisma: eski hata.log'u temizle ki gecmis hatalar
        # (or. suresi dolmus token) seni bir daha yaniltmasin.
        try:
            if os.path.exists("hata.log") and os.path.getsize("hata.log") > 0:
                open("hata.log", "w", encoding="utf-8").write("")
                for c in (["git","config","user.name","bot"],
                          ["git","config","user.email","bot@users.noreply.github.com"],
                          ["git","add","hata.log"],
                          ["git","commit","-m","hata.log temizlendi (basarili calisma)"],
                          ["git","push"]):
                    subprocess.run(c, check=False)
        except Exception:
            pass
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
