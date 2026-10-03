#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub-native otomasyon (AI BAĞIMLILIĞI YOK).
senaryolar.json'daki hazır senaryolardan sıradakini alır -> video üretir ->
YouTube'a yükler -> sırayı ilerletir. Ayarlar: config.json
"""
import os, json, tempfile, io, sys, re, unicodedata, hashlib
import video as V

SENARYOLAR = "senaryolar.json"
DURUM = "durum.json"
LOG = io.StringIO()
LOCK = ".otomasyon.lock"

_KONU_STOP = {
    "NEDEN", "NASIL", "TUZAĞI", "TUZAK", "GİZLİ", "GERÇEK", "GERÇEKTE",
    "SENİ", "KADAR", "DAHA", "İLE", "BİR", "NEDİR", "VAR", "YOK", "İLAVE",
    "EDİLEN", "AYLIK", "GÜNDE", "GERÇEKTEN", "KİM", "HANGİ", "NELER",
    "ÖNÜNDE", "İÇİN", "OLAN", "OLUR", "GİDER", "MALİYET",
}


def _konu_kokleri(baslik):
    metin = re.sub(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü ]", " ", (baslik or "").upper())
    return {kelime[:4] for kelime in metin.split()
            if len(kelime) >= 4 and kelime not in _KONU_STOP}


def _konu_tekrari(baslik, kullanilan_basliklar):
    kokler = _konu_kokleri(baslik)
    if len(kokler) < 2:
        return None
    for eski in kullanilan_basliklar or []:
        if eski and len(kokler & _konu_kokleri(eski)) >= 2:
            return eski
    return None


def _kilit_al():
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True
    except FileExistsError:
        try:
            with open(LOCK, encoding="utf-8") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
        except (FileNotFoundError, ProcessLookupError, ValueError, PermissionError):
            try:
                os.unlink(LOCK)
            except FileNotFoundError:
                pass
            return _kilit_al()
        return False


def _kilit_birak():
    try:
        os.unlink(LOCK)
    except FileNotFoundError:
        pass


def _senaryolar():
    with open(SENARYOLAR, encoding="utf-8-sig") as f:
        base = json.load(f)
    oncelik_yolu = "senaryolar_oncelik.json"
    if os.path.exists(oncelik_yolu):
        try:
            with open(oncelik_yolu, encoding="utf-8-sig") as f:
                ekstra = json.load(f) or []
            if isinstance(ekstra, list) and ekstra:
                gorulen = {s.get("baslik") for s in base}
                ekstra = [s for s in ekstra if s.get("baslik") not in gorulen]
                base = ekstra + base
                print(f"      Öncelik senaryoları eklendi: {len(ekstra)}")
        except Exception as e:
            print(f"      Öncelik senaryoları okunamadı: {str(e)[:100]}")
    return base


def _durum():
    if os.path.exists(DURUM):
        with open(DURUM, encoding="utf-8-sig") as f:
            return json.load(f)
    return {"yapilan": []}


def _durum_yaz(durum):
    durum["son_rapor"] = LOG.getvalue()[-1800:]
    with open(DURUM, "w", encoding="utf-8") as f:
        json.dump(durum, f, ensure_ascii=False, indent=2)


def _sonraki_yayin_zamani(cfg):
    from datetime import datetime, timezone, timedelta
    saatler = cfg.get("yayin_saatleri_utc")
    if not saatler:
        tek = cfg.get("yayin_saati_utc")
        saatler = [tek] if tek else []
    adaylar = []
    now = datetime.now(timezone.utc)
    TOLERANS = timedelta(hours=4)
    for saat in saatler:
        try:
            hh, mm = map(int, str(saat).split(":"))
        except Exception:
            continue
        h = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if h + TOLERANS < now:
            h += timedelta(days=1)
            adaylar.append(h)
        elif h > now:
            adaylar.append(h)
    if not adaylar:
        return None
    return min(adaylar).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hedef_slot(cfg, yayin_zamani):
    """Bu koşunun dolduracağı slotun 'HH:MM' (UTC) değeri. Planlı yayında
    yayin_zamani'ndan; slot kaçmışsa (yayin_zamani yok) son 4 saatteki slottan."""
    if yayin_zamani:
        return yayin_zamani[11:16]
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    for saat in (cfg.get("yayin_saatleri_utc") or []):
        try:
            hh, mm = map(int, str(saat).split(":"))
        except Exception:
            continue
        h = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if timedelta(0) <= now - h <= timedelta(hours=4):
            return f"{hh:02d}:{mm:02d}"
    return None


def main():
    with open("config.json", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    senaryolar = _senaryolar()
    durum = _durum()
    n = len(senaryolar)
    yapilan = set(durum.get("yapilan", []))
    ONCELIK = ("market", "kasa", "sinema", "otel", "reklam", "paket", "fiyat", "indirim",
               "istasyon", "akaryak", "kart", "kredi", "taksit", "abonelik", "çocuk", "cocuk",
               "oyun", "telefon", "fatura", "restoran", "kahve", "avm", "kargo", "site",
               "uygulama", "banka", "market", "tuzak")

    def _oncelik_skoru(baslik):
        bl = baslik.lower()
        skor = sum(1 for k in ONCELIK if k in bl)
        # Öneri sistemi: oneri_tema.json bonus/ceza — üretim saatine dokunmaz
        try:
            if os.path.exists("oneri_tema.json"):
                with open("oneri_tema.json", encoding="utf-8-sig") as _tf:
                    _tema = json.load(_tf) or {}
                skor += 2 * sum(1 for k in (_tema.get("bonus_kw") or []) if k in bl)
                skor -= 2 * sum(1 for k in (_tema.get("engelle_kw") or []) if k in bl)
        except Exception:
            pass
        return skor

    OKYANUS = ("okyanus", "deniz", "derin", "dalga", "balina", "köpekbalığı", "megalodon",
               "kraken", "denizaltı", "batık", "girdap", "mercan", "mariana", "marıana",
               "çukur", "titanik", "bermuda", "su altı", "sualtı", "buzul", "kutup",
               "canavar", "adası", "mavi del", "hayalet gemi", "bloop", "çember")

    def _tr_lower(s):
        return s.replace("İ", "i").replace("I", "ı").lower()

    def _okyanus_mu(baslik):
        bl = _tr_lower(baslik)
        return any(k in bl for k in OKYANUS)

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
        return s.get("tema", "tuzak")

    MARKA_TERIMLERI = (
        "market", "fiyat", "indirim", "ödeme", "ücret", "alışveriş", "ürün",
        "mağaza", "reyon", "raf", "sepet", "kasa", "restoran", "menü",
        "büfe", "sinema", "kart", "kredi", "banka", "faiz", "taksit",
        "kampanya", "kupon", "abonelik", "üyelik", "iade", "kargo", "garanti",
        "otopark", "kuaför", "berber", "uygulama", "site", "çerez", "wifi",
        "internet", "reklam", "kampanya", "para", "satış", "hizmet", "sözleşme",
        "ek ücret", "gizli ücret", "sana özel", "son iki", "bedava", "ücretsiz",
    )
    ZAYIF_BASLIK_TERIMLERI = ("müzik", "koku", "sağa", "yön", "hız", "kokunun")
    DOĞRUDAN_BASLIK_TERIMLERI = (
        "fiyat", "indirim", "ücret", "ödeme", "para", "ürün", "market", "reyon",
        "raf", "sepet", "kasa", "kart", "kredi", "banka", "taksit", "kampanya",
        "abonelik", "üyelik", "iade", "kargo", "garanti", "menü", "gizli tuzak",
        "ekstra", "bedava", "ücretsiz", "son iki", "sınırlı", "çerez",
    )

    def _marka_norm(metin):
        metin = unicodedata.normalize("NFC", str(metin))
        return metin.replace("İ", "I").replace("ı", "i").lower()

    def _marka_uygun_mu(s):
        metin = _marka_norm(" ".join(str(s.get(k, "")) for k in ("baslik", "aciklama", "script")))
        if not any(_marka_norm(t) in metin for t in MARKA_TERIMLERI):
            return False
        baslik = _marka_norm(s.get("baslik", ""))
        zayif = any(_marka_norm(t) in baslik for t in ZAYIF_BASLIK_TERIMLERI)
        dogrudan = any(_marka_norm(t) in baslik for t in DOĞRUDAN_BASLIK_TERIMLERI)
        return not zayif or dogrudan

    kalan = []
    for i, s in enumerate(senaryolar):
        baslik = s.get("baslik", "")
        if baslik in yapilan:
            continue
        eski = _konu_tekrari(baslik, yapilan)
        if eski:
            print(f"      · atlandı (yayınlanmış konu tekrarı ~ '{eski[:45]}'): {baslik[:55]}")
            continue
        kalan.append((i, s))
    if not kalan:
        print("✓ Tüm konular yayınlanmış!")
        _durum_yaz(durum)
        return
    tema_havuz = [t for t in kalan if _tema(t[1]) == "tuzak" and _marka_uygun_mu(t[1])]
    print(f"      Tema (katı marka filtresi): 'tuzak' (uygun kalan: {len(tema_havuz)})")
    if not tema_havuz:
        print("✓ Marka uyumlu tuzak senaryosu kalmadı.")
        _durum_yaz(durum)
        return

    # SLOT AYRIMI: marka serisi (Temu, Getir, A101...) yalnız marka slotunda
    # (varsayılan 12:00 TR = 09:00 UTC); diğer slotlar klasik tuzak konuları.
    # Marka serisi biterse marka slotu klasik havuzdan devam eder.
    _marka_slot = str(cfg.get("marka_slot_utc", "09:00") or "")
    _slot = _hedef_slot(cfg, _sonraki_yayin_zamani(cfg))
    _marka_modu = False
    if _marka_slot:
        _marka = [t for t in tema_havuz if t[1].get("seri") == "marka"]
        _klasik = [t for t in tema_havuz if t[1].get("seri") != "marka"]
        _marka_modu = _slot == _marka_slot and bool(_marka)
        if _marka_modu:
            tema_havuz = _marka
            print(f"      Slot {_slot} UTC: marka serisi (kalan: {len(_marka)})")
        elif _klasik:
            tema_havuz = _klasik
            print(f"      Slot {_slot or '?'} UTC: klasik tuzak (kalan: {len(_klasik)})")

    def _kohort(s):
        return s.get("uretim") or "v1"

    _kohort_map = {s.get("baslik", ""): _kohort(s) for s in senaryolar}
    _yayin = {"v1": 0, "v2": 0}
    for _b in yapilan:
        _yayin[_kohort_map.get(_b, "v1")] = _yayin.get(_kohort_map.get(_b, "v1"), 0) + 1
    _v1 = [x for x in tema_havuz if _kohort(x[1]) == "v1"]
    _v2 = [x for x in tema_havuz if _kohort(x[1]) == "v2"]
    if _v1 and _v2:
        _sec = "v2" if _yayin["v2"] <= _yayin["v1"] else "v1"
        tema_havuz = _v2 if _sec == "v2" else _v1
        print(f"      Kohort: {_sec}")
    elif _v2:
        tema_havuz = _v2
    else:
        print(f"      Kohort: v1")

    son_kat = durum.get("son_kategori")
    havuz = [t for t in tema_havuz if _kategori(t[1]["baslik"]) != son_kat] or tema_havuz
    havuz.sort(key=lambda t: (0 if _okyanus_mu(t[1]["baslik"]) else 1,
                              -_oncelik_skoru(t[1]["baslik"]), t[0]))
    if _marka_modu:   # marka serisi uzun video konu sırasıyla (A101, Temu, Amazon...)
        havuz = sorted(tema_havuz, key=lambda t: t[0])
    idx = havuz[0][0]
    force_yolu = "force_next.json"
    if os.path.exists(force_yolu):
        try:
            with open(force_yolu, encoding="utf-8-sig") as f:
                force = json.load(f) or {}
            hedef = (force.get("baslik") or "").strip()
            if hedef:
                for i, s in enumerate(senaryolar):
                    if s.get("baslik") == hedef and hedef not in yapilan:
                        idx = i
                        print(f"      force_next: zorunlu konu seçildi → {hedef[:60]}")
                        break
            try:
                os.unlink(force_yolu)
            except FileNotFoundError:
                pass
        except Exception as e:
            print(f"      force_next okunamadı: {str(e)[:100]}")
    veri = senaryolar[idx]
    durum["son_kategori"] = _kategori(veri["baslik"])
    print(f"[1/3] Senaryo ({idx+1}/{n}) [{durum['son_kategori']}]: {veri['baslik']}")

    yayin_zamani = _sonraki_yayin_zamani(cfg)
    import youtube_yukle as YT
    if yayin_zamani:
        mevcut_slot = YT.planli_slot_video(yayin_zamani)
        if mevcut_slot:
            print(f"✓ Yayın slotu zaten dolu ({yayin_zamani}); atlandı: https://youtu.be/{mevcut_slot}")
            _durum_yaz(durum)
            return
        if durum.get("son_yayin_zamani") == yayin_zamani and durum.get("son_video_id"):
            print(f"✓ Slot durum.json'da kayıtlı; atlandı")
            _durum_yaz(durum)
            return
    else:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        son_yz = durum.get("son_yayin_zamani") or ""
        for saat in (cfg.get("yayin_saatleri_utc") or []):
            try:
                hh, mm = map(int, str(saat).split(":"))
            except Exception:
                continue
            slot = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            slot_s = slot.strftime("%Y-%m-%dT%H:%M:%SZ")
            if son_yz == slot_s and durum.get("son_video_id"):
                if abs((now - slot).total_seconds()) < 6 * 3600:
                    print(f"✓ Bugünün slotu zaten üretildi; atlandı")
                    _durum_yaz(durum)
                    return

    tmp = tempfile.mkdtemp()
    sp = os.path.join(tmp, "script.txt")
    SABIT_CTA = (
        "Artık biliyorsun. Her gün 12:00 ve 20:00'de yeni bir tuzak. "
        "Abone ol, bir daha kanma."
    )
    script_metin = (veri.get("script") or "").strip()
    for eski_bitis in (
        "Yarın yeni bir tuzağı çözüyoruz, kaçırma.",
        "Yarın yeni bir tuzak. Abone ol, uyanık kal.",
        "Her akşam yeni bir tuzak. Abone ol, uyanık kal.",
        "Abone ol, uyanık kal. Yarın yeni bir tuzağı çözüyoruz, kaçırma.",
    ):
        if script_metin.endswith(eski_bitis):
            script_metin = script_metin[: -len(eski_bitis)].rstrip(" .")
            break
    if SABIT_CTA not in script_metin:
        script_metin = (script_metin.rstrip(" .") + " " + SABIT_CTA).strip()
    with open(sp, "w", encoding="utf-8") as f:
        f.write(script_metin)
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
                 ai_sahne=bool(cfg.get("ai_sahne", False)),
                 ai_fallback=bool(cfg.get("ai_gorsel_yedegi", True)))
    print(f"      Çıktı: {cikti}  ({os.path.getsize(cikti)//1024} KB)")

    kapak_yolu = None
    try:
        import kapak as K
        ai_bg = None
        if cfg.get("ai_kapak"):
            try:
                import nvidia_araclar as NA
                ai_bg = NA.kapak_arkaplani(veri["baslik"], veri.get("kanca", ""), "output/ai_kapak_bg.jpg")
            except Exception as e:
                print(f"      AI kapak atlandı: {str(e)[:100]}")
        kapak_yolu = K.kapak_uret(cikti, veri["baslik"], "output/kapak.jpg", arka_plan=ai_bg)
        print(f"      Kapak: {kapak_yolu}")
    except Exception as e:
        print(f"      Kapak üretilemedi: {str(e)[:120]}")

    if cfg.get("marka_ilk_kare", True) and kapak_yolu:
        try:
            cikti = K.ilk_kare_bas(cikti, kapak_yolu, sure=float(cfg.get("marka_ilk_kare_sn", 1.0)))
        except Exception as e:
            print(f"      İlk kare atlandı: {str(e)[:100]}")

    if cfg.get("yukleme_atla"):
        print("[3/3] ÖNİZLEME MODU"); _durum_yaz(durum); return

    yayin_zamani = _sonraki_yayin_zamani(cfg)
    if yayin_zamani:
        print(f"      Planlı yayın: {yayin_zamani} UTC")

    print("[3/3] YouTube'a yükleniyor ...")
    _bek = durum.get("bekleyen_yorum")
    if _bek and _bek.get("video_id"):
        try:
            YT.yorum_at(_bek["video_id"], _bek["metin"])
            print("✓ Onceki videoya abone yorumu eklendi")
            durum["bekleyen_yorum"] = None
        except Exception as _e:
            print("! Yorum eklenemedi: " + str(_e)[:160])

    try:
        import aciklama as ACK
        _aciklama = ACK.olustur(veri, cfg)
    except Exception:
        _aciklama = veri.get("aciklama", "")
    _vid = YT.planli_video_bul(veri["baslik"], yayin_zamani)
    if not _vid and yayin_zamani:
        _vid = YT.planli_slot_video(yayin_zamani)
    if _vid:
        print(f"✓ Slot dolu; atlandı: https://youtu.be/{_vid}")
    else:
        _vid = YT.yukle(cikti, veri["baslik"], _aciklama,
                 veri.get("etiketler") or [],
                 gizlilik=cfg.get("gizlilik", "private"),
                 kategori=str(cfg.get("kategori", "28")),
                 cocuk_icerigi=bool(cfg.get("cocuk_icerigi", False)),
                 kapak=kapak_yolu, yayin_zamani=yayin_zamani,
                 sentetik=bool(cfg.get("ai_beyani", True)))
    if cfg.get("oynatma_listesi", True):
        _LISTE = {"market": "🛒 Market & AVM Tuzakları", "finans": "💳 Banka & Kart Tuzakları",
                  "dijital": "📱 Dijital & Uygulama Tuzakları", "psikoloji": "🧠 Psikolojik Satış Oyunları",
                  "yeme": "🍔 Restoran & Yeme-İçme Tuzakları", "hizmet": "🏨 Hizmet & Abonelik Tuzakları"}
        _liste = ("🌊 Gizemler & Bilinmeyenler" if veri.get("tema") == "gizem"
                  else _LISTE.get(durum.get("son_kategori"), "🎯 Tüm Tuzaklar"))
        try:
            YT.oynatma_listesine_ekle(_vid, _liste)
        except Exception:
            pass
    try:
        import yorum_at as YORUM
        _yorum_metni = YORUM.yorum_metni_uret(veri)
    except Exception:
        _yorum_metni = f"{veri.get('baslik', '')} hakkında sen en çok hangi ayrıntıyı gözden kaçırıyorsun?"
    durum["bekleyen_yorum"] = {"video_id": _vid, "metin": _yorum_metni, "kaynak": "fallback",
        "hash": hashlib.sha1((_vid or "").encode()).hexdigest()[:16]}
    durum["son_video_id"] = _vid
    durum["son_baslik"] = veri["baslik"]
    durum["son_yayin_zamani"] = yayin_zamani or ""
    try:
        import shutil
        shutil.copy(cikti, "son_video.mp4")
        if kapak_yolu and os.path.exists(kapak_yolu):
            shutil.copy(kapak_yolu, "son_kapak.jpg")
    except Exception:
        pass
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
    if not _kilit_al():
        print("! Başka bir otomasyon çalışıyor."); raise SystemExit(0)
    try:
        main()
    except BaseException:
        LOG.write("\n" + traceback.format_exc())
        try:
            d = _durum(); d["son_rapor"] = LOG.getvalue()[-1800:]
            open(DURUM, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2))
        except Exception: pass
        open("hata.log", "w", encoding="utf-8").write(traceback.format_exc())
        for c in (["git","config","user.name","bot"], ["git","config","user.email","bot@users.noreply.github.com"],
                  ["git","add","-A"], ["git","commit","-m","tani/hata"], ["git","push"]):
            subprocess.run(c, check=False)
        raise
    finally:
        _kilit_birak()
