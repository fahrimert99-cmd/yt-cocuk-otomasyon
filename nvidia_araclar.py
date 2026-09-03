#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NVIDIA NIM (build.nvidia.com) tabanlı KALİTE araçları — hepsi NON-FATAL.

Herhangi bir hata / erişim sorunu / anahtar yokluğunda sistem ESKİ davranışına
düşer (None ya da orijinal veri döner; ASLA patlamaz). Böylece bu araçlar
sistemi yalnızca İYİLEŞTİRİR, hiçbir koşulda bozamaz.

Araçlar:
  senaryo_iyilestir(sen)  -> senaryoyu ikinci bir güçlü modele eleştirtip
                             hook/netlik/CTA açısından GÜÇLENDİRİR (dict|None).
  benzer_var_mi(baslik, mevcut) -> embedding ile ANLAMSAL tekrar tespiti (bool).

Env (opsiyonel):
  NVIDIA_KRITIK_MODEL  varsayılan deepseek-ai/deepseek-v3 (senaryo eleştirisi)
  NVIDIA_EMBED_MODEL   varsayılan nvidia/nv-embedqa-e5-v5  (anlamsal benzerlik)
  NVIDIA_BENZERLIK_ESIK varsayılan 0.90 (bu ve üstü kosinüs -> tekrar say)
"""
import os, re, json, math, urllib.request, urllib.error
import ai_script as A

# Senaryo eleştirisi için buffet'ten güçlü bir reasoning modeli.
KRITIK_MODEL = os.environ.get("NVIDIA_KRITIK_MODEL", "").strip() or "deepseek-ai/deepseek-v3"
# Anlamsal benzerlik için embedding modeli.
EMBED_MODEL = os.environ.get("NVIDIA_EMBED_MODEL", "").strip() or "nvidia/nv-embedqa-e5-v5"


def _nvidia_json(prompt, model=None):
    """NVIDIA chat -> JSON dict. HER hata None döner (asla fırlatmaz)."""
    key = A._nvidia_key()
    if not key:
        return None
    try:
        ham = A._nvidia(prompt, key, model=model)
        return json.loads(A._temizle(ham))
    except Exception:
        return None


IYILESTIR_PROMPT = """Sen "TUZAK AVCISI" Türk YouTube Shorts kanalının KIDEMLİ senaryo editörüsün.
Aşağıda bir tüketici-tuzağı senaryosu var. Görevin onu DAHA VURUCU hale getirmek:
- İLK CÜMLE ilk 2 saniyede kaydırmayı durduracak kadar şok/merak dolu olsun.
- Tuzak net anlatılsın; izleyiciye pratik bir KORUNMA ipucu versin.
- Sonda kısa bir ABONE çağrısı + bir sonraki videoya merak bırakan TEASER olsun.
- Uydurma istatistik YOK. Emoji/başlık/madde YOK; düz paragraf. ~100-120 kelime.
- 6 sahne; her sahne için İNGİLİZCE sinematik görsel tarifi.
- TÜRKÇE İMLÂ KUSURSUZ: ç,ğ,ı,İ,ö,ş,ü harflerini eksiksiz kullan; ASCII'ye sadeleştirme.
Anlam/konu AYNI kalsın; sadece güçlendir. Zaten güçlüyse küçük rötuşla iyileştir.

MEVCUT SENARYO (JSON):
{mevcut}

SADECE geçerli JSON döndür, AYNI şema, başka hiçbir şey yazma:
{{"baslik":"...","aciklama":"2-3 cümle","etiketler":["tuzak","tüketici","e3","e4","e5"],
"kanca":"...","script":"...","sahneler":[{{"metin":"...","gorsel":"cinematic english"}}],
"tema":"tuzak"}}"""


def senaryo_iyilestir(sen):
    """Senaryoyu güçlü bir modele eleştirtip güçlendirilmiş sürümü döner.
    Başarısızlıkta None (çağıran orijinali kullanır). Şema/başlık korunur."""
    if not isinstance(sen, dict) or not sen.get("script"):
        return None
    try:
        mevcut = json.dumps({k: sen.get(k) for k in
                             ("baslik", "kanca", "aciklama", "etiketler", "script", "sahneler")},
                            ensure_ascii=False)
    except Exception:
        return None
    d = _nvidia_json(IYILESTIR_PROMPT.format(mevcut=mevcut[:6000]), model=KRITIK_MODEL)
    if not isinstance(d, dict) or not d.get("script"):
        return None
    # Kimlik alanlarını KORU: başlık/kanca/tema orijinalden gelsin (editör bunları
    # değiştirmesin; havuz determinizmi ve marka tutarlılığı için).
    d["baslik"] = sen.get("baslik") or d.get("baslik")
    d["kanca"] = sen.get("kanca") or d.get("kanca")
    d["tema"] = "tuzak"
    if not isinstance(d.get("etiketler"), list) or not d["etiketler"]:
        d["etiketler"] = sen.get("etiketler", ["tuzak", "tüketici"])
    return d


# ---- Anlamsal benzerlik (embedding) -----------------------------------------
def _embed(metinler, input_type="query"):
    """NVIDIA embeddings -> vektör listesi. Hata None döner (asla fırlatmaz)."""
    key = A._nvidia_key()
    if not key or not metinler:
        return None
    url = "https://integrate.api.nvidia.com/v1/embeddings"
    body = {"input": list(metinler), "model": EMBED_MODEL,
            "input_type": input_type, "encoding_format": "float", "truncate": "END"}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
        return [row["embedding"] for row in d.get("data", [])]
    except Exception:
        return None


def _kosinus(a, b):
    if not a or not b:
        return 0.0
    nokta = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return nokta / (na * nb) if na and nb else 0.0


def benzer_var_mi(baslik, mevcut_basliklar, esik=None):
    """baslik, mevcut başlıklardan biriyle ANLAMSAL olarak (embedding kosinüs)
    yeterince benziyorsa True. Erişim/hata halinde False (tekrarı engelleme
    görevini düz-metin dedup'a bırakır -> asla yanlışlıkla fikir atmaz)."""
    if esik is None:
        try:
            esik = float(os.environ.get("NVIDIA_BENZERLIK_ESIK", "0.90") or "0.90")
        except Exception:
            esik = 0.90
    liste = [b for b in (mevcut_basliklar or []) if b][-60:]   # maliyet: son 60
    if not baslik or not liste:
        return False
    vekt = _embed([baslik] + liste)
    if not vekt or len(vekt) != len(liste) + 1:
        return False
    aday, digerleri = vekt[0], vekt[1:]
    return any(_kosinus(aday, v) >= esik for v in digerleri)


if __name__ == "__main__":
    print("KRITIK_MODEL:", KRITIK_MODEL, "| EMBED_MODEL:", EMBED_MODEL,
          "| NVIDIA key:", bool(A._nvidia_key()))
