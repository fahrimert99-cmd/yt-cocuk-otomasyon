# uzun_otomasyon.py — OTONOM uzun (yatay ~6 dk) video hatti — GIZEM / GERCEK OLAYLAR.
# ⚠️ Yayin GUVENLI: ilk testlerde config.json'da "uzun_gizlilik":"unlisted" birak;
#    begenince "private" (zamanlanmis public) yap.
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
    """uzun_konular.json'dan yapilmamis ilk konuyu sec (deterministik, sirayla)."""
    konular=_load(KONU_P,[])
    yapilan=set(u.get("yapilan",[]))
    for k in konular:
        baslik = k if isinstance(k,str) else k.get("baslik","")
        if baslik and baslik not in yapilan:
            return baslik
    return None

def main():
    cfg=_load(CFG_P,{})
    # DURDURMA BAYRAGI: analiz (uzun ort. 38 izlenme vs short 750) sonrasi uzun hatti
    # devre disi. Yeniden acmak icin config.json'da "uzun_aktif": true yapin.
    if not cfg.get("uzun_aktif", True):
        print("Uzun hatti devre disi (config.uzun_aktif=false) — atlaniyor."); return
    u=_load(UZUN_P,{"pending":[],"yapilan":[],"yapilan_id":[],"bekleyen_yorum":None})
    for k in ("pending","yapilan","yapilan_id"): u.setdefault(k,[])

    konu=_sonraki_konu(u)
    if not konu:
        print("Uzun konu bankasi bitti — uzun_konular.json'a yeni gizem konulari ekleyin."); _save(u); return
    print(f"[1/4] Uzun konu (gizem): {konu!r}")

    _man=os.path.join("uzun_scripts", _slug(konu)+".json")
    if os.path.exists(_man):
        with open(_man,encoding="utf-8-sig") as _f: uzun=json.load(_f)
        print("  [manuel script kullanildi]", _man)
    else:
        uzun=uzun_script.uret(konu)

    tmp=tempfile.mkdtemp(); sp=os.path.join(tmp,"script.txt"); open(sp,"w",encoding="utf-8").write(uzun["script"])
    os.makedirs("output",exist_ok=True); cikti="output/uzun_video.mp4"
    print("[2/4] Yatay render ...")
    V.uret_video(sp,cikti,ses=cfg.get("ses","erkek"),dikey=False,hiz=str(cfg.get("uzun_hiz",cfg.get("hiz","+5%"))),
                 sahneler=uzun.get("sahneler"),animasyon=bool(cfg.get("animasyon",True)),cocuk=bool(cfg.get("cocuk_icerigi",False)),
                 tonlama=str(cfg.get("tonlama","+0Hz")),gorsel_stil=str(cfg.get("uzun_gorsel_stil","stok")),kanca=(uzun.get("kanca") or konu),
                 eleven_once=bool(cfg.get("uzun_eleven",True)))
    kapak=None
    try:
        import kapak_uzun as K; kapak=K.kapak_uret(cikti,uzun["baslik"],"output/uzun_kapak.jpg",kanca=uzun.get("kanca"))
    except Exception as e: print("kapak atlandi:",str(e)[:60])

    gizlilik=cfg.get("uzun_gizlilik","unlisted"); yayin=None
    if gizlilik=="private":
        h=datetime.now(timezone.utc).replace(hour=18,minute=0,second=0,microsecond=0)
        if h<=datetime.now(timezone.utc)+timedelta(minutes=10): h+=timedelta(days=1)
        yayin=h.isoformat().replace("+00:00","Z")
    print("[3/4] Yukleniyor ...")
    vid=YT.yukle(cikti,uzun["baslik"],uzun.get("aciklama",""),uzun.get("etiketler",[]),gizlilik=gizlilik,
                 kategori=str(cfg.get("kategori","27")),cocuk_icerigi=bool(cfg.get("cocuk_icerigi",False)),kapak=kapak,yayin_zamani=yayin)
    uzun_url=f"https://youtu.be/{vid}"; print("✓ uzun yuklendi:",uzun_url,f"({gizlilik})")

    print("[4/4] Durum kaydediliyor ...")
    u["yapilan"].append(konu)
    u["son"]={"konu":konu,"uzun_url":uzun_url,"gizlilik":gizlilik}
    _save(u); print("Tamam.")

if __name__=="__main__": main()
