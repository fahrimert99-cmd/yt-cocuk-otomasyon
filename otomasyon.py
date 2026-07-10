#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub-native otomasyon (AI BAĞIMLILIĞI YOK) — RESILIENT VERSION
✓ Adım-adım checkpoint (partial failures recover)
✓ Hata log tarih/saat + detaylı stack trace
✓ Git conflict handling + atomic state transitions
✓ API kesintisinde baştan başlamak yerine durum.json'dan devam
✓ YouTube upload retry logic
"""
import os, json, tempfile, traceback, subprocess, time
from datetime import datetime
import video as V
from senaryolar_validator import validate_and_load

SENARYOLAR = "senaryolar.json"
DURUM = "durum.json"
HATA_LOG = "hata.log"
CHECKPOINT = "checkpoint.json"  # Yeni: işlem checkpointi

# ============================================================
# CHECKPOINT YÖNETIM (partial failures for recovery)
# ============================================================

def checkpoint_olustur(aşama, idx, veri=None):
    """İşlem aşamasını kaydeder (recovery için)."""
    cp = {
        "timestamp": datetime.now().isoformat(),
        "aşama": aşama,  # "senaryo_seçildi", "video_üretildi", "upload_başladı", "upload_tamamlandı"
        "idx": idx,
        "veri": veri or {}
    }
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)
    return cp

def checkpoint_oku():
    """Mevcut checkpoint'i oku (yoksa None)."""
    if os.path.exists(CHECKPOINT):
        try:
            with open(CHECKPOINT, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def checkpoint_temizle():
    """Başarılı işlemden sonra checkpoint'i sil."""
    if os.path.exists(CHECKPOINT):
        os.remove(CHECKPOINT)

# ============================================================
# DURUM DOSYASI (atomik güncelleme)
# ============================================================

def _senaryolar():
    """Senaryoları doğrulamalar ile yükle."""
    try:
        return validate_and_load(SENARYOLAR)
    except RuntimeError as e:
        print(f"❌ {e}", flush=True)
        raise

def _durum():
    if os.path.exists(DURUM):
        with open(DURUM, encoding="utf-8-sig") as f:
            return json.load(f)
    return {"sonraki": 0}

def durum_güncelle(idx):
    """Durum dosyasını atomik şekilde güncelle + git'e push et."""
    durum = _durum()
    durum["sonraki"] = idx + 1
    
    # Yazma
    with open(DURUM, "w", encoding="utf-8") as f:
        json.dump(durum, f, ensure_ascii=False, indent=2)
    
    # Git push (retry 3x)
    for attempt in range(3):
        try:
            subprocess.run(["git", "config", "user.name", "bot"], check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], 
                          check=True, capture_output=True)
            subprocess.run(["git", "pull", "--rebase"], check=True, capture_output=True, timeout=30)
            subprocess.run(["git", "add", DURUM], check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"Update: Senaryo {idx+1} tamamlandı"], 
                          check=True, capture_output=True)
            subprocess.run(["git", "push"], check=True, capture_output=True, timeout=30)
            return True
        except subprocess.CalledProcessError as e:
            if attempt < 2:
                time.sleep(5 * (attempt + 1))  # exponential backoff
                continue
            return False
        except Exception:
            return False

# ============================================================
# HATA LOG (tarih + detaylı)
# ============================================================

def hata_log_yaz(hata_msg, aşama, idx):
    """Tarih/saat ile hata log'u yaz."""
    now = datetime.now().isoformat()
    entry = f"""
{'='*70}
[{now}] HATA - Aşama: {aşama}, Senaryo: {idx}
{'='*70}
{hata_msg}
"""
    mode = "a" if os.path.exists(HATA_LOG) else "w"
    with open(HATA_LOG, mode, encoding="utf-8") as f:
        f.write(entry)
    
    # Git'e push et (hata durumu belgelemek için)
    try:
        subprocess.run(["git", "add", HATA_LOG], check=False, capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", f"Log: Hata {aşama}"], check=False, capture_output=True, timeout=10)
        subprocess.run(["git", "push"], check=False, capture_output=True, timeout=10)
    except Exception:
        pass  # Log push başarısız olsa bile devam et

# ============================================================
# ANA AKIŞ (RECOVERY-AWARE)
# ============================================================

def main():
    # 1. Eski checkpoint varsa recovery yap
    cp = checkpoint_oku()
    if cp:
        print(f"[RECOVERY] Son checkpoint: {cp['aşama']} (idx={cp['idx']})")
        if cp["aşama"] == "video_üretildi":
            print("  → Video zaten üretildi, YouTube'a yüklemeye devam ediliyor...")
            idx = cp["idx"]
            cikti = cp["veri"].get("video_path")
            # Video upload'ı retry et
            if os.path.exists(cikti):
                _youtube_yukle_retry(cikti, idx)
                checkpoint_temizle()
                return
            else:
                print("  ✗ Video dosyası bulunamadı, baştan başlanıyor...")
                checkpoint_temizle()
        elif cp["aşama"] == "upload_başladı":
            print("  → Upload işlemi başladı ancak tamamlanmadı. Yeniden deneniyor...")
            idx = cp["idx"]
            video_id = cp["veri"].get("video_id")
            if video_id:
                print(f"  → Video zaten YouTube'a yüklendi: {video_id}")
                durum_güncelle(idx)
                checkpoint_temizle()
                return
    
    # 2. Normal akış
    try:
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)
        senaryolar = _senaryolar()
        durum = _durum()
        idx = durum["sonraki"] % len(senaryolar)
        veri = senaryolar[idx]
        
        print(f"[1/3] Senaryo ({idx+1}/{len(senaryolar)}): {veri['baslik']}")
        checkpoint_olustur("senaryo_seçildi", idx)
        
        # Video üretim
        tmp = tempfile.mkdtemp()
        sp = os.path.join(tmp, "script.txt")
        with open(sp, "w", encoding="utf-8") as f:
            f.write(veri["script"])
        os.makedirs("output", exist_ok=True)
        cikti = "output/video.mp4"
        
        print("[2/3] Video üretiliyor (ses + görsel + alt yazı) ...")
        try:
            V.uret_video(sp, cikti,
                        ses=cfg.get("ses", "erkek"),
                        dikey=(cfg.get("format", "dikey") == "dikey"),
                        sahneler=veri.get("sahneler"),
                        animasyon=bool(cfg.get("animasyon", True)),
                        cocuk=bool(cfg.get("cocuk_icerigi", False)),
                        tonlama=str(cfg.get("tonlama", "+0Hz")))
            boyut_kb = os.path.getsize(cikti) // 1024
            print(f"      Çıktı: {cikti}  ({boyut_kb} KB)")
            checkpoint_olustur("video_üretildi", idx, {"video_path": cikti})
        except Exception as e:
            hata_msg = traceback.format_exc()
            hata_log_yaz(hata_msg, "video_üretim", idx)
            raise RuntimeError(f"Video üretim hatası: {str(e)}")
        
        # YouTube yükleme
        print("[3/3] YouTube'a yükleniyor ...")
        _youtube_yukle_retry(cikti, idx, veri)
        
        # Durum güncelle (başarılı)
        if durum_güncelle(idx):
            print(f"TAMAM ✓  (sıradaki: {idx+1})")
            checkpoint_temizle()
        else:
            hata_msg = "durum.json güncellemesi başarısız (git push failed)"
            hata_log_yaz(hata_msg, "durum_güncelleme", idx)
            print("⚠ UYARI: Video yüklendi ama durum.json güncellenemedi!")
            
    except Exception as e:
        hata_msg = traceback.format_exc()
        aşama = cp["aşama"] if cp else "bilinmiyor"
        idx = cp["idx"] if cp else -1
        hata_log_yaz(hata_msg, aşama, idx)
        raise

def _youtube_yukle_retry(cikti, idx, veri=None):
    """YouTube upload'ı retry logic ile."""
    import youtube_yukle as YT
    
    if not veri:
        # Checkpoint'ten veri oku
        senaryolar = _senaryolar()
        durum = _durum()
        idx_actual = durum["sonraki"] % len(senaryolar)
        veri = senaryolar[idx_actual]
    
    cfg = {}
    with open("config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    
    checkpoint_olustur("upload_başladı", idx, {})
    
    max_retry = 3
    for attempt in range(max_retry):
        try:
            vid = YT.yukle(cikti, veri["baslik"], veri.get("aciklama", ""),
                          veri.get("etiketler", []),
                          gizlilik=cfg.get("gizlilik", "private"),
                          kategori=str(cfg.get("kategori", "28")),
                          cocuk_icerigi=bool(cfg.get("cocuk_icerigi", False)))
            checkpoint_olustur("upload_tamamlandı", idx, {"video_id": vid})
            return vid
        except Exception as e:
            if attempt < max_retry - 1:
                wait = 10 * (attempt + 1)
                print(f"  ✗ Upload hatası, {wait}s sonra retry... ({attempt+1}/{max_retry})")
                time.sleep(wait)
                continue
            else:
                hata_msg = traceback.format_exc()
                hata_log_yaz(hata_msg, "youtube_upload", idx)
                raise RuntimeError(f"YouTube upload başarısız (3x denendi): {str(e)}")

# ============================================================
# GİRİŞ
# ============================================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"✗ HATA: {str(e)}")
        exit(1)
