#!/usr/bin/env python3
"""
Nextcloud Directory Watcher Daemon.
Memantau direktori data Nextcloud secara otomatis untuk memindai setiap file
foto/video baru. Jika ditemukan unsur seksualitas atau kekerasan, file akan
segera dihapus/dikarantina sebelum pengguna lain dapat mengaksesnya.

Penggunaan:
    python nextcloud_watcher.py /var/www/nextcloud/data/
    python nextcloud_watcher.py /path/to/folder --quarantine /path/to/quarantine
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from moderator.config import load_config
from moderator.detector import ContentModerator
from moderator.video_utils import is_image_file, is_video_file


def watch_directory(watch_dir: str, moderator: ContentModerator, poll_interval: float = 3.0):
    watch_path = Path(watch_dir).resolve()
    print(f"[Watcher] Memulai pemantauan direktori: {watch_path}")
    print(f"[Watcher] Interval pemindaian: {poll_interval} detik")

    scanned_files = set()

    # Pre-populate file yang sudah ada agar tidak di-scan ulang saat startup
    for root, _, files in os.walk(watch_path):
        for f in files:
            fp = os.path.join(root, f)
            scanned_files.add(fp)

    print(f"[Watcher] Siap. Menunggu file baru diupload...")

    try:
        while True:
            current_files = []
            for root, _, files in os.walk(watch_path):
                # Lewatkan folder recycle bin / cache Nextcloud
                if "files_trashbin" in root or "cache" in root or "appdata_" in root:
                    continue
                for f in files:
                    fp = os.path.join(root, f)
                    if fp not in scanned_files:
                        current_files.append(fp)

            for fp in current_files:
                scanned_files.add(fp)
                if not (is_image_file(fp) or is_video_file(fp)):
                    continue

                # Tunggu file selesai ditulis sepenuhnya jika ukuran bertambah
                try:
                    init_size = os.path.getsize(fp)
                    time.sleep(0.5)
                    if os.path.getsize(fp) != init_size:
                        time.sleep(1.0)
                except Exception:
                    continue

                print(f"[Watcher] Mendeteksi file baru: {fp}")
                try:
                    result = moderator.scan_file(fp)
                    if result["is_rejected"]:
                        print(f"❌ [DITOLAK] {fp} melanggar kebijakan!")
                        print(f"   Alasan: {result.get('reasons')}")
                        # Jika tidak dipindahkan ke karantina, hapus file untuk melindungi sistem
                        if "quarantined_to" not in result and os.path.exists(fp):
                            os.remove(fp)
                            print(f"   File telah dihapus otomatis dari server.")
                    else:
                        print(f"✅ [AMAN] {fp} lolos verifikasi.")
                except Exception as e:
                    print(f"⚠️ [Error] Gagal memindai {fp}: {e}")

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\n[Watcher] Pemantauan dihentikan.")


def main():
    parser = argparse.ArgumentParser(description="Nextcloud Directory Watcher Daemon")
    parser.add_argument("watch_dir", help="Direktori data Nextcloud yang ingin dipantau")
    parser.add_argument("--quarantine", default=None, help="Direktori karantina untuk file terlarang")
    parser.add_argument("--interval", type=float, default=3.0, help="Interval polling dalam detik")
    args = parser.parse_args()

    cfg = load_config()
    if args.quarantine:
        cfg["nextcloud"]["quarantine_dir"] = args.quarantine

    if not os.path.isdir(args.watch_dir):
        print(f"Error: Direktori '{args.watch_dir}' tidak ditemukan!", file=sys.stderr)
        sys.exit(1)

    moderator = ContentModerator(config=cfg)
    watch_directory(args.watch_dir, moderator, poll_interval=args.interval)


if __name__ == "__main__":
    main()
