#!/usr/bin/env python3
"""
CLI Script Moderasi Konten untuk Nextcloud.
Menganalisis foto dan video terhadap unsur seksualitas dan kekerasan.

Contoh Penggunaan:
    python moderate.py /path/to/foto.jpg
    python moderate.py /path/to/video.mp4 --verbose
    python moderate.py /path/to/file.jpg --json

Status Exit Code:
    0 = Clean / Allowed (Upload Nextcloud diterima)
    1 = Rejected / Blocked (Upload Nextcloud ditolak)
    2 = System Error
"""

import argparse
import json
import sys
import os
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ["PYTHONWARNINGS"] = "ignore"

# Otomatis gunakan .venv jika dijalankan dengan python sistem
_venv_python = Path(__file__).resolve().parent / ".venv" / "bin" / "python"
if _venv_python.exists() and sys.executable != str(_venv_python):
    try:
        os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)
    except Exception:
        pass

# Tambahkan direktori root script ke sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from moderator.config import load_config
from moderator.detector import ContentModerator


def main():
    parser = argparse.ArgumentParser(
        description="Nextcloud Automated Content Moderation Scanner (Foto & Video)"
    )
    parser.add_argument("file", help="Path ke file foto atau video yang akan dianalisis")
    parser.add_argument("--config", help="Path ke file konfigurasi json kustom", default=None)
    parser.add_argument("--engine", choices=["auto", "gemini", "sightengine", "local"], default=None,
                        help="Pilih engine moderasi (auto, gemini, sightengine, atau local)")
    parser.add_argument("--threshold-sexuality", type=float, default=None,
                        help="Ambang batas deteksi seksualitas (0.0 - 1.0)")
    parser.add_argument("--threshold-violence", type=float, default=None,
                        help="Ambang batas deteksi kekerasan (0.0 - 1.0)")
    parser.add_argument("--quarantine-dir", default=None,
                        help="Pindahkan file yang ditolak ke folder karantina ini")
    parser.add_argument("--action-on-reject", choices=["none", "delete", "quarantine"], default=None,
                        help="Tindakan setelah file ditolak; delete memakai OCC dan default-nya none")
    parser.add_argument("--occ-path", default=None,
                        help="Path ke Nextcloud occ, misalnya /var/www/html/nextcloud/occ")
    parser.add_argument("--file-id", default=None,
                        help="File ID Nextcloud dari placeholder Workflow Script %i")
    parser.add_argument("--json", action="store_true",
                        help="Cetak output dalam format JSON murni")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Tampilkan rincian proses secara detail")

    args = parser.parse_args()

    # Muat konfigurasi
    cfg = load_config(args.config)
    if args.threshold_sexuality is not None:
        cfg["thresholds"]["sexuality"] = args.threshold_sexuality
    if args.threshold_violence is not None:
        cfg["thresholds"]["violence"] = args.threshold_violence
    if args.quarantine_dir is not None:
        cfg["nextcloud"]["quarantine_dir"] = args.quarantine_dir
    if args.action_on_reject is not None:
        cfg["nextcloud"]["action_on_reject"] = args.action_on_reject
    if args.occ_path is not None:
        cfg["nextcloud"]["occ_path"] = args.occ_path

    reject_code = int(cfg.get("nextcloud", {}).get("reject_exit_code", 1))
    clean_code = int(cfg.get("nextcloud", {}).get("clean_exit_code", 0))
    error_code = int(cfg.get("nextcloud", {}).get("error_exit_code", 2))

    if not os.path.exists(args.file):
        if args.json:
            print(json.dumps({"error": f"File tidak ditemukan: {args.file}", "is_rejected": True}))
        else:
            print(f"[ERROR] File '{args.file}' tidak ditemukan!", file=sys.stderr)
        sys.exit(error_code)

    try:
        moderator = ContentModerator(config=cfg)
        result = moderator.scan_file(
            args.file,
            force_engine=args.engine,
            nextcloud_file_id=args.file_id,
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            verdict = result["verdict"]
            is_rejected = result["is_rejected"]
            icon = "❌ REJECTED" if is_rejected else "✅ ALLOWED"
            
            print("=" * 60)
            print(f" HASIL PEMERIKSAAN KONTEN: {icon}")
            print("=" * 60)
            print(f" File        : {result['file']}")
            print(f" Tipe        : {result.get('file_type', 'unknown').upper()}")
            print(f" Engine      : {result.get('engine_used')}")
            print(f" Seksualitas : {result.get('sexuality_score', 0.0):.2f} (Batas: {moderator.threshold_sexuality:.2f})")
            print(f" Kekerasan   : {result.get('violence_score', 0.0):.2f} (Batas: {moderator.threshold_violence:.2f})")
            print(f" Keterangan  : {result.get('details')}")

            if is_rejected:
                print("\n[ALASAN PENOLAKAN]")
                for r in result.get("reasons", []):
                    print(f"  • {r}")
                if "quarantined_to" in result:
                    print(f"  • File dikarantina ke: {result['quarantined_to']}")
            print("=" * 60)

        # Keluar dengan kode sesuai keputusan
        if result["is_rejected"]:
            sys.exit(reject_code)
        else:
            sys.exit(clean_code)

    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e), "is_rejected": True}))
        else:
            print(f"[CRITICAL ERROR] Kegagalan pemindaian: {e}", file=sys.stderr)
        sys.exit(error_code)


if __name__ == "__main__":
    main()
