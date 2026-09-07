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
    # KANAL KİMLİĞİ = "TUZAK AVCISI": SADECE tuzak üret. Gizem içeriği hem
    # off-brand (abone tüketici tuzağı için geldi) hem en zayıf tema (ort. 528);
    # kanal kimliğini bozuyor. Öncelik sırası: tuzak -> (biterse) cesitlilik ->
    # (o da biterse, havuz boş kalmasın diye en son) gizem.
    istenen_tema = None
    tema_havuz = kalan
    for _t in ("tuzak", "cesitlilik", "gizem"):
        _h = [t for t in kalan if _tema(t[1]) == _t]
        if _h:
            istenen_tema, tema_havuz = _t, _h
            break
    print(f"      Tema (marka: sadece tuzak): '{istenen_tema}' "
          f"(tuzak kalan: {sum(1 for t in kalan if _tema(t[1])=='tuzak')})")
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
                 eleven_voice_id=str(cfg.get("kisa_ses_id", "")).strip() or None,
                 ai_sahne=bool(cfg.get("ai_sahne", False)))
    print(f"      Çıktı: {cikti}  ({os.path.getsize(cikti)//1024} KB)")

    kapak_yolu = None
    try:
        import kapak as K
        # AI KAPAK (opsiyonel, config.ai_kapak): NVIDIA image-gen ile özel dramatik
        # arka plan üret; başarısızsa None -> kapak videodan kare çıkarır (eski hal).
        ai_bg = None
        if cfg.get("ai_kapak"):
            try:
                import nvidia_araclar as NA
                ai_bg = NA.kapak_arkaplani(veri["baslik"], veri.get("kanca", ""),
                                           "output/ai_kapak_bg.jpg")
                if ai_bg:
                    print(f"      AI kapak arka planı üretildi ({NA.GORSEL_MODEL})")
            except Exception as e:
                print(f"      AI kapak atlandı: {str(e)[:100]}")
        kapak_yolu = K.kapak_uret(cikti, veri["baslik"], "output/kapak.jpg", arka_plan=ai_bg)
        print(f"      Kapak: {kapak_yolu}")
    except Exception as e:
        print(f"      Kapak üretilemedi: {str(e)[:120]}")

    # MARKALI İLK KARE: kapağı videonun başına ~1sn intro karesi olarak ekle
    # (Shorts özel kapak yerine kareyi gösterir -> ilk kare markalı olsun).
    if cfg.get("marka_ilk_kare", True) and kapak_yolu:
        try:
            cikti = K.ilk_kare_bas(cikti, kapak_yolu, sure=float(cfg.get("marka_ilk_kare_sn", 1.0)))
        except Exception as e:
            print(f"      İlk kare atlandı: {str(e)[:100]}")

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

    # PLANLI YAYIN: video 'private' yuklenir, en yakin gelecek slotta (publishAt)
    # otomatik public olur -> Studio'da "Planlanan"da gorunur, tam saatinde cikar.
    # yayin_saatleri_utc (liste) onceliklidir; yoksa tekil yayin_saati_utc; o da
    # yoksa aninda public. Cron slottan ~2 saat once uretir (gecikme payi).
    yayin_zamani = None
    saatler = cfg.get("yayin_saatleri_utc")
    if not saatler:
        _tek = cfg.get("yayin_saati_utc")
        saatler = [_tek] if _tek else []
    if saatler:
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        adaylar = []
        for _s in saatler:
            try:
                hh, mm = map(int, str(_s).split(":"))
            except Exception:
                continue
            h = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if h <= now + timedelta(minutes=10):
                h += timedelta(days=1)   # slot gecti -> ertesi gune kaydir
            adaylar.append(h)
        if adaylar:
            hedef = min(adaylar)         # en yakin gelecek slot
            yayin_zamani = hedef.strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"      Planlı yayın: {yayin_zamani} UTC")

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

    try:
        import aciklama as ACK
        _aciklama = ACK.olustur(veri, cfg)  # SEO + marka footer (CTA/saat/handle/hashtag)
    except Exception as e:
        print(f"      Açıklama şablonu atlandı: {str(e)[:100]}")
        _aciklama = veri.get("aciklama", "")
    _vid = YT.yukle(cikti, veri["baslik"], _aciklama,
             veri.get("etiketler") or [],
             gizlilik=cfg.get("gizlilik", "private"),
             kategori=str(cfg.get("kategori", "28")),
             cocuk_icerigi=bool(cfg.get("cocuk_icerigi", False)),
             kapak=kapak_yolu, yayin_zamani=yayin_zamani,
             sentetik=bool(cfg.get("ai_beyani", True)))
    # OYNATMA LİSTESİ: videoyu kategori/temasına göre listeye ekle (izlenme
    # süresi/oturum uzunluğu -> algoritma sever). Hata olursa yükleme bozulmaz.
    if cfg.get("oynatma_listesi", True):
        _LISTE = {"market": "🛒 Market & AVM Tuzakları",
                  "finans": "💳 Banka & Kart Tuzakları",
                  "dijital": "📱 Dijital & Uygulama Tuzakları",
                  "psikoloji": "🧠 Psikolojik Satış Oyunları",
                  "yeme": "🍔 Restoran & Yeme-İçme Tuzakları",
                  "hizmet": "🏨 Hizmet & Abonelik Tuzakları"}
        _liste = ("🌊 Gizemler & Bilinmeyenler" if veri.get("tema") == "gizem"
                  else _LISTE.get(durum.get("son_kategori"), "🎯 Tüm Tuzaklar"))
        try:
            YT.oynatma_listesine_ekle(_vid, _liste)
            print(f"      Oynatma listesine eklendi: {_liste}")
        except Exception as e:
            print(f"      Oynatma listesi atlandı: {str(e)[:120]}")
    # Yorum, video public olduktan SONRA atilir (ozel videoya yorum yasak).
    # Video ID + yorum metni durum.json'a yazilir; yorum.yml 19:15'te gonderir.
    durum["bekleyen_yorum"] = {
        "video_id": _vid,
        "metin": (f"{veri.get('kanca','Bu tuzağı biliyor muydun?')}\n\n"
                  "Sen bu tuzağa hiç düştün mü? Yorumla \U0001F447\n"
                  "\U0001F514 Her gün yeni tüketici tuzakları — ABONE OL, kaçırma!"),
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
