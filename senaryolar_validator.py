#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
senaryolar.json Validator — Structural + Encoding checks
Repo'ya push edilecek: yt-cocuk-otomasyon/senaryolar_validator.py
"""
import json
import os
import re
from typing import List, Dict, Any, Tuple

class SenaryoValidator:
    """Senaryo yapısını ve içeriğini doğrula."""
    
    REQUIRED_FIELDS = ["baslik", "aciklama", "script", "sahneler", "seslendirme"]
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
        
        # Mojibake patterns (double-encoded UTF-8)
        mojibake_patterns = {
            "Ã": "Corrupted UTF-8 (À-ÿ range)",
            "â": "Corrupted UTF-8 (â range)",
            "Äž": "Corrupted ğ",
            "Ä°": "Corrupted ı",
            "ğŸ": "Corrupted emoji"
        }
        
        for pattern, desc in mojibake_patterns.items():
            if pattern in text:
                count = text.count(pattern)
                issues[pattern] = (count, desc)
        
        return issues
    
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
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
