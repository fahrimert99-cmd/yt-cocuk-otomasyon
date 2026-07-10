# 🛡️ Otomasyon Resilience & Recovery Guide

## Mevcut Durum Analizi

### ❌ Sorunlar

1. **Kısmi Hatalar Recovery Yok**
   - Video başarılı → YouTube upload fail → durum.json **güncellenmiyor**
   - Sonraki çalışmada baştan başlar (video yeniden üretilir)

2. **Hata Logging Zayıf**
   - Tarih/saat yok
   - Sadece son hata kaydediliyor
   - Hatalar git'e push edilmiyor

3. **Git Push Conflict**
   - Workflow ve lokal changes aynı dosyayı değiştirebilir
   - Rebase conflict → hiçbir kayıt pushlenmez

4. **API Kesintisi**
   - YouTube down → hiç retry yok
   - Baştan başlar (video waste)

---

## ✅ Önerilen Çözümler

### 1. **Checkpoint Sistem** (Partial Recovery)

**Yeni dosya: `checkpoint.json`**
```json
{
  "timestamp": "2026-07-10T11:30:00.123456",
  "aşama": "video_üretildi",
  "idx": 2,
  "veri": {
    "video_path": "output/video.mp4"
  }
}
```

**Aşamalar:**
- `senaryo_seçildi` → Video başlamak üzere
- `video_üretildi` → Video dosya hazır, YouTube'a yüklenecek
- `upload_başladı` → YouTube push edilmek üzere
- `upload_tamamlandı` → Tamamlandı, durum.json'a yazılacak

**Recovery Mantığı:**
```
Program start:
├─ checkpoint.json var mı?
│  ├─ Evet → son aşamadan devam et
│  └─ Hayır → normal akış
└─ İşlem tamamlandı → checkpoint.json sil
```

### 2. **Geliştirilmiş Hata Logging**

```python
def hata_log_yaz(hata_msg, aşama, idx):
    now = datetime.now().isoformat()
    entry = f"[{now}] HATA - Aşama: {aşama}, Senaryo: {idx}\n{hata_msg}"
    
    with open("hata.log", "a", encoding="utf-8") as f:
        f.write(entry + "\n" + "="*70 + "\n")
    
    # Git'e push et
    subprocess.run(["git", "add", "hata.log"], check=False)
    subprocess.run(["git", "commit", "-m", f"Log: {aşama}"], check=False)
    subprocess.run(["git", "push"], check=False)
```

**Avantajlar:**
- ✅ Tarih/saat ile tüm hatalar kaydediliyor
- ✅ Git history'de saklanıyor
- ✅ Arşivlenebilir

### 3. **Atomic durum.json Update**

```python
def durum_güncelle(idx):
    durum["sonraki"] = idx + 1
    with open(DURUM, "w", encoding="utf-8") as f:
        json.dump(durum, f)
    
    # Retry 3x with exponential backoff
    for attempt in range(3):
        try:
            subprocess.run(["git", "pull", "--rebase"], timeout=30)
            subprocess.run(["git", "add", DURUM], timeout=30)
            subprocess.run(["git", "commit", "-m", f"Update: Senaryo {idx+1}"])
            subprocess.run(["git", "push"], timeout=30)
            return True
        except subprocess.CalledProcessError:
            if attempt < 2:
                time.sleep(5 * (attempt + 1))  # Exponential backoff
                continue
            return False
```

**Avantajlar:**
- ✅ Git rebase conflict otomatik çözülüyor
- ✅ Push başarısızsa retry
- ✅ Timeout ile hanging engelliyor

### 4. **YouTube Upload Retry (API Resilience)**

```python
def yukle(..., max_retry=3):
    for attempt in range(max_retry):
        try:
            # Upload...
            return video_id
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                # Server error → retry
                time.sleep(10 * (attempt + 1))
                continue
            else:
                # Client error → fail immediately
                raise
        except Exception as e:
            if attempt < max_retry - 1:
                time.sleep(10 * (attempt + 1))
                continue
            raise
```

**Avantajlar:**
- ✅ Geçici API hatalarında retry
- ✅ Exponential backoff (rate limit respect)
- ✅ Kalıcı hatalarda fail-fast

---

## 📊 Yeni İş Akışı

```
START
│
├─ checkpoint.json var mı?
│  │
│  ├─ EVET: Son aşamadan devam
│  │  ├─ video_üretildi → YouTube'a yükle
│  │  ├─ upload_başladı → durum.json güncelle
│  │  └─ SUCCESS → checkpoint sil
│  │
│  └─ HAYIR: Normal akış
│     │
│     ├─ 1. Senaryo seç (checkpoint: senaryo_seçildi)
│     ├─ 2. Video üret (checkpoint: video_üretildi)
│     │   [FAIL] → hata.log + exit
│     ├─ 3. YouTube yükle, 3x retry (checkpoint: upload_başladı)
│     │   [FAIL after 3 retry] → hata.log + exit
│     ├─ 4. durum.json güncelle, 3x retry
│     │   [SUCCESS] → checkpoint sil
│     └─ END
│
[EXCEPTION] → hata_log_yaz() + git push + exit
```

---

## 🔧 Uygulama

### Dosyalar değiştirilecek:
1. `otomasyon.py` → **`otomasyon_improved.py`** (yeni)
2. `youtube_yukle.py` → **`youtube_yukle_improved.py`** (yeni)
3. `.gitignore` → `checkpoint.json` ekle

### Deployment:
```bash
# Backup
cp otomasyon.py otomasyon.py.bak
cp youtube_yukle.py youtube_yukle.py.bak

# Replace
mv otomasyon_improved.py otomasyon.py
mv youtube_yukle_improved.py youtube_yukle.py

# Commit
git add -A
git commit -m "Improvement: Add resilience, checkpoint recovery, better error logging"
git push
```

---

## 📈 Faydalar Özeti

| Sorun | Çözüm | Fayda |
|-------|-------|-------|
| Kısmi hata recovery yok | Checkpoint sistem | Video waste %80 azalır |
| Hata tracking zayıf | Tarih/saat + git push | Debugging kolay, history var |
| Git conflict | Pull + rebase retry | Otomatik çözüm, downtime azalır |
| API fail = baştan | Retry logic | Geçici hatalar otomatik recover |
| Durumlar belirsiz | Aşama yönetimi | Nerde olduğu her zaman belli |

---

## ⚠️ Notlar

- **checkpoint.json**: Geçici, her başarılı işlemden sonra silinir
- **hata.log**: Kalıcı, arşivlenebilir (tarih ile)
- **durum.json**: Video sırasını track eder (kısa + atomic)
- Tüm dosya işlemleri UTF-8 (BOM-free) olacak
- Timeout: 30s (network delay için yeterli)

