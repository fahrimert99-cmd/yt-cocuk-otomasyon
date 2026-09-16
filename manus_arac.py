#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MANUS API ARACI — kredi korumali, stdlib-only istemci.

Manus (https://manus.ai) bir *ajan* servisidir: web'de gezinir, arastirir,
dosya uretir. Bu yuzden normal bir LLM'den PAHALIDIR (gorev basina ~100-500
kredi). Bu depodaki gunluk hatta (otomasyon/uzun/haber) BILEREK baglanmamistir;
yalnizca ELLE tetiklenen `manus.yml` is akisindan cagrilir.

Kredi butcesi `manus_durum.json` dosyasinda tutulur; her gorevden once kalan
butce kontrol edilir, sonra gercek (varsa) ya da tahmini tuketim islenir.

Env:
  MANUS_API_KEY | MANUS_KEY   : API anahtari (GitHub Secrets)
  MANUS_BUTCE                 : toplam kredi butcesi (ilk kurulumda, vars. 1100)
  MANUS_BUTCE_ZORLA=1         : butce kilidini gec (dikkat)
  MANUS_KURU=1                : kuru calisma — API'ye istek atmaz, promptu yazar
  MANUS_SAHTE_YANIT=<dosya>   : kuru calismada dondurulecek sahte JSON yanit
  MANUS_API_URL               : (opsiyonel) alternatif kok adres
"""
import os, re, json, time, urllib.parse, urllib.request, urllib.error

KOK = (os.environ.get("MANUS_API_URL") or "https://api.manus.ai").rstrip("/")
DURUM_DOSYA = "manus_durum.json"

# Ajan profilleri. lite = en ucuz/hizli, max = en derin arastirma (en pahali).
PROFILLER = {
    "lite":     "manus-1.6-lite",
    "standart": "manus-1.6",
    "max":      "manus-1.6-max",
}
# Muhafazakar kredi tahmini (Manus gercek tuketimi yanitta bildirirse o kullanilir).
TAHMINI_KREDI = {"lite": 100, "standart": 250, "max": 500}

# KREDI MODELI (Manus ucretsiz plan):
#   · 300 kredi HER GUN yenilenir, UTC gece yarisi sifirlanir ve DEVREDILMEZ.
#   · Tuketim sirasi gunluk -> aylik -> ek paket -> kalici bakiye; yani gunde
#     300'u asmayan bir gorev kalici bakiyeye HIC dokunmaz (bedava calisir).
#   · Gunluk yenileme kredilerinin AYLIK tuketim tavani 1500'dur — asil
#     kisitlayici sinir budur (ayda ~10-12 lite gorev).
#   · Kalici bakiye (rezerv) yalnizca ACIKCA izin verilirse harcanir.
GUNLUK_LIMIT = 300
AYLIK_LIMIT = 1500
VARSAYILAN_REZERV = 1100


# --------------------------------------------------------------- yardimcilar
def anahtar():
    k = (os.environ.get("MANUS_API_KEY") or os.environ.get("MANUS_KEY") or "").strip()
    if not k:
        raise SystemExit("MANUS_API_KEY tanimli degil (GitHub Secrets -> MANUS_API_KEY).")
    return k


def _profil(ad):
    ad = (ad or "lite").strip().lower()
    return PROFILLER.get(ad, PROFILLER["lite"]), (ad if ad in PROFILLER else "lite")


def _derin_ara(obj, adaylar, _derinlik=0):
    """Ic ice JSON icinde adaylardan biriyle eslesen ilk degeri dondur."""
    if _derinlik > 6 or obj is None:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in adaylar and v not in (None, "", [], {}):
                return v
        for v in obj.values():
            r = _derin_ara(v, adaylar, _derinlik + 1)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _derin_ara(v, adaylar, _derinlik + 1)
            if r is not None:
                return r
    return None


def _kredi_bul(obj):
    """Yanitta gercek kredi tuketimi bildiriliyorsa onu cek (alan adi degisebilir)."""
    for ad in ("credits_used", "credit_used", "credits_consumed", "credit_cost",
               "credits", "credit_usage", "usage_credits"):
        v = _derin_ara(obj, {ad})
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
        if isinstance(v, dict):
            for kk in ("used", "total", "amount", "consumed"):
                if isinstance(v.get(kk), (int, float)) and v[kk] > 0:
                    return int(v[kk])
    return None


def _json_ayikla(metin):
    """Serbest metinden ilk gecerli JSON govdesini cikar (```json cercevesi dahil)."""
    t = (metin or "").strip()
    t = re.sub(r"^```(json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    for ac, kap in (("{", "}"), ("[", "]")):
        i, j = t.find(ac), t.rfind(kap)
        if i >= 0 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except Exception:
                continue
    return None


# --------------------------------------------------------------------- HTTP
def _http(yontem, yol, govde=None, sorgu=None, timeout=90, deneme=3):
    url = KOK + yol
    if sorgu:
        url += "?" + urllib.parse.urlencode({k: v for k, v in sorgu.items() if v is not None})
    veri = json.dumps(govde).encode() if govde is not None else None
    son = ""
    for k in range(deneme):
        req = urllib.request.Request(url, data=veri, method=yontem, headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-manus-api-key": anahtar(),
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                ham = r.read().decode("utf-8", "ignore")
            return json.loads(ham) if ham.strip() else {}
        except urllib.error.HTTPError as he:
            govde_txt = ""
            try:
                govde_txt = he.read().decode("utf-8", "ignore")[:400]
            except Exception:
                pass
            son = f"HTTP {he.code}: {govde_txt}"
            if he.code in (401, 403):
                raise RuntimeError(f"Manus yetki hatasi — anahtari kontrol et. {son}")
            if he.code == 402 or "credit" in govde_txt.lower():
                raise RuntimeError(f"Manus kredi hatasi: {son}")
            if he.code not in (408, 409, 425, 429, 500, 502, 503, 504):
                raise RuntimeError(f"Manus istek hatasi: {son}")
        except Exception as e:
            son = f"{type(e).__name__}: {str(e)[:200]}"
        if k < deneme - 1:
            time.sleep(4 * (k + 1))
    raise RuntimeError(f"Manus istegi basarisiz ({yontem} {yol}): {son}")


def gorev_olustur(prompt, profil="lite", baslik=None, sema=None, gizli=True):
    model, _ = _profil(profil)
    govde = {"prompt": prompt, "agent_profile": model, "locale": "tr-TR",
             "hide_in_task_list": bool(gizli)}
    if baslik:
        govde["title"] = baslik[:120]
    if sema:
        govde["structured_output_schema"] = sema
    try:
        return _http("POST", "/v2/task.create", govde)
    except RuntimeError as e:
        # Sema desteklenmiyorsa semasiz tekrar dene (JSON'u metinden ayikilacak).
        if sema and ("structured_output" in str(e) or "schema" in str(e).lower()):
            print("      [uyari] structured_output_schema reddedildi, semasiz deneniyor")
            govde.pop("structured_output_schema", None)
            return _http("POST", "/v2/task.create", govde)
        raise


def gorev_detay(tid):
    return _http("GET", "/v2/task.detail", sorgu={"task_id": tid})


def gorev_mesajlar(tid, limit=30):
    return _http("GET", "/v2/task.listMessages",
                 sorgu={"task_id": tid, "limit": limit, "order": "desc"})


def gorev_durdur(tid):
    try:
        return _http("POST", "/v2/task.stop", {"task_id": tid}, deneme=1)
    except Exception as e:
        print(f"      [uyari] gorev durdurulamadi: {str(e)[:100]}")
        return {}


BITTI = {"finished", "completed", "complete", "done", "success", "succeeded",
         "stopped", "failed", "error", "cancelled", "canceled"}
HATA = {"failed", "error", "cancelled", "canceled"}


def _durum(detay):
    d = _derin_ara(detay, {"status", "state", "task_status"})
    return str(d).lower().strip() if d else ""


def _metin_topla(mesajlar):
    """Mesaj listesinden ajanin URETTIGI metni birlestir (en yeniden eskiye)."""
    kayitlar = mesajlar
    if isinstance(mesajlar, dict):
        for k in ("messages", "data", "items", "list"):
            if isinstance(mesajlar.get(k), list):
                kayitlar = mesajlar[k]
                break
    if not isinstance(kayitlar, list):
        return ""
    parcalar = []
    for m in kayitlar:
        if not isinstance(m, dict):
            continue
        rol = str(m.get("role") or m.get("sender") or m.get("type") or "").lower()
        if rol in ("user", "human"):
            continue
        icerik = m.get("content") or m.get("text") or m.get("message") or ""
        if isinstance(icerik, list):
            icerik = "".join(p.get("text", "") for p in icerik if isinstance(p, dict))
        if isinstance(icerik, str) and icerik.strip():
            parcalar.append(icerik.strip())
    return "\n\n".join(parcalar)


def calistir(prompt, sema=None, profil="lite", baslik=None,
             zaman_asimi=2400, aralik=20):
    """Gorevi olustur, bitene kadar bekle, (veri, metin, meta) dondur."""
    _, profil_ad = _profil(profil)

    if os.environ.get("MANUS_KURU") == "1":
        print("--- KURU CALISMA (API'ye istek atilmadi) ---")
        print(prompt[:2000])
        sahte = os.environ.get("MANUS_SAHTE_YANIT", "").strip()
        veri = None
        if sahte and os.path.exists(sahte):
            with open(sahte, encoding="utf-8") as f:
                veri = json.load(f)
        return veri, json.dumps(veri, ensure_ascii=False) if veri else "", \
            {"kuru": True, "kredi": 0, "profil": profil_ad}

    t0 = time.time()
    y = gorev_olustur(prompt, profil=profil_ad, baslik=baslik, sema=sema)
    tid = _derin_ara(y, {"task_id", "id", "taskid"})
    if not tid:
        raise RuntimeError(f"Manus task_id dondurmedi: {str(y)[:200]}")
    url = _derin_ara(y, {"task_url", "url", "share_url"}) or ""
    print(f"      Manus gorevi basladi: {tid}  {url}")

    detay, durum = {}, ""
    while time.time() - t0 < zaman_asimi:
        time.sleep(aralik)
        try:
            detay = gorev_detay(tid)
        except Exception as e:
            print(f"      [uyari] detay alinamadi: {str(e)[:90]}")
            continue
        durum = _durum(detay)
        print(f"      ... {int(time.time()-t0):>4}sn  durum={durum or '?'}")
        if durum in BITTI:
            break
    else:
        gorev_durdur(tid)
        raise RuntimeError(f"Manus gorevi {zaman_asimi}sn icinde bitmedi (task_id={tid}).")

    mesajlar = {}
    try:
        mesajlar = gorev_mesajlar(tid)
    except Exception as e:
        print(f"      [uyari] mesajlar alinamadi: {str(e)[:90]}")

    kredi = _kredi_bul(detay) or _kredi_bul(mesajlar)
    meta = {"task_id": tid, "url": url, "durum": durum, "profil": profil_ad,
            "sure_sn": int(time.time() - t0),
            "kredi": kredi or TAHMINI_KREDI[profil_ad],
            "kredi_tahmini": kredi is None}

    if durum in HATA:
        raise RuntimeError(f"Manus gorevi basarisiz (durum={durum}, task_id={tid}).")

    # 1) yapisal cikti  2) mesaj metninden JSON  3) duz metin
    veri = _derin_ara(detay, {"structured_output", "structured_result", "output", "result"})
    if isinstance(veri, str):
        veri = _json_ayikla(veri) or veri
    metin = _metin_topla(mesajlar)
    if not isinstance(veri, (dict, list)):
        veri = _json_ayikla(metin)
    return veri, metin, meta


# ------------------------------------------------------------------- butce
def _bugun():
    return time.strftime("%Y-%m-%d", time.gmtime())


def _bu_ay():
    return time.strftime("%Y-%m", time.gmtime())


def durum_oku():
    """Kredi defterini oku; gun/ay degistiyse ilgili sayaci sifirla."""
    try:
        with open(DURUM_DOSYA, encoding="utf-8-sig") as f:
            d = json.load(f)
    except Exception:
        d = {}
    d["gunluk_limit"] = int(os.environ.get("MANUS_GUNLUK_LIMIT") or
                            d.get("gunluk_limit") or GUNLUK_LIMIT)
    d["aylik_limit"] = int(os.environ.get("MANUS_AYLIK_LIMIT") or
                           d.get("aylik_limit") or AYLIK_LIMIT)
    d["rezerv_kredi"] = int(os.environ.get("MANUS_REZERV_KREDI") or
                            d.get("rezerv_kredi") or VARSAYILAN_REZERV)
    if d.get("gun") != _bugun():                  # UTC gece yarisi sifirlanir
        d["gun"], d["gunluk_harcanan"] = _bugun(), 0
    if d.get("ay") != _bu_ay():
        d["ay"], d["aylik_harcanan"] = _bu_ay(), 0
    d.setdefault("gunluk_harcanan", 0)
    d.setdefault("aylik_harcanan", 0)
    d.setdefault("gorevler", [])
    return _kalanlar(d)


def _kalanlar(d):
    d["gunluk_kalan"] = max(0, d["gunluk_limit"] - d["gunluk_harcanan"])
    d["aylik_kalan"] = max(0, d["aylik_limit"] - d["aylik_harcanan"])
    return d


def durum_yaz(d):
    _kalanlar(d)
    d["guncelleme"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with open(DURUM_DOSYA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def butce_kontrol(profil="lite", rezerv_izin=False):
    """Gorevden ONCE cagir. (defter, kaynak) dondurur; yetmezse calismayi durdurur.

    kaynak = "gunluk" (bedava yenilenen kredi) | "rezerv" (kalici bakiye).
    Gunluk yenilenen kredi kullanilmazsa YANAR, bu yuzden once o harcanir.
    """
    _, ad = _profil(profil)
    tahmin = TAHMINI_KREDI[ad]
    d = durum_oku()
    if not rezerv_izin:
        rezerv_izin = os.environ.get("MANUS_REZERV") == "1"
    print(f"      Kredi defteri: gunluk {d['gunluk_kalan']}/{d['gunluk_limit']} | "
          f"aylik {d['aylik_kalan']}/{d['aylik_limit']} | "
          f"rezerv {d['rezerv_kredi']} | bu gorev ~{tahmin}")

    if d["gunluk_kalan"] >= tahmin and d["aylik_kalan"] >= tahmin:
        return d, "gunluk"

    neden = ("gunluk yenilenen kredi bitti" if d["gunluk_kalan"] < tahmin
             else "aylik yenileme tavani (1500) doldu")
    if rezerv_izin and d["rezerv_kredi"] >= tahmin:
        print(f"      [{neden}] -> REZERVDEN harcanacak ({d['rezerv_kredi']} kredi)")
        return d, "rezerv"
    if os.environ.get("MANUS_BUTCE_ZORLA") == "1":
        print(f"      [{neden}] -> MANUS_BUTCE_ZORLA=1, yine de calistiriliyor")
        return d, "gunluk"
    raise SystemExit(
        f"BUTCE KORUMASI: {neden}. Bu gorev ~{tahmin} kredi gerektiriyor "
        f"(gunluk kalan {d['gunluk_kalan']}, aylik kalan {d['aylik_kalan']}, "
        f"rezerv {d['rezerv_kredi']}). Yenilenen kredi UTC gece yarisi sifirlanir; "
        f"yarin tekrar dene. Rezervden harcamak icin MANUS_REZERV=1 ver.")


def butce_isle(d, mod, meta, kaynak="gunluk"):
    """Gorevden SONRA cagir: tuketimi dogru kovaya isle."""
    if meta.get("kuru"):
        return d
    kredi = int(meta.get("kredi", 0))
    if kaynak == "rezerv":
        d["rezerv_kredi"] = max(0, int(d.get("rezerv_kredi", 0)) - kredi)
    else:
        d["gunluk_harcanan"] = int(d.get("gunluk_harcanan", 0)) + kredi
        d["aylik_harcanan"] = int(d.get("aylik_harcanan", 0)) + kredi
    d["gorevler"] = (d.get("gorevler") or [])[-49:] + [{
        "tarih": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "mod": mod, "profil": meta.get("profil"), "kaynak": kaynak,
        "task_id": meta.get("task_id"), "kredi": kredi,
        "tahmini": meta.get("kredi_tahmini"), "sure_sn": meta.get("sure_sn"),
        "url": meta.get("url"),
    }]
    durum_yaz(d)
    print(f"      Kredi islendi: -{kredi} ({kaynak}, "
          f"{'tahmini' if meta.get('kredi_tahmini') else 'gercek'}) | "
          f"gunluk kalan {d['gunluk_kalan']} · aylik kalan {d['aylik_kalan']} · "
          f"rezerv {d['rezerv_kredi']}")
    return d


if __name__ == "__main__":
    # Hizli anahtar dogrulamasi: en ucuz profil, tek kelimelik cikti.
    print("Manus anahtari dogrulaniyor (en dusuk maliyetli gorev) ...")
    veri, metin, meta = calistir(
        "Sadece su tek kelimeyi yaz, baska hicbir sey yazma: TAMAM",
        profil="lite", baslik="anahtar testi", zaman_asimi=600, aralik=10)
    print(f"Yanit: {(metin or '')[:200]!r}")
    print(f"Meta : {json.dumps(meta, ensure_ascii=False)}")
