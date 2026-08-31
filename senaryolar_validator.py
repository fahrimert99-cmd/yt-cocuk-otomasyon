#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
senaryolar.json Validator — Structural + Encoding checks
Repo'ya push edilecek: yt-cocuk-otomasyon/senaryolar_validator.py
"""
import json
import os
import re
import unicodedata
from typing import List, Dict, Any, Tuple

class SenaryoValidator:
    """Senaryo yapısını ve içeriğini doğrula."""
    
    # NOT: "seslendirme" runtime (otomasyon.py) tarafindan OKUNMUYOR; ses
    # ayarlari config.json'dan gelir. Bu yuzden zorunlu degildir (varsa yine de
    # sekli kontrol edilir). Zorunlu alanlar gercek runtime ihtiyaciyla eslesir.
    REQUIRED_FIELDS = ["baslik", "aciklama", "script", "sahneler"]
    SESLENDIRME_FIELDS = ["motor", "ses", "hiz", "pitch"]
    SAHNE_FIELDS = ["metin", "gorsel"]
    
    @staticmethod
    def check_encoding(filepath: str) -> bool:
        """Dosyada BOM veya encoding sorunları var mı?"""
        with open(filepath, "rb") as f:
            first_bytes = f.read(3)
            if first_bytes == b'\xef\xbb\xbf':
                print(f"⚠ WARNING: UTF-8 BOM detected in {filepath}")
                return False
        return True
    
    @staticmethod
    def check_turkish_chars(text: str) -> Dict[str, Tuple[int, str]]:
        """Bozuk UTF-8 karakterleri tespit et."""
        issues = {}
        
        # Mojibake patterns (double-encoded UTF-8).
        # NOT: Yalin "â" KALDIRILDI — meşru Türkçe bir harftir (ör. "kâr",
        # "hâlâ", "kâğıt") ve yanlış alarm veriyordu. Asil mojibake, iki-kez
        # kodlanmis "Ã..." dizileridir (ör. "Ã¢", "Ã§").
        mojibake_patterns = {
            "Ã": "Corrupted UTF-8 (À-ÿ range)",
            "Äž": "Corrupted ğ",
            "Ä°": "Corrupted ı",
            "ğŸ": "Corrupted emoji"
        }
        
        for pattern, desc in mojibake_patterns.items():
            if pattern in text:
                count = text.count(pattern)
                issues[pattern] = (count, desc)
        
        return issues
    
    # --- BAŞLIK KALİTE DENETİMİ (bilgilendirici) ---
    # Analiz (izlenme dalgalanması) verisinden çıkan 3 kaldıraç: en çok izlenen
    # başlıklar (1) AÇIK merak boşluğu içeriyor ("...NE VAR?", "...NEDEN?") — kapalı
    # evet/hayır sorularından ("...GERÇEK Mİ?") daha iyi tutuyor; (2) BÜYÜK HARF;
    # (3) sonda EMOJI. Bunlar üretimi ENGELLEMEZ, yalnızca uyarı üretir.
    TITLE_WH = {"NE", "NEDEN", "NASIL", "KİM", "KIM", "NEREDE", "NEREDEN", "NEREYE",
                "HANGİ", "HANGI", "KAÇ", "KAC", "NİYE", "NIYE", "KAÇTA", "NEYİN"}

    @staticmethod
    def _emoji_var(s: str) -> bool:
        for c in s:
            o = ord(c)
            # 0x1F000+: emoji blokları; 'So': sembol; 0xFE0F: emoji varyasyon
            # seçici; 0x20E3: keycap birleştirici (ör. 9️⃣). Bunlardan biri -> emoji.
            if o >= 0x1F000 or o in (0xFE0F, 0x20E3) or unicodedata.category(c) == "So":
                return True
        return False

    @staticmethod
    def _buyuk_harf_orani(s: str) -> float:
        harf = [c for c in s if c.isalpha()]
        if not harf:
            return 1.0
        return sum(1 for c in harf if c.isupper()) / len(harf)

    @staticmethod
    def _kapali_soru(s: str) -> bool:
        """Soru işareti var ama açık soru kelimesi (NE/NASIL/...) yoksa -> kapalı
        (evet/hayır) soru sayılır. Soru işareti hiç yoksa (ünlem tipi) kapsanmaz."""
        if "?" not in s:
            return False
        kelimeler = set(re.findall(r"[A-ZÇĞİÖŞÜ]+", s.upper()))
        return not (kelimeler & SenaryoValidator.TITLE_WH)

    @staticmethod
    def title_quality(baslik: str) -> List[str]:
        b = baslik or ""
        w = []
        if SenaryoValidator._kapali_soru(b):
            w.append("kapalı (evet/hayır) soru — açık merak boşluğu (NE/NASIL/NEDEN...) daha çok tutuyor")
        if SenaryoValidator._buyuk_harf_orani(b) < 0.7:
            w.append("çoğunlukla BÜYÜK HARF değil (veri: büyük harf başlıklar daha çok izleniyor)")
        if not SenaryoValidator._emoji_var(b):
            w.append("emoji yok (güçlü başlıkların hepsinde sonda emoji var)")
        return w

    # --- İÇERİK (SCRIPT) KALİTE DENETİMİ (bilgilendirici) ---
    # Analiz (abone dönüşümü %0.226, sağlıklı ~%0.5-1): abone büyümüyor çünkü
    # (1) videoların ~yarısında abone CTA'sı yok, (2) neredeyse hiçbirinde
    # süreklilik/teaser ("yarın yeni video") yok. İzleyici geri dönmek için
    # sebep bulamayınca abone olmuyor. Bu denetim üretimi ENGELLEMEZ.
    ABONE_KW = ("abone", "subscribe", "kanala katıl", "takip et")
    TEASER_KW = ("yarın", "bir sonraki", "sonraki video", "yeni video", "seri", "kaçırma")

    @staticmethod
    def script_quality(item: Dict[str, Any]) -> List[str]:
        s = (item.get("script") or "").lower()
        w = []
        if not any(k in s for k in SenaryoValidator.ABONE_KW):
            w.append("abone CTA'sı yok — dönüşüm için sonda net bir abone çağrısı ekle")
        if not any(k in s for k in SenaryoValidator.TEASER_KW):
            w.append("süreklilik/teaser yok — 'yarın yeni video' tarzı geri dönüş kancası ekle")
        return w

    @staticmethod
    def validate_single(item: Dict[str, Any], idx: int) -> List[str]:
        """Tek bir senaryo objesini doğrula."""
        errors = []
        
        # Required fields
        for field in SenaryoValidator.REQUIRED_FIELDS:
            if field not in item:
                errors.append(f"[{idx}] Missing required field: {field}")
            elif isinstance(item[field], str) and not item[field].strip():
                errors.append(f"[{idx}] Field '{field}' is empty")
        
        # Turkish character corruption
        for field in ["baslik", "aciklama", "script"]:
            if field in item:
                issues = SenaryoValidator.check_turkish_chars(item[field])
                if issues:
                    for pattern, (count, desc) in issues.items():
                        errors.append(f"[{idx}] {field}: {count}x {desc}")
        
        # Seslendirme validation
        if "seslendirme" in item:
            ss = item["seslendirme"]
            if not isinstance(ss, dict):
                errors.append(f"[{idx}] 'seslendirme' must be object, got {type(ss)}")
            else:
                for field in SenaryoValidator.SESLENDIRME_FIELDS:
                    if field not in ss:
                        errors.append(f"[{idx}] 'seslendirme' missing: {field}")
        
        # Sahneler validation
        if "sahneler" in item:
            sahneler = item["sahneler"]
            if not isinstance(sahneler, list):
                errors.append(f"[{idx}] 'sahneler' must be array, got {type(sahneler)}")
            else:
                if len(sahneler) == 0:
                    errors.append(f"[{idx}] 'sahneler' is empty")
                for s_idx, sahne in enumerate(sahneler):
                    if not isinstance(sahne, dict):
                        errors.append(f"[{idx}] sahne[{s_idx}] must be object, got {type(sahne)}")
                    else:
                        for field in SenaryoValidator.SAHNE_FIELDS:
                            if field not in sahne:
                                errors.append(f"[{idx}] sahne[{s_idx}] missing: {field}")
        
        return errors
    
    @staticmethod
    def validate_file(filepath: str) -> Tuple[List[Dict], List[str]]:
        """Tüm dosyayı doğrula, hataları topla."""
        all_errors = []
        senaryolar = []
        
        # 1. Encoding check
        if not SenaryoValidator.check_encoding(filepath):
            all_errors.append("⚠ File has UTF-8 BOM (may cause issues)")
        
        # 2. Parse JSON
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:  # utf-8-sig handles BOM
                raw = json.load(f)
        except json.JSONDecodeError as e:
            all_errors.append(f"❌ JSON Parse Error: {e}")
            return [], all_errors
        except UnicodeDecodeError as e:
            all_errors.append(f"❌ Encoding Error: {e}")
            return [], all_errors
        
        # 3. Validate each scenario
        if not isinstance(raw, list):
            all_errors.append(f"❌ Root must be array, got {type(raw)}")
            return [], all_errors
        
        for i, item in enumerate(raw):
            errors = SenaryoValidator.validate_single(item, i)
            all_errors.extend(errors)
            if not errors:  # Only add valid items
                senaryolar.append(item)
        
        return senaryolar, all_errors


def validate_and_load(filepath: str) -> List[Dict]:
    """Güvenli yükleme (hata raporu ile)."""
    valid, errors = SenaryoValidator.validate_file(filepath)
    
    if errors:
        print("=" * 70)
        print("❌ VALIDATION ERRORS:")
        for err in errors:
            print(f"  • {err}")
        print("=" * 70)
        
        if not valid:
            raise RuntimeError(f"No valid scenarios found. Fix errors above.")
    
    return valid


if __name__ == "__main__":
    import sys
    filepath = sys.argv[1] if len(sys.argv) > 1 else "senaryolar.json"
    
    try:
        scenarios = validate_and_load(filepath)
        print(f"✓ Validated {len(scenarios)} scenarios")
        for i, s in enumerate(scenarios):
            print(f"  [{i}] {s['baslik'][:50]}")

        # Başlık kalite uyarıları — bilgilendirici, CI'yı DÜŞÜRMEZ (exit 0).
        uyarili = []
        for i, s in enumerate(scenarios):
            uy = SenaryoValidator.title_quality(s.get("baslik", ""))
            if uy:
                uyarili.append((i, s.get("baslik", ""), uy))
        if uyarili:
            print("\n" + "-" * 70)
            print(f"ℹ Başlık kalite uyarıları ({len(uyarili)}/{len(scenarios)}) — üretimi engellemez:")
            for i, b, uy in uyarili:
                print(f"  ⚠ [{i}] {b[:45]}")
                for u in uy:
                    print(f"       - {u}")

        # İçerik (script) kalite uyarıları — abone dönüşümü için; CI'yı DÜŞÜRMEZ.
        icerik = []
        for i, s in enumerate(scenarios):
            uy = SenaryoValidator.script_quality(s)
            if uy:
                icerik.append((i, s.get("baslik", ""), uy))
        if icerik:
            print("\n" + "-" * 70)
            print(f"ℹ İçerik/abone uyarıları ({len(icerik)}/{len(scenarios)}) — üretimi engellemez:")
            for i, b, uy in icerik:
                print(f"  ⚠ [{i}] {b[:45]}")
                for u in uy:
                    print(f"       - {u}")
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
