# uzun_otomasyon.py — OTONOM uzun (yatay ~6 dk) video hatti. (DÜZELTİLMİŞ + mock-test edildi)
# ⚠️ Canli API'lere karsi test edilmedi; sozdizimi/mantik mock ile dogrulandi.
#    İlk calistirmada config.json'da "uzun_gizlilik":"unlisted" (GUVENLI MOD) ile dogrula.
# - Kisa sistemin durum.json'una YAZMAZ; kendi uzun_durum.json'unu tutar.
# - Eslestirme: short video_id=durum["bekleyen_yorum"]["video_id"], konu=senaryolar[(sonraki-1)%n]["baslik"].
#   Her gun pending'e yakalanir; ONCEKI gun yakalanan konu islenir (short o an public olur).
import os, json, tempfile
from datetime import datetime, timezone, timedelta, date
import video as V
import youtube_yukle as YT
import uzun_script

CFG_P="config.json"; SEN_P="senaryolar.json"; KISA_P="durum.json"; UZUN_P="uzun_durum.json"

def _load(p,d):
    try:
        with open(p,encoding="utf-8-sig") as f: return json.load(f)
    except Exception: return d
def _save(u):
    with open(UZUN_P,"w",encoding="utf-8") as f: json.dump(u,f,ensure_ascii=False,indent=2)
def _bugun(): return date.today().isoformat()

def _capture_short(u,sen):
    d=_load(KISA_P,{}); bek=d.get("bekleyen_yorum")
    if not isinstance(bek,dict): return
    sid=bek.get("video_id")
    if not sid: return
    n=len(sen)
    try: title=sen[(int(d.get("sonraki",0))-1)%n]["baslik"]
    except Exception: return
    biliniyor={p["short_id"] for p in u["pending"]} | set(u.get("yapilan_id",[]))
    if sid in biliniyor: return
    u["pending"].append({"title":title,"short_id":sid,"gun":_bugun()})
    print(f"  [yakalandi] short: {title!r} -> {sid}")

def _retry_yorum(u):
    bek=u.get("bekleyen_yorum")
    if bek and bek.get("short_id"):
        try:
            YT.yorum_at(bek["short_id"],bek["metin"]); print("✓ (ertelenmis) yorum:",bek["short_id"]); u["bekleyen_yorum"]=None
        except Exception as e: print("ertelenmis yorum yine olmadi:",str(e)[:100])

def main():
    cfg=_load(CFG_P,{}); sen=_load(SEN_P,[])
    if not sen: print("senaryolar yok"); return
    u=_load(UZUN_P,{"pending":[],"yapilan":[],"yapilan_id":[],"bekleyen_yorum":None})
    for k in ("pending","yapilan","yapilan_id"): u.setdefault(k,[])
    _capture_short(u,sen); _retry_yorum(u)
    bugun=_bugun()
    isle=next((p for p in u["pending"] if p.get("gun","9999")<bugun), None)
    if not isle:
        print("Bugun islenecek uygun konu yok (short'lar henuz public degil)."); _save(u); return
    konu=isle["title"]; short_id=isle["short_id"]
    print(f"[1/4] Uzun konu: {konu!r} (short={short_id})")
    uzun=uzun_script.uret(konu)
    tmp=tempfile.mkdtemp(); sp=os.path.join(tmp,"script.txt"); open(sp,"w",encoding="utf-8").write(uzun["script"])
    os.makedirs("output",exist_ok=True); cikti="output/uzun_video.mp4"
    print("[2/4] Yatay render ...")
    V.uret_video(sp,cikti,ses=cfg.get("ses","erkek"),dikey=False,hiz=str(cfg.get("uzun_hiz",cfg.get("hiz","+5%"))),
                 sahneler=uzun.get("sahneler"),animasyon=bool(cfg.get("animasyon",True)),cocuk=bool(cfg.get("cocuk_icerigi",False)),
                 tonlama=str(cfg.get("tonlama","+0Hz")),gorsel_stil=str(cfg.get("gorsel_stil","stok")),kanca=uzun.get("kanca"))
    kapak=None
    try:
        import kapak as K; kapak=K.kapak_uret(cikti,uzun["baslik"],"output/uzun_kapak.jpg")
    except Exception as e: print("kapak atlandi:",str(e)[:60])
    gizlilik=cfg.get("uzun_gizlilik","private"); yayin=None
    if gizlilik=="private":
        h=datetime.now(timezone.utc).replace(hour=17,minute=0,second=0,microsecond=0)
        if h<=datetime.now(timezone.utc)+timedelta(minutes=10): h+=timedelta(days=1)
        yayin=h.isoformat().replace("+00:00","Z")
    print("[3/4] Yukleniyor ...")
    vid=YT.yukle(cikti,uzun["baslik"],uzun.get("aciklama",""),uzun.get("etiketler",[]),gizlilik=gizlilik,
                 kategori=str(cfg.get("kategori","27")),cocuk_icerigi=bool(cfg.get("cocuk_icerigi",False)),kapak=kapak,yayin_zamani=yayin)
    uzun_url=f"https://youtu.be/{vid}"; print("✓ uzun yuklendi:",uzun_url,f"({gizlilik})")
    print("[4/4] Short'a yonlendirme ...")
    metin=f"Bu tuzagi DETAYLI anlattigim video kanalimda 👉 {uzun_url}\nKendini ve cocugunu korumanin yollari videonun sonunda."
    try:
        YT.yorum_at(short_id,metin); print("✓ short'a yorum:",short_id)
    except Exception as e:
        u["bekleyen_yorum"]={"short_id":short_id,"metin":metin}; print("yorum ertelendi:",str(e)[:100])
    u["pending"]=[p for p in u["pending"] if p is not isle]
    u["yapilan"].append(konu); u["yapilan_id"].append(short_id)
    u["son"]={"konu":konu,"uzun_url":uzun_url,"gizlilik":gizlilik}
    _save(u); print("Tamam.")

if __name__=="__main__": main()
