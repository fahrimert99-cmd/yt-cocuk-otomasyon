#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MANUS BESLEME — Manus ajanini kanal icin ELLE calisan is kollarinda kullanir.

Manus'un normal LLM'den farki: gercekten web'de GEZINIR, kaynak dogrular ve
rapor uretir. Bu yuzden burada yalnizca "arastirma gerektiren, seyrek, yuksek
degerli" isler ona verilir; gunluk video uretimi eskisi gibi ucuz/ucretsiz
saglayicilarla (NVIDIA -> Claude -> Gemini -> Pollinations) calismaya devam eder.

Modlar:
  ping      : anahtari en dusuk maliyetle dogrular (~5-15 kredi)
  senaryo   : web'den DOGRULANMIS yeni tuzak senaryolari uretip senaryolar.json'a ekler
  strateji  : analiz_rapor.json + havuzu okuyup buyume strateji raporu yazar
  rakip     : nis rakip/bosluk analizi raporu yazar

Kullanim:
  MOD=senaryo SAYI=6 PROFIL=lite python3 manus_besle.py
  python3 manus_besle.py strateji
"""
import os, re, sys, json, time, unicodedata
import manus_arac as M

CIKTI_RAPOR = {"senaryo": "manus_rapor.md", "strateji": "manus_strateji.md",
               "rakip": "manus_rakip.md"}

# Is kolu basina kredi tahmini. API gercek tuketimi bildirdiginde O kullanilir;
# bunlar yalnizca (a) gorev oncesi butce rezervasyonu ve (b) bildirilmediginde
# deftere islenecek deger icin.
# OLCULEN GERCEK MALIYETLER: ping ~3 kredi (kosu 35062848507); rakip 67 kredi /
# 861 sn (kosu 35066375092) — 14 dakikalik derin arastirma. Tahminler olculen
# degerin ~2 kati tutuluyor (guvenlik payi).
MOD_KREDI = {"ping": 5, "senaryo": 150, "strateji": 150, "rakip": 150}


# ---------------------------------------------------------------- yardimci
def _norm(s):
    """Baslik normalizasyonu (dedup icin) — trend.py ile ayni davranis hedefi."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


try:                                  # tercihen depodaki tek dogruluk kaynagi
    from trend import _gecerli        # noqa: F401  (googleapiclient gerektirir)
except Exception:                     # yerel ortamda bagimlilik yoksa esdegeri
    def _gecerli(d):
        if not isinstance(d, dict):
            return False
        if not (d.get("script") and d.get("baslik") and d.get("sahneler")):
            return False
        if len((d["script"] or "").split()) < 45:
            return False
        if not isinstance(d["sahneler"], list) or len(d["sahneler"]) < 4:
            return False
        return all(s.get("metin") and s.get("gorsel") for s in d["sahneler"])


def _json_oku(yol, vars_=None):
    try:
        with open(yol, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return vars_


def _kanal_kimligi():
    cfg = _json_oku("config.json", {}) or {}
    return (cfg.get("marka_ad") or "TUZAK AVCISI",
            cfg.get("marka_slogan") or "Her gün yeni bir tüketici tuzağı")


def _performans_ozet():
    """analiz_rapor.json'dan Manus'a verilecek kisa performans ozeti."""
    r = _json_oku("analiz_rapor.json", {}) or {}
    sat = []
    for v in (r.get("top10") or [])[:10]:
        sat.append(f"- {v.get('izlenme','?')} izlenme | {v.get('baslik','')[:70]}")
    zayif = [f"- {v.get('baslik','')[:70]}" for v in (r.get("son7gun") or [])[:5]]
    ozet = ""
    if sat:
        ozet += "EN COK IZLENEN VIDEOLARIMIZ:\n" + "\n".join(sat)
    if zayif:
        ozet += "\n\nSON 7 GUNDE EN DUSUK PERFORMANS:\n" + "\n".join(zayif)
    a = r.get("analytics") or {}
    if a:
        ozet += (f"\n\nSON 28 GUN: izlenme {a.get('izlenme','?')}, "
                 f"ort. retention %{a.get('retention_yuzde','?')}, "
                 f"abone kazanci {a.get('abone','?')}.")
    return ozet or "(henuz performans raporu yok)"


def _mevcut_basliklar(n=70):
    havuz = _json_oku("senaryolar.json", []) or []
    return [s.get("baslik", "") for s in havuz][-n:], havuz


# ------------------------------------------------------------------ semalar
SENARYO_SEMA = {
    "type": "object",
    "properties": {
        "senaryolar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "baslik": {"type": "string"},
                    "kanca": {"type": "string"},
                    "aciklama": {"type": "string"},
                    "etiketler": {"type": "array", "items": {"type": "string"}},
                    "script": {"type": "string"},
                    "sahneler": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"metin": {"type": "string"},
                                           "gorsel": {"type": "string"}},
                            "required": ["metin", "gorsel"],
                        },
                    },
                    "kaynaklar": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["baslik", "kanca", "aciklama", "etiketler",
                             "script", "sahneler", "kaynaklar"],
            },
        },
        "arastirma_ozeti": {"type": "string"},
    },
    "required": ["senaryolar", "arastirma_ozeti"],
}


# ----------------------------------------------------------------- promptlar
def _senaryo_prompt(sayi):
    marka, slogan = _kanal_kimligi()
    mevcut, _ = _mevcut_basliklar()
    return f"""Sen "{marka}" adli Turk YouTube Shorts kanalinin arastirmaci icerik yazarisin.
Kanalin tek konusu: TUKETICI TUZAKLARI ({slogan}).

GOREVIN — once ARASTIR, sonra YAZ:
1) Web'de gez ve BUGUN Turkiye'de gecerli, GERCEK ve DOGRULANABILIR {sayi} adet
   tuketici tuzagi bul. Oncelik: son 12 ayda degisen uygulamalar, yeni yasal
   duzenlemeler, guncel fiyat/gramaj oyunlari, bankacilik/abonelik ucretleri,
   e-ticaret karanlik desenleri (dark pattern).
2) Her tuzak icin iddiani GUVENILIR kaynaga dayandir (resmi kurum, mevzuat,
   buyuk haber kaynagi, sirketin kendi sartlari). Kaynak URL'lerini yaz.
3) UYDURMA ISTATISTIK/SAYI VERME. Dogrulayamadigin sayiyi hic kullanma;
   emin olamadigin bir tuzagi listeye KOYMA — az ama saglam olsun.

YAZIM KURALLARI (kanalin uretim hatti bunlara gore calisir):
- "baslik": BUYUK HARF, sonunda konuya uygun bir emoji, ACIK merak sorusu
  (NE/NEDEN/NASIL/KIM...). Kapali evet-hayir sorusu KULLANMA. En fazla 60 karakter.
  Ornek kaliplar: "CIPS PAKETI NEDEN YARI BOS? 🥔", "KASA SIRASI NEDEN UZUN? 🧾"
- "kanca": EN FAZLA 3 KELIME, kapak yazisi olacak vurucu ifade.
- "script": 65-85 kelime, TEK paragraf, duz metin. ILK CUMLE en fazla 14 kelime
  ve dogrudan sok edici sonucla baslasin (kurulum/tanim cumlesi YASAK).
  Sonda MUTLAKA hem abone cagrisi hem "yarin yeni bir tuzak" teaser'i olsun.
- "sahneler": TAM 6 sahne. Her sahnenin "metin"i script'in sirali parcasi olsun
  (birlestirildiginde script'i vermeli). "gorsel" alani INGILIZCE, 2-5 kelimelik
  stok video arama terimi olsun ve konunun GERCEK anlamina uysun (ornek: web
  cerezi -> "cookie consent popup screen", yiyecek kurabiye DEGIL).
- "aciklama": 2-3 cumle + abone cagrisi. "etiketler": 6-10 Turkce etiket.
- TURKCE YAZIM KUSURSUZ olsun: c,g,i,I,o,s,u harflerini EKSIKSIZ kullan
  (guclu DEGIL guclu -> "güçlü"). ASCII'ye sadelestirme. Yalnizca "gorsel" Ingilizce.

BU BASLIKLAR HAVUZDA ZATEN VAR — AYNISINI VE BENZERINI URETME:
{chr(10).join('- ' + b for b in mevcut)}

KANAL PERFORMANS VERISI (kazanan kaliba benzet, zayif olandan kac):
{_performans_ozet()}

CIKTI: yalnizca su JSON. Baska hicbir sey yazma:
{{"senaryolar":[{{"baslik":"...","kanca":"...","aciklama":"...","etiketler":["..."],
"script":"...","sahneler":[{{"metin":"...","gorsel":"..."}}],"kaynaklar":["https://..."]}}],
"arastirma_ozeti":"bulgularin 5-8 cumlelik ozeti"}}"""


def _strateji_prompt():
    marka, slogan = _kanal_kimligi()
    mevcut, havuz = _mevcut_basliklar(40)
    return f"""Sen bir YouTube buyume stratejistisin. Musteri: "{marka}" adli Turk
YouTube Shorts kanali ({slogan}). Kanal gunde 2 Shorts yayinliyor, tamami
otomatik uretiliyor (yapay zeka senaryo + seslendirme + stok video).

ELINDEKI GERCEK VERI:
{_performans_ozet()}

HAVUZDAKI SON BASLIKLAR ({len(havuz)} senaryo var):
{chr(10).join('- ' + b for b in mevcut)}

GOREVIN — web'de arastirma yaparak (2026 guncel YouTube Shorts dinamikleri,
Turkiye'deki benzer kanallarin yaklasimi, Shorts algoritmasinin bilinen
davranislari) somut ve UYGULANABILIR bir buyume raporu yaz. Genel gecer
tavsiye ISTEMIYORUM; her maddeyi yukaridaki veriyle iliskilendir.

Rapor basliklari:
1. Tespit — verideki en onemli 3 bulgu (sayilarla).
2. Baslik & kanca — kanalin kazanan kaliplari, somut 10 ornek yeni baslik.
3. Retention — ilk 3 saniye ve kurgu icin 5 somut degisiklik onerisi.
4. Kapak/thumbnail — Shorts'ta gercekten etkili olan yaklasim.
5. Yayin ritmi ve seri fikri — abone donusumunu artiracak format.
6. Buyume tikanikligi — abone donusumu neden dusuk, ne degismeli.
7. 30 gunluk uygulama plani — hafta hafta, olculebilir hedeflerle.

Cikti: TURKCE, Markdown baslik yapisiyla, tam ve kusursuz Turkce imla ile
(c,g,i,I,o,s,u harfleri eksiksiz). Kullandigin kaynaklarin URL'lerini raporun
sonunda "Kaynaklar" basligi altinda listele. UYDURMA VERI KULLANMA.

CIKTI BICIMI — COK ONEMLI:
Raporu DOSYA OLARAK OLUSTURMA, kaydetme ya da bir dosya yoluna baglanti verme.
Raporun TAMAMINI, SON MESAJININ GOVDESINDE duz Markdown metni olarak yaz.
Yerel dosya yolu (/home/... gibi) iceren baglanti verirsen cikti KULLANILAMAZ.
Ilerleme/durum aciklamasi yazma; son mesajin dogrudan raporun kendisi olsun."""


def _rakip_prompt():
    marka, slogan = _kanal_kimligi()
    mevcut, _ = _mevcut_basliklar(40)
    return f"""Sen bir icerik pazari analistisin. Musteri: "{marka}" adli Turk
YouTube Shorts kanali ({slogan}) — tuketici tuzaklari nisinde.

GOREVIN — web'de ve YouTube'da gercekten arastirma yaparak nis rekabet analizi yap:
1. Turkiye'de bu nisde (tuketici haklari, market/banka tuzaklari, fiyat oyunlari,
   dark pattern ifsalari) uretim yapan kanallari bul: yaklasik abone araligi,
   yayin sikligi, format ve en cok izlenen video kaliplari.
2. Ayni nisde ULUSLARARASI (ozellikle ABD/Ingiltere) kanitlanmis formatlari bul
   ve bunlardan Turkiye'de HENUZ UYGULANMAYANLARI isaretle (fikir arbitraji).
3. ICERIK BOSLUGU: asagidaki havuzumuzda olmayan, talebi olan konu kumeleri.
4. Kanalimizin farklilasma acisi ne olmali — 3 secenek, artilari/eksileriyle.
5. Hemen uretilebilecek 15 somut video fikri (baslik + tek cumlelik aci),
   her biri hangi bosluga denk geliyor belirt.

HAVUZUMUZDAKI SON BASLIKLAR:
{chr(10).join('- ' + b for b in mevcut)}

Cikti: TURKCE Markdown rapor, kusursuz Turkce imla ile. Kanal/video iddialarini
kaynak URL ile destekle; emin olmadigin rakamı yazma. Raporun sonunda
"Kaynaklar" basliginda URL listesi ver.

CIKTI BICIMI — COK ONEMLI:
Raporu DOSYA OLARAK OLUSTURMA, kaydetme ya da bir dosya yoluna baglanti verme.
Raporun TAMAMINI, SON MESAJININ GOVDESINDE duz Markdown metni olarak yaz.
Yerel dosya yolu (/home/... gibi) iceren baglanti verirsen cikti KULLANILAMAZ.
Ilerleme/durum aciklamasi yazma; son mesajin dogrudan raporun kendisi olsun."""


# --------------------------------------------------------------------- modlar
def _rapor_yaz(yol, baslik, govde, meta):
    with open(yol, "w", encoding="utf-8") as f:
        f.write(f"# {baslik}\n\n")
        f.write(f"> Manus ajani ile uretildi · {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} "
                f"· profil `{meta.get('profil')}` · ~{meta.get('kredi')} kredi"
                f"{' (tahmini)' if meta.get('kredi_tahmini') else ''}\n\n")
        f.write((govde or "").strip() + "\n")
    print(f"      Rapor yazildi: {yol}")


def mod_ping(profil):
    d, kaynak = M.butce_kontrol("lite", tahmin=MOD_KREDI["ping"])
    veri, metin, meta = M.calistir(
        "Sadece su tek kelimeyi yaz, baska hicbir sey yazma: TAMAM",
        profil="lite", baslik="anahtar testi", zaman_asimi=600, aralik=10,
        tahmin=MOD_KREDI["ping"])
    print(f"      Yanit: {(metin or '')[:200]!r}")
    M.butce_isle(d, "ping", meta, kaynak)
    return 0


def mod_senaryo(profil, sayi):
    d, kaynak = M.butce_kontrol(profil, tahmin=MOD_KREDI["senaryo"])
    veri, metin, meta = M.calistir(_senaryo_prompt(sayi), sema=SENARYO_SEMA,
                                   profil=profil, baslik=f"{sayi} yeni tuzak senaryosu",
                                   tahmin=MOD_KREDI["senaryo"])
    d = M.butce_isle(d, "senaryo", meta, kaynak)

    if isinstance(veri, list):
        veri = {"senaryolar": veri}
    yeni = (veri or {}).get("senaryolar") if isinstance(veri, dict) else None
    if not yeni:
        raise SystemExit("Manus gecerli senaryo JSON'u dondurmedi.\n"
                         f"Ham cikti (ilk 800): {(metin or '')[:800]}")

    havuz = _json_oku("senaryolar.json", []) or []
    mevcut_norm = {_norm(s.get("baslik", "")) for s in havuz}
    eklenen, elenen = [], []
    for s in yeni:
        if not isinstance(s, dict):
            continue
        bas = (s.get("baslik") or "").strip()
        if not bas:
            continue
        if _norm(bas) in mevcut_norm:
            elenen.append(f"{bas} (havuzda var)")
            continue
        # kanca 3 kelime kurali (kapak/acilis kisa-vurucu)
        kk = (s.get("kanca") or "").split()
        s["kanca"] = " ".join(kk[:3]) if kk else bas.split("?")[0][:24]
        et = s.get("etiketler")
        et = [str(x).strip() for x in et if str(x).strip()] if isinstance(et, list) else []
        for z in ("tuzak", "tüketici", "tasarruf"):
            if z not in et:
                et.append(z)
        s["etiketler"] = et[:12]
        s["tema"] = s.get("tema") or "tuzak"
        s["kaynak"] = "manus"
        if not _gecerli(s):
            elenen.append(f"{bas} (sema/kalite)")
            continue
        havuz.append(s)
        mevcut_norm.add(_norm(bas))
        eklenen.append(s)

    if eklenen:
        with open("senaryolar.json", "w", encoding="utf-8") as f:
            json.dump(havuz, f, ensure_ascii=False, indent=2)
        print(f"      senaryolar.json'a {len(eklenen)} senaryo eklendi (toplam {len(havuz)}).")
    else:
        print("      Eklenecek yeni senaryo yok.")

    govde = ["## Eklenen senaryolar\n"]
    for s in eklenen:
        govde.append(f"### {s['baslik']}\n- **Kanca:** {s['kanca']}\n"
                     f"- **Kaynaklar:** " +
                     (", ".join(f"<{u}>" for u in (s.get("kaynaklar") or [])) or "—"))
    if elenen:
        govde.append("\n## Elenenler\n" + "\n".join(f"- {e}" for e in elenen))
    ozet = (veri or {}).get("arastirma_ozeti") if isinstance(veri, dict) else ""
    if ozet:
        govde.append("\n## Arastirma ozeti\n" + str(ozet))
    _rapor_yaz(CIKTI_RAPOR["senaryo"], "Manus Senaryo Besleme", "\n".join(govde), meta)

    # Dogrulayici ile son kontrol (bozuk kayit repoya girmesin).
    try:
        import senaryolar_validator as V
        gecerli, hatalar = V.SenaryoValidator.validate_file("senaryolar.json")
        if hatalar:
            print(f"      [uyari] dogrulayici {len(hatalar)} uyari verdi (ilk 5):")
            for h in hatalar[:5]:
                print(f"        · {h}")
        print(f"      Dogrulayici: {len(gecerli)} gecerli senaryo.")
    except Exception as e:
        print(f"      [uyari] dogrulayici calistirilamadi: {str(e)[:120]}")
    return 0 if eklenen else 0


def mod_rapor(mod, profil):
    prompt = _strateji_prompt() if mod == "strateji" else _rakip_prompt()
    baslik = ("Kanal Buyume Stratejisi" if mod == "strateji" else "Nis Rakip & Bosluk Analizi")
    d, kaynak = M.butce_kontrol(profil, tahmin=MOD_KREDI[mod])
    veri, metin, meta = M.calistir(prompt, profil=profil, baslik=baslik,
                                   zaman_asimi=3000, aralik=25, tahmin=MOD_KREDI[mod])
    d = M.butce_isle(d, mod, meta, kaynak)
    govde = metin or (json.dumps(veri, ensure_ascii=False, indent=2) if veri else "")
    if not govde.strip():
        raise SystemExit("Manus bos rapor dondurdu.")
    # Ajan raporu kendi sanal makinesine DOSYA olarak yazdiysa sohbete yalnizca
    # bizim erisemedigimiz bir yerel yol dusuyor (kosu 35066375092'de yasandi).
    # Boyle bir cikti kullanilamaz — sessizce commit'lemek yerine acikca bildir.
    _yerel_yol = re.search(r"\]\(\s*/(home|tmp|root|var|mnt)/", govde)
    if _yerel_yol and len(govde) < 4000:
        raise SystemExit(
            "Manus raporu mesaj icinde DEGIL, kendi sanal makinesinde dosya olarak "
            f"uretmis (yerel yol baglantisi var, govde {len(govde)} karakter).\n"
            f"Raporun kendisi Manus panelinde duruyor: {meta.get('url')}\n"
            "Prompt 'dosya olusturma, mesaj govdesinde yaz' diyor; yine de olduysa "
            "gorevi tekrar calistir.")
    _rapor_yaz(CIKTI_RAPOR[mod], baslik, govde, meta)
    return 0


def main():
    mod = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MOD", "ping")).strip().lower()
    profil = (os.environ.get("PROFIL") or "lite").strip().lower()
    try:
        sayi = max(1, min(8, int(os.environ.get("SAYI") or 3)))
    except ValueError:
        sayi = 3
    print(f"[Manus] mod={mod} profil={profil} sayi={sayi}")
    if profil != "lite":
        print("      [uyari] ucretsiz planda yalnizca 'lite' (Manus 1.6 Lite) "
              "calisir; standart/max ucretli plan gerektirir.")
    if mod == "ping":
        return mod_ping(profil)
    if mod == "senaryo":
        return mod_senaryo(profil, sayi)
    if mod in ("strateji", "rakip"):
        return mod_rapor(mod, profil)
    raise SystemExit(f"Bilinmeyen mod: {mod} (ping|senaryo|strateji|rakip)")


if __name__ == "__main__":
    sys.exit(main())
