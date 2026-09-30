#!/usr/bin/env python3
"""
Unit test dan verifikasi fungsionalitas Content Moderator.
Membuat sampel buatan (gambar aman, gambar vulgar sintetis, gambar kekerasan/darah sintetis,
dan video sintetis) lalu menguji respons penolakan/penerimaan sistem.
"""

import os
import subprocess
import sys
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from moderator.detector import ContentModerator
from moderator.config import load_config


def create_test_samples(samples_dir: str):
    os.makedirs(samples_dir, exist_ok=True)

    # 1. Gambar Bersih / Aman (Pemandangan gradien hijau & biru)
    safe_path = os.path.join(samples_dir, "sample_clean_landscape.jpg")
    img_clean = np.zeros((300, 300, 3), dtype=np.uint8)
    img_clean[:150, :] = [100, 180, 255]  # Langit biru
    img_clean[150:, :] = [40, 160, 40]    # Rumput hijau
    Image.fromarray(img_clean).save(safe_path)

    # 2. Gambar Unsur Seksualitas Sintetis (Area kulit manusia YCbCr > 75%)
    # R=220, G=170, B=140 (warna kulit terang dominan)
    sexuality_path = os.path.join(samples_dir, "sample_simulated_nsfw.jpg")
    img_skin = np.full((300, 300, 3), [225, 175, 145], dtype=np.uint8)
    Image.fromarray(img_skin).save(sexuality_path)

    # 3. Gambar Unsur Kekerasan / Gore Sintetis (Area darah/luka pekat dominan)
    # R=180, G=15, B=15
    gore_path = os.path.join(samples_dir, "sample_simulated_violence.jpg")
    img_gore = np.full((300, 300, 3), [190, 20, 20], dtype=np.uint8)
    Image.fromarray(img_gore).save(gore_path)

    # 4. Video Sintetis Aman menggunakan ffmpeg (3 detik)
    video_path = os.path.join(samples_dir, "sample_safe_video.mp4")
    if not os.path.exists(video_path):
        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "testsrc=duration=3:size=320x240:rate=10",
                "-pix_fmt", "yuv420p",
                video_path
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception as e:
            print(f"[Warning] Gagal membuat video sintetis ffmpeg: {e}")

    return safe_path, sexuality_path, gore_path, video_path


def run_tests():
    samples_dir = os.path.join(Path(__file__).parent, "test_samples")
    print(">>> 1. Menyiapkan sampel gambar & video pengujian...")
    safe_img, nsfw_img, gore_img, safe_vid = create_test_samples(samples_dir)

    print(">>> 2. Menginisialisasi Content Moderator...")
    cfg = load_config()
    moderator = ContentModerator(config=cfg)

    # Test 1: Gambar Bersih
    print("\n[Pengujian 1: Gambar Aman]")
    res1 = moderator.scan_file(safe_img, force_engine="local")
    print(f"Verdict: {res1['verdict']} | Sexuality: {res1['sexuality_score']} | Violence: {res1['violence_score']}")
    assert res1["is_rejected"] is False, "Gambar bersih seharusnya diizinkan (ALLOW)!"
    print("  -> Lolos: Gambar aman diterima.")

    # Test 2: Unsur Seksualitas Sintetis
    print("\n[Pengujian 2: Unsur Seksualitas Sintetis]")
    res2 = moderator.scan_file(nsfw_img, force_engine="local")
    print(f"Verdict: {res2['verdict']} | Sexuality: {res2['sexuality_score']} | Violence: {res2['violence_score']}")
    assert res2["is_rejected"] is True, "Gambar vulgar sintetis harus ditolak (REJECT)!"
    print("  -> Lolos: Konten seksualitas berhasil terdeteksi dan DITOLAK.")

    # Test 3: Unsur Kekerasan / Gore Sintetis
    print("\n[Pengujian 3: Unsur Kekerasan Sintetis]")
    res3 = moderator.scan_file(gore_img, force_engine="local")
    print(f"Verdict: {res3['verdict']} | Sexuality: {res3['sexuality_score']} | Violence: {res3['violence_score']}")
    assert res3["is_rejected"] is True, "Gambar kekerasan/darah sintetis harus ditolak (REJECT)!"
    print("  -> Lolos: Konten kekerasan berhasil terdeteksi dan DITOLAK.")

    # Test 4: Video Aman
    if os.path.exists(safe_vid):
        print("\n[Pengujian 4: Video Aman]")
        res4 = moderator.scan_file(safe_vid, force_engine="local")
        print(f"Verdict: {res4['verdict']} | Sexuality: {res4['sexuality_score']} | Violence: {res4['violence_score']}")
        print(f"Frames analyzed: {res4.get('frames_analyzed', 0)}")
        assert res4["is_rejected"] is False, "Video aman harus diizinkan (ALLOW)!"
        print("  -> Lolos: Video aman diekstrak framenya dan diizinkan.")

    # Test 5: Uji CLI exit code dengan script moderate.py
    print("\n[Pengujian 5: Verifikasi Exit Code CLI]")
    cmd_safe = [sys.executable, "moderate.py", safe_img, "--engine", "local"]
    ret_safe = subprocess.run(cmd_safe, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode
    assert ret_safe == 0, f"CLI exit code untuk safe image harus 0, didapat {ret_safe}"
    print(f"  -> Safe image exit code: {ret_safe} (Clean/Accepted by Nextcloud)")

    cmd_reject = [sys.executable, "moderate.py", nsfw_img, "--engine", "local"]
    ret_reject = subprocess.run(cmd_reject, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode
    assert ret_reject == 1, f"CLI exit code untuk NSFW image harus 1, didapat {ret_reject}"
    print(f"  -> Rejected image exit code: {ret_reject} (Rejected by Nextcloud)")

    print("\n" + "=" * 50)
    print(" SEMUA PENGUJIAN OTOMATIS BERHASIL DENGAN SEMPURNA!")
    print("=" * 50)


if __name__ == "__main__":
    run_tests()
