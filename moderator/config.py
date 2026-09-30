import json
import os
from pathlib import Path
from typing import Any, Dict


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    """
    Memuat konfigurasi dari config.json dan environment variable.
    """
    default_config: Dict[str, Any] = {
        "engine": "auto",
        "gemini": {
            "api_key": "",
            "model": "gemini-3.8-flash"
        },
        "sightengine": {
            "api_user": "",
            "api_secret": "",
            "models": "nudity-2.1,violence,weapon,gore-2.0",
            "timeout_seconds": 90
        },
        "thresholds": {
            "sexuality": 0.6,
            "violence": 0.6
        },
        "video": {
            "sample_interval_seconds": 2.0,
            "max_frames": 15,
            "ffmpeg_path": "ffmpeg"
        },
        "nextcloud": {
            "reject_exit_code": 1,
            "clean_exit_code": 0,
            "error_exit_code": 2,
            "log_file": "moderation.log",
            "quarantine_dir": "",
            "action_on_reject": "none",
            "occ_path": "",
            "occ_php": "php",
            "occ_timeout_seconds": 30
        }
    }

    # Cari file config.json di lokasi saat ini atau folder kerja
    if config_path is None:
        possible_paths = [
            Path.cwd() / "config.json",
            Path(__file__).resolve().parent.parent / "config.json"
        ]
        for p in possible_paths:
            if p.exists():
                config_path = str(p)
                break

    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                # Deep merge konfigurasi sederhana
                for k, v in loaded.items():
                    if isinstance(v, dict) and k in default_config and isinstance(default_config[k], dict):
                        default_config[k].update(v)
                    else:
                        default_config[k] = v
        except Exception as e:
            print(f"[Warning] Gagal membaca config.json ({e}), menggunakan default.")
    # Cari dan muat file .env secara otomatis
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env"
    ]
    for ep in env_paths:
        if ep.exists():
            try:
                with open(ep, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass
            break

    # Override dari environment variables
    env_gemini_key = os.environ.get("GEMINI_API_KEY")
    if env_gemini_key:
        default_config["gemini"]["api_key"] = env_gemini_key

    env_sightengine_user = os.environ.get("SIGHTENGINE_API_USER")
    if env_sightengine_user:
        default_config["sightengine"]["api_user"] = env_sightengine_user

    env_sightengine_secret = os.environ.get("SIGHTENGINE_API_SECRET")
    if env_sightengine_secret:
        default_config["sightengine"]["api_secret"] = env_sightengine_secret

    env_engine = os.environ.get("MODERATION_ENGINE")
    if env_engine:
        default_config["engine"] = env_engine.lower()

    if os.environ.get("SEXUALITY_THRESHOLD"):
        try:
            default_config["thresholds"]["sexuality"] = float(os.environ["SEXUALITY_THRESHOLD"])
        except ValueError:
            pass

    if os.environ.get("VIOLENCE_THRESHOLD"):
        try:
            default_config["thresholds"]["violence"] = float(os.environ["VIOLENCE_THRESHOLD"])
        except ValueError:
            pass

    return default_config
