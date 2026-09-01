#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Make tarafindan tetiklenir (GitHub repository_dispatch, event: 'uret').
Make senaryosu Gemini ile JSON senaryo uretir, base64'leyip gonderir.
Bu betik base64'u cozer, JSON'u ayristirir, videoyu uretir ve YouTube'a yukler.

Ortam degiskenleri:
  RAW_B64 -> Make'in gonderdigi base64(Gemini JSON ciktisi)
  YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN  (GitHub Secrets)
Ayarlar: config.json (format, ses, gizlilik, kategori)
"""
import os, re, json, base64, tempfile
import video as V


def _temizle(txt):
    txt = txt.strip()
    txt = re.sub(r"^```(json)?", "", txt).strip()
    txt = re.sub(r"```$", "", txt).strip()
    return txt


def _icerik_al():
    # KISAYOL: konu alanına "FRAGMAN" (veya TANITIM/TRAILER) yazılırsa kanal
    # fragmanı dosyasını yükle. (senaryo_dosya girdisi main'de olmadığından
    # "Run workflow" formunda görünmüyor; bu yol mevcut 'konu' girdisiyle çalışır.)
    _konu = os.environ.get("KONU", "").strip()
    if _konu.upper() in ("FRAGMAN", "TANITIM", "TRAILER"):
        with open("assets/marka/kanal_fragmani.json", encoding="utf-8-sig") as f:
            return json.load(f)
    # Elle "Run workflow": hazır senaryo dosyası yolu (ör. kanal fragmanı).
    dosya = os.environ.get("SENARYO_DOSYA", "").strip()
    if dosya and os.path.exists(dosya):
        with open(dosya, encoding="utf-8-sig") as f:
            return json.load(f)
    b64 = os.environ.get("RAW_B64", "").strip()
    if b64:
        ham = base64.b64decode(b64).decode("utf-8")
        return json.loads(_temizle(ham))
    if os.environ.get("SCRIPT", "").strip():
        return {
            "script":   os.environ.get("SCRIPT", ""),
            "baslik":   os.environ.get("BASLIK", "Video"),
            "aciklama": os.environ.get("ACIKLAMA", ""),
            "etiketler": json.loads(os.environ.get("ETIKETLER", "[]") or "[]"),
        }
    # Ne Make payload'i ne de hazir SCRIPT var (elle "Run workflow") ->
    # konudan Claude (yoksa Gemini) ile tam senaryo + sahneler uret.
    konu = os.environ.get("KONU", "").strip() or "SİNEMADA MISIR NEDEN PAHALI?"
    import uzun_script
    print(f"      [otomatik senaryo uretiliyor: {konu!r}]")
    return uzun_script.uret(konu)


def main():
    cfg = {}
    if os.path.exists("config.json"):
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)

    veri = _icerik_al()
    script = (veri.get("script") or "").strip()
    if not script:
        raise SystemExit("Senaryo metni bos - Make'ten icerik gelmedi.")
    baslik   = (veri.get("baslik") or "Video")[:100]
    etiketler = veri.get("etiketler") or []
    try:
        import aciklama as _ACK
        aciklama = _ACK.olustur(veri, cfg)  # SEO + marka footer
    except Exception:
        aciklama = veri.get("aciklama") or ""
    if isinstance(etiketler, str):
        etiketler = [e.strip() for e in etiketler.split(",") if e.strip()]

    dikey    = str(cfg.get("format", "dikey")).lower() == "dikey"
    # Elle calistirmada DIKEY env'i ile bicim secilebilir (uzun icin "hayir").
    _dv = os.environ.get("DIKEY", "").strip().lower()
    if _dv:
        dikey = _dv in ("1", "true", "evet", "dikey", "yes")
    ses      = cfg.get("ses", "kadin")
    # Senaryo kendi gizliliğini belirtebilir (ör. fragman -> "unlisted" ile
    # önce incele, sonra public yap). Yoksa config'ten.
    gizlilik = veri.get("gizlilik") or cfg.get("gizlilik", "private")
    kategori = str(cfg.get("kategori", "27"))
    cocuk = bool(cfg.get("cocuk_icerigi", False))
    animasyon = bool(cfg.get("animasyon", True))
    tonlama = str(cfg.get("tonlama", "+0Hz"))
    hiz = str(cfg.get("hiz", "+15%"))
    sahneler = veri.get("sahneler") or None

    print(f"[1/3] Icerik alindi ({len(script.split())} kelime). Baslik: {baslik}")

    tmp = tempfile.mkdtemp()
    sp = os.path.join(tmp, "script.txt")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(script)
    os.makedirs("output", exist_ok=True)
    cikti = "output/video.mp4"
    print("[2/3] Video uretiliyor (ElevenLabs oncelikli + alt yazi + FFmpeg) ...")
    # Ses ID: dikey (short) icin sabit kisa_ses_id (DUTY FREE'deki ses),
    # yatay (uzun) icin varsa uzun_ses_id; boylece bu yoldan cikan short'lar
    # da HER ZAMAN ayni sesle uretilir (otomasyon.py ile ayni davranis).
    _ses_id = (str(cfg.get("kisa_ses_id", "")).strip() if dikey
               else str(cfg.get("uzun_ses_id", "")).strip()) or None
    V.uret_video(sp, cikti, ses=ses, dikey=dikey, hiz=hiz,
                 sahneler=sahneler, animasyon=animasyon, cocuk=cocuk, tonlama=tonlama,
                 gorsel_stil=str(cfg.get("gorsel_stil", "stok")), kanca=veri.get("kanca"),
                 eleven_once=bool(cfg.get("eleven", True)),
                 eleven_voice_id=_ses_id)
    print(f"      Cikti: {cikti}  ({os.path.getsize(cikti)//1024} KB)")

    # Carpici kapak uret (dikey->kapak.py, yatay/uzun->kapak_uzun.py).
    # Boylece bu yoldan yuklenen videolar da ozel kapakli olur (otomatik
    # kare yerine). Kapak uretilemezse video yine yuklenir.
    kapak_yolu = None
    try:
        if dikey:
            import kapak as K
        else:
            import kapak_uzun as K
        kapak_yolu = K.kapak_uret(cikti, baslik, "output/kapak.jpg")
        print(f"      Kapak: {kapak_yolu}")
    except Exception as e:
        print(f"      Kapak uretilemedi: {str(e)[:120]}")

    # MARKALI İLK KARE (yalnizca dikey/Shorts; kapak.py ilk_kare_bas'a sahip):
    if dikey and kapak_yolu and cfg.get("marka_ilk_kare", True):
        try:
            cikti = K.ilk_kare_bas(cikti, kapak_yolu, sure=float(cfg.get("marka_ilk_kare_sn", 1.0)))
        except Exception as e:
            print(f"      Ilk kare atlandi: {str(e)[:100]}")

    print("[3/3] YouTube'a yukleniyor ...")
    import youtube_yukle as YT
    YT.yukle(cikti, baslik, aciklama, etiketler, gizlilik=gizlilik, kategori=kategori,
             cocuk_icerigi=cocuk, kapak=kapak_yolu)
    print("TAMAM :)")


if __name__ == "__main__":
    main()
