import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List
from PIL import Image

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".3gp", ".ts"
}

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"
}


def is_video_file(file_path: str) -> bool:
    """Mengecek apakah file merupakan ekstensi video."""
    ext = Path(file_path).suffix.lower()
    return ext in VIDEO_EXTENSIONS


def is_image_file(file_path: str) -> bool:
    """Mengecek apakah file merupakan ekstensi gambar."""
    ext = Path(file_path).suffix.lower()
    return ext in IMAGE_EXTENSIONS


def get_video_duration(video_path: str, ffmpeg_bin: str = "ffmpeg") -> float:
    """Mendapatkan durasi video menggunakan ffprobe / ffmpeg."""
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception:
        # Fallback jika ffprobe tidak ada atau gagal
        return 60.0


def extract_video_frames(
    video_path: str,
    interval_seconds: float = 2.0,
    max_frames: int = 15,
    ffmpeg_bin: str = "ffmpeg"
) -> List[str]:
    """
    Mengekstrak frame dari video pada interval tertentu dan menyimpannya dalam folder temp.
    Mengembalikan daftar path file gambar frame yang diekstrak.
    """
    temp_dir = tempfile.mkdtemp(prefix="mod_frames_")
    output_pattern = os.path.join(temp_dir, "frame_%04d.jpg")

    # Hitung fps filter, misal interval 2 detik -> fps = 1/2 = 0.5
    fps_val = 1.0 / max(interval_seconds, 0.5)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", video_path,
        "-vf", f"fps={fps_val}",
        "-frames:v", str(max_frames),
        "-q:v", "2",
        output_pattern
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError as e:
        # Jika gagal dengan filter fps, coba fallback sederhana mengambil 5 frame pertama
        fallback_cmd = [
            ffmpeg_bin,
            "-y",
            "-i", video_path,
            "-vframes", str(min(max_frames, 5)),
            "-q:v", "2",
            output_pattern
        ]
        try:
            subprocess.run(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return []

    frame_files = sorted([
        os.path.join(temp_dir, f)
        for f in os.listdir(temp_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    ])

    return frame_files


def cleanup_frames(frame_paths: List[str]) -> None:
    """Membersihkan file dan direktori temporary hasil ekstraksi video."""
    if not frame_paths:
        return
    parent_dir = os.path.dirname(frame_paths[0])
    if os.path.isdir(parent_dir) and "mod_frames_" in parent_dir:
        shutil.rmtree(parent_dir, ignore_errors=True)
