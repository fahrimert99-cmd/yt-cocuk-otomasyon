#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""12:00/20:00 TR YouTube yayın bekçisi.

GitHub Actions cron gecikir veya atlanırsa, ilgili publishAt slotunda video yoksa
aynı günlük üretim workflowunu bir kez yeniden tetikler. PC/browser gerektirmez.
"""
import datetime as dt
import json
import os
import subprocess
import sys

import youtube_yukle as yt


def _slot():
    now = dt.datetime.now(dt.timezone.utc)
    saat = os.environ.get("SLOT_UTC", "").strip()
    if saat not in {"09:00", "17:00"}:
        raise SystemExit("SLOT_UTC yalnızca 09:00 veya 17:00 olabilir")
    return now.strftime("%Y-%m-%d") + "T" + saat + ":00Z"


def _workflow_calismiyor():
    """Aynı üretim workflowu zaten çalışıyorsa ikinci tetiklemeyi engelle."""
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not repo:
        return True
    try:
        p = subprocess.run(
            ["gh", "run", "list", "--repo", repo, "--workflow", "otomasyon.yml",
             "--status", "queued", "--status", "in_progress", "--limit", "5",
             "--json", "status"],
            text=True, capture_output=True, check=False, timeout=30)
        if p.returncode != 0:
            print("! Aktif workflow kontrolü yapılamadı; güvenli tarafta tetikleme atlandı")
            return False
        return not bool(json.loads(p.stdout or "[]"))
    except Exception as e:
        print(f"! Aktif workflow kontrolü başarısız: {str(e)[:120]}")
        return False


def main():
    slot = _slot()
    print(f"[bekçi] Kontrol edilen slot: {slot}")
    if yt.planli_slot_var(slot):
        print("[bekçi] Yayın slotu dolu; işlem yok.")
        return 0
    print("[bekçi] Slot boş; üretim workflowu kontrol ediliyor.")
    if not _workflow_calismiyor():
        print("[bekçi] Üretim zaten çalışıyor veya kontrol edilemedi; yeniden tetiklenmedi.")
        return 0
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    p = subprocess.run(["gh", "workflow", "run", "otomasyon.yml", "--repo", repo,
                        "--ref", "main"], check=False, text=True)
    if p.returncode:
        raise SystemExit("Günlük üretim workflowu tetiklenemedi")
    print("[bekçi] Günlük üretim workflowu yeniden tetiklendi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
