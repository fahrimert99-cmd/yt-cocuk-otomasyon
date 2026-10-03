# uzun_otomasyon.py — OTONOM uzun (yatay 8-12 dk) video hatti — TUKETICI BELGESELI.
# "<Marka> Neden ...?" hikayesi + tuketiciye kurulan tuzak + korunma rehberi
# (config.uzun_tema; eski ~3 dk gizem hatti icin "gizem").
# ⚠️ Yayin GUVENLI: ilk testlerde config.json'da "uzun_gizlilik":"unlisted" birak;
#    begenince "private" (haftalik zamanlanmis public) yap.
# - Kisa (Shorts) sistemden BAGIMSIZDIR: kendi konu bankasindan (uzun_konular.json) beslenir.
# - Kendi durumunu uzun_durum.json'da tutar (durum.json'a dokunmaz).
# - Elle script override: uzun_scripts/<slug>.json varsa onu kullanir.
import os, json, tempfile
from datetime import datetime, timezone, timedelta, date
import video as V
import youtube_yukle as YT
import uzun_script

CFG_P="config.json"; KONU_P="uzun_konular.json"; UZUN_P="uzun_durum.json"

def _load(p,d):
    try:
        with open(p,encoding="utf-8-sig") as f: return json.load(f)
    except Exception: return d
def _save(u):
    with open(UZUN_P,"w",encoding="utf-8") as f: json.dump(u,f,ensure_ascii=False,indent=2)

import re as _re, unicodedata as _ud
def _slug(t):
    t=_ud.normalize("NFKD",t).encode("ascii","ignore").decode().lower()
    return _re.sub(r"[^a-z0-9]+","-",t).strip("-")

def _sonraki_konu(u):
    """uzun_konular.json'dan yapilmamis ilk konuyu sec (deterministik, sirayla).
    Konu duz metin ya da {"baslik":..., "not":...} olabilir; (baslik, not) doner."""
    konular=_load(KONU_P,[])
    yapilan=set(u.get("yapilan",[]))
    for k in konular:
        baslik = k if isinstance(k,str) else k.get("baslik","")
        if baslik and baslik not in yapilan:
            return baslik, ("" if isinstance(k,str) else k.get("not",""))
    return None, ""

def _yayin_zamani(cfg, simdi=None):
    """Bir sonraki haftalik yayin anı: config.uzun_yayin_gunu (0=Pzt..6=Paz) +
    uzun_yayin_saati_utc. Kisa video slotlarindan (09:00/17:00 UTC) ayri tutulur."""
    simdi=simdi or datetime.now(timezone.utc)
    sa,dk=(int(x) for x in str(cfg.get("uzun_yayin_saati_utc","15:00")).split(":"))
    gun=int(cfg.get("uzun_yayin_gunu",3))
    h=simdi.replace(hour=sa,minute=dk,second=0,microsecond=0)+timedelta(days=(gun-simdi.weekday())%7)
    if h<=simdi+timedelta(minutes=30): h+=timedelta(days=7)
    return h.isoformat().replace("+00:00","Z")

def _zaman_damgalari(bolumler, baslangiclar):
    """Senaryonun bolumlerini (baslik + baslangic sahnesi) render'daki gercek sahne
    zamanlarina cevirir. YouTube kurallari: ilk 00:00, en az 3 bolum, her bolum
    >= 10 sn. Kurallar saglanmazsa bos string (aciklama bolumsuz kalir)."""
    if not bolumler or not baslangiclar:
        return ""
    satirlar, son = [], None
    for i, b in enumerate(sorted(bolumler, key=lambda x: int(x.get("sahne", 0)))):
        n = min(max(0, int(b.get("sahne", 0))), len(baslangiclar) - 1)
        t = 0 if i == 0 else int(baslangiclar[n])
        bas = (b.get("baslik") or "").strip()
        if not bas or (son is not None and t - son < 10):
            continue
        satirlar.append(f"{t // 60:02d}:{t % 60:02d} — {bas}"); son = t
    return ("Zaman Damgaları\n" + "\n".join(satirlar)) if len(satirlar) >= 3 else ""

def _aciklama_bolumlu(aciklama, damgalar):
    """Zaman damgalarini, aciklamanin sonundaki gorus sorusundan ONCE yerlestirir
    (Toyota videosu duzeni: ozet -> kavramlar -> zaman damgalari -> soru)."""
    if not damgalar:
        return aciklama
    par = [p for p in (aciklama or "").strip().split("\n\n") if p.strip()]
    if par and par[-1].strip().endswith("?"):
        return "\n\n".join(par[:-1] + [damgalar, par[-1]])
    return "\n\n".join(par + [damgalar])

ONIZLEME_DIR="output/onizleme"

def _kaynaklar_ve_etiket(uzun):
    """Aciklamanin sonuna KAYNAKLAR (resmi kurum + kok alan adi) ve 2 hashtag ekler."""
    satir=[f"{k.get('ad','').strip()}\nhttps://{k.get('alan','').strip().strip('/')}"
           for k in (uzun.get("kaynaklar") or []) if k.get("ad") and k.get("alan")]
    ek=[]
    if satir: ek.append("KAYNAKLAR\n\n"+"\n\n".join(satir))
    et=[t for t in (uzun.get("etiketler") or []) if t and " " not in t.strip()][:1]
    ek.append(" ".join(["#"+_slug(t).replace("-","") for t in et]+["#belgesel"]))
    return (uzun.get("aciklama","").rstrip()+"\n\n"+"\n\n".join(ek)).strip()

def _onizleme_kaydet(uzun, cikti, kapak):
    """YAYINLAMADAN inceleme paketi: video + kapak + aciklama + senaryo + kare paneli."""
    import shutil, subprocess
    os.makedirs(ONIZLEME_DIR,exist_ok=True)
    shutil.copy(cikti,os.path.join(ONIZLEME_DIR,"video.mp4"))
    if kapak and os.path.exists(kapak): shutil.copy(kapak,os.path.join(ONIZLEME_DIR,"kapak.jpg"))
    # Yazısız arka plan: kapak yazısı değişirse yeni AI görseli üretmeden yeniden basılır.
    bg=os.path.splitext(kapak or "")[0]+"_bg.jpg"
    if kapak and os.path.exists(bg): shutil.copy(bg,os.path.join(ONIZLEME_DIR,"kapak_bg.jpg"))
    with open(os.path.join(ONIZLEME_DIR,"aciklama.txt"),"w",encoding="utf-8") as f:
        f.write(f"BAŞLIK: {uzun['baslik']}\n\nETİKETLER: {', '.join(uzun.get('etiketler') or [])}\n\n{uzun.get('aciklama','')}\n")
    with open(os.path.join(ONIZLEME_DIR,"senaryo.json"),"w",encoding="utf-8") as f:
        json.dump(uzun,f,ensure_ascii=False,indent=1)
    # 12 karelik panel (videoyu indirmeden genel bakis)
    sure=float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of",
                               "default=nokey=1:noprint_wrappers=1",cikti],capture_output=True,text=True).stdout.strip() or 0)
    if sure>0:
        subprocess.run(["ffmpeg","-v","error","-y","-i",cikti,"-vf",
                        f"fps=12/{sure:.1f},scale=480:-1,tile=4x3","-frames:v","1",
                        os.path.join(ONIZLEME_DIR,"kareler.jpg")])
    print(f"✓ ONIZLEME hazir ({sure/60:.1f} dk): {ONIZLEME_DIR}/ — YouTube'a YUKLENMEDI")

ONIZLEME_SENARYO="onizleme/uzun/senaryo.json"; ONIZLEME_KAPAK="onizleme/uzun/kapak.jpg"
SES_CACHE="output/ses_cache"

def _cipali_zaman(uzun, toplam):
    """Kelime zamanı olmayan hazır (müzikli) anlatım için kelime zamanları: açıklamadaki
    gerçek bölüm zaman damgalarına çapalanmış doğrusal dağıtım (sahne-ses kayması ~1 sn)."""
    import re as _r
    sahneler=uzun.get("sahneler") or []
    adet=[len((x.get("metin") or "").split()) for x in sahneler]
    bas=[sum(adet[:i]) for i in range(len(adet))]; W=sum(adet)
    if W==0: return None
    damga={m.group(3).strip():int(m.group(1))*60+int(m.group(2)) for m in
           _r.finditer(r"^(\d\d):(\d\d) — (.+)$", uzun.get("aciklama",""), _r.M)}
    cipa=[(0,0.0)]
    for b in uzun.get("bolumler") or []:
        t=damga.get((b.get("baslik") or "").strip()); i=int(b.get("sahne",0))
        if t is not None and 0<i<len(bas) and bas[i]>cipa[-1][0] and t>cipa[-1][1]:
            cipa.append((bas[i],float(t)))
    cipa.append((W,float(toplam)))
    zaman=[]; kelimeler=" ".join(x.get("metin","") for x in sahneler).split()
    for k,w in enumerate(kelimeler):
        j=max(i for i in range(len(cipa)-1) if cipa[i][0]<=k)
        (k0,t0),(k1,t1)=cipa[j],cipa[j+1]
        t=t0+(t1-t0)*(k-k0)/max(1,k1-k0); d=(t1-t0)/max(1,k1-k0)
        zaman.append({"start":t,"dur":max(0.05,d),"text":w})
    return zaman

def _anlatim_sakla():
    """Son render'ın temiz anlatımını (+ kelime zamanları) önbelleğe yaz."""
    import shutil
    son=getattr(V,"SON_ANLATIM",None)
    if not son: return
    os.makedirs(SES_CACHE,exist_ok=True)
    shutil.copy(son[0],os.path.join(SES_CACHE,"anlatim.mp3"))
    with open(os.path.join(SES_CACHE,"zaman.json"),"w",encoding="utf-8") as f: json.dump(son[1],f)
    print(f"  Anlatım önbelleğe alındı: {SES_CACHE}/ (aynı senaryo bir daha seslendirilmez)")

def main():
    cfg=_load(CFG_P,{})
    onizleme=os.environ.get("ONIZLEME")=="1"
    # DURDURMA BAYRAGI: analiz (uzun ort. 38 izlenme vs short 750) sonrasi uzun hatti
    # devre disi. Yeniden acmak icin config.json'da "uzun_aktif": true yapin.
    if not onizleme and not cfg.get("uzun_aktif", True):
        print("Uzun hatti devre disi (config.uzun_aktif=false) — atlaniyor."); return
    u=_load(UZUN_P,{"pending":[],"yapilan":[],"yapilan_id":[],"bekleyen_yorum":None})
    for k in ("pending","yapilan","yapilan_id"): u.setdefault(k,[])

    konu,konu_notu=_sonraki_konu(u)
    tema=str(cfg.get("uzun_tema","tuketici_belgesel"))
    if not konu:
        print("Uzun konu bankasi bitti — uzun_konular.json'a yeni konular ekleyin."); _save(u); return
    print(f"[1/4] Uzun konu ({tema}): {konu!r}")

    yeni_ses=onizleme and os.environ.get("ONIZLEME_YENI_SES")=="1"   # aynı senaryo, sıfırdan (ücretsiz) ses
    yeniden=onizleme and (os.environ.get("ONIZLEME_YENIDEN")=="1" or yeni_ses)
    _man=os.path.join("uzun_scripts", _slug(konu)+".json")
    if yeniden:
        # ONAYLI ÖNİZLEMEYİ YENİDEN RENDER: aynı senaryo + hazır ses (+ onaylı kapak);
        # yalnızca görseller yeniden üretilir. Hazır ses yoksa TTS'e GİDİLMEZ (kredi korunur).
        if not os.path.exists(ONIZLEME_SENARYO):
            raise SystemExit(f"Yeniden kullanım: {ONIZLEME_SENARYO} yok")
        with open(ONIZLEME_SENARYO,encoding="utf-8") as _f: uzun=json.load(_f)
        print("  [onaylı önizleme senaryosu yeniden kullanılıyor]")
    elif os.path.exists(_man):
        with open(_man,encoding="utf-8-sig") as _f: uzun=json.load(_f)
        print("  [manuel script kullanildi]", _man)
    else:
        uzun=uzun_script.uret(konu,tema=tema,not_=konu_notu)
    uzun["baslik"]=(uzun.get("baslik") or konu).strip()
    print(f"  Senaryo: {len(uzun['script'].split())} kelime, {len(uzun.get('sahneler') or [])} sahne")

    tmp=tempfile.mkdtemp(); sp=os.path.join(tmp,"script.txt"); open(sp,"w",encoding="utf-8").write(uzun["script"])
    os.makedirs("output",exist_ok=True); cikti="output/uzun_video.mp4"
    hazir_ses=hazir_zaman=None; karisik=False
    if yeniden and not yeni_ses:
        if os.path.exists(f"{SES_CACHE}/anlatim.mp3") and os.path.exists(f"{SES_CACHE}/zaman.json"):
            hazir_ses=f"{SES_CACHE}/anlatim.mp3"
            with open(f"{SES_CACHE}/zaman.json",encoding="utf-8") as _f: hazir_zaman=json.load(_f)
            print("  Ses: önbellekteki temiz anlatım")
        elif os.path.exists(os.environ.get("ONIZLEME_HAZIR_SES","") or "/yok"):
            hazir_ses=os.environ["ONIZLEME_HAZIR_SES"]; karisik=True
            hazir_zaman=_cipali_zaman(uzun, V.sure_al(hazir_ses))
            print("  Ses: önceki önizleme videosundan çıkarılan anlatım (müzikli)")
        else:
            raise SystemExit("Hazır ses bulunamadı — ElevenLabs kredisi harcamamak için durduruldu.")
    print("[2/4] Yatay render ...")
    V.uret_video(sp,cikti,ses=cfg.get("ses","erkek"),dikey=False,hiz=str(cfg.get("uzun_hiz","+0%")),
                 sahneler=uzun.get("sahneler"),animasyon=bool(cfg.get("animasyon",True)),cocuk=bool(cfg.get("cocuk_icerigi",False)),
                 tonlama=str(cfg.get("tonlama","+0Hz")),gorsel_stil=str(cfg.get("uzun_gorsel_stil","stok")),kanca=(uzun.get("kanca") or konu),
                 eleven_once=bool(cfg.get("uzun_eleven",True)),altyazi=bool(cfg.get("uzun_altyazi",True)),
                 hazir_ses=hazir_ses,hazir_zaman=hazir_zaman,ses_karisik=karisik,
                 ucretsiz_ses=str(cfg.get("uzun_ses","")).lower()=="ucretsiz")
    if onizleme: _anlatim_sakla()
    if "Zaman Damgaları" not in uzun.get("aciklama",""):   # yeniden kullanımda açıklama hazır
        damgalar=_zaman_damgalari(uzun.get("bolumler"), getattr(V,"SON_SAHNE_BASLANGIC",None))
        uzun["aciklama"]=_aciklama_bolumlu(uzun.get("aciklama",""), damgalar)
        print("  Bolumler:", ("\n    "+damgalar.replace("\n","\n    ")) if damgalar else "yok (kural saglanmadi)")
        uzun["aciklama"]=_kaynaklar_ve_etiket(uzun)
    kapak=None
    if yeniden and os.path.exists(ONIZLEME_KAPAK):
        import shutil as _sh; _sh.copy(ONIZLEME_KAPAK,"output/uzun_kapak.jpg"); kapak="output/uzun_kapak.jpg"
        print("  Kapak: onaylı önizleme kapağı")
    ky=uzun.get("kapak_yazi") or {}
    if not kapak and ky.get("alt"):
        try:
            import belgesel_gorsel as BG
            kapak=BG.kapak(uzun.get("kapak_gorsel"),ky.get("ust",""),ky["alt"],"output/uzun_kapak.jpg")
        except Exception as e: print("belgesel kapak atlandi:",str(e)[:80])
    if not kapak:
        try:
            import kapak_uzun as K; kapak=K.kapak_uret(cikti,uzun["baslik"],"output/uzun_kapak.jpg",kanca=uzun.get("kanca"))
        except Exception as e: print("kapak atlandi:",str(e)[:60])
    if onizleme:
        _onizleme_kaydet(uzun,cikti,kapak); return

    gizlilik=cfg.get("uzun_gizlilik","unlisted"); yayin=None
    if gizlilik=="private":
        yayin=_yayin_zamani(cfg)
        # Yeniden calisma korumasi: ayni baslik + slot zaten yuklendiyse tekrar yukleme.
        try:
            onceki=YT.planli_video_bul(uzun["baslik"],yayin)
        except Exception as e:
            onceki=None; print("  (onceki yukleme kontrolu atlandi:",str(e)[:80],")")
        if onceki:
            print(f"✓ Ayni uzun video zaten planli ({yayin}): https://youtu.be/{onceki}")
            u["yapilan"].append(konu); _save(u); return
    print(f"[3/4] Yukleniyor ... ({gizlilik}{', yayin '+yayin if yayin else ''})")
    vid=YT.yukle(cikti,uzun["baslik"],uzun.get("aciklama",""),uzun.get("etiketler") or [],gizlilik=gizlilik,
                 kategori=str(cfg.get("kategori","27")),cocuk_icerigi=bool(cfg.get("cocuk_icerigi",False)),kapak=kapak,yayin_zamani=yayin)
    uzun_url=f"https://youtu.be/{vid}"; print("✓ uzun yuklendi:",uzun_url,f"({gizlilik})")

    print("[4/4] Durum kaydediliyor ...")
    u["yapilan"].append(konu)
    u["son"]={"konu":konu,"uzun_url":uzun_url,"gizlilik":gizlilik,"yayin":yayin}
    _save(u); print("Tamam.")

if __name__=="__main__": main()
