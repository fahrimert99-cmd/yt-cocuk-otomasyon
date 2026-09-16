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
VARSAYILAN_BUTCE = 1100


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
def durum_oku():
    try:
        with open(DURUM_DOSYA, encoding="utf-8-sig") as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("butce_kredi", int(os.environ.get("MANUS_BUTCE") or VARSAYILAN_BUTCE))
    if os.environ.get("MANUS_BUTCE"):
        d["butce_kredi"] = int(os.environ["MANUS_BUTCE"])
    d.setdefault("harcanan_kredi", 0)
    d.setdefault("gorevler", [])
    d["kalan_kredi"] = d["butce_kredi"] - d["harcanan_kredi"]
    return d


def durum_yaz(d):
    d["kalan_kredi"] = d["butce_kredi"] - d["harcanan_kredi"]
    d["guncelleme"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with open(DURUM_DOSYA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def butce_kontrol(profil="lite"):
    """Gorevden ONCE cagir. Kalan butce yetmiyorsa calismayi durdurur."""
    _, ad = _profil(profil)
    tahmin = TAHMINI_KREDI[ad]
    d = durum_oku()
    print(f"      Kredi: butce {d['butce_kredi']} | harcanan {d['harcanan_kredi']} | "
          f"kalan {d['kalan_kredi']} | bu gorev ~{tahmin}")
    if d["kalan_kredi"] < tahmin and os.environ.get("MANUS_BUTCE_ZORLA") != "1":
        raise SystemExit(
            f"BUTCE KORUMASI: kalan {d['kalan_kredi']} kredi, bu gorev icin ~{tahmin} "
            f"gerekiyor. Gercek bakiyen daha yuksekse {DURUM_DOSYA} icindeki "
            f"'butce_kredi' degerini guncelle ya da MANUS_BUTCE_ZORLA=1 ver.")
    return d


def butce_isle(d, mod, meta):
    """Gorevden SONRA cagir: tuketimi deftere isle."""
    if meta.get("kuru"):
        return d
    d["harcanan_kredi"] = int(d.get("harcanan_kredi", 0)) + int(meta.get("kredi", 0))
    d["gorevler"] = (d.get("gorevler") or [])[-49:] + [{
        "tarih": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "mod": mod, "profil": meta.get("profil"), "task_id": meta.get("task_id"),
        "kredi": meta.get("kredi"), "tahmini": meta.get("kredi_tahmini"),
        "sure_sn": meta.get("sure_sn"), "url": meta.get("url"),
    }]
    durum_yaz(d)
    print(f"      Kredi islendi: -{meta.get('kredi')} "
          f"({'tahmini' if meta.get('kredi_tahmini') else 'gercek'}) | "
          f"kalan {d['kalan_kredi']}")
    return d


if __name__ == "__main__":
    # Hizli anahtar dogrulamasi: en ucuz profil, tek kelimelik cikti.
    print("Manus anahtari dogrulaniyor (en dusuk maliyetli gorev) ...")
    veri, metin, meta = calistir(
        "Sadece su tek kelimeyi yaz, baska hicbir sey yazma: TAMAM",
        profil="lite", baslik="anahtar testi", zaman_asimi=600, aralik=10)
    print(f"Yanit: {(metin or '')[:200]!r}")
    print(f"Meta : {json.dumps(meta, ensure_ascii=False)}")
