import json
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from .config import load_config
from .local_engine import LocalModerationEngine
from .gemini_engine import GeminiModerationEngine
from .sightengine_engine import SightengineModerationEngine
from .video_utils import (
    is_video_file,
    is_image_file,
    extract_video_frames,
    cleanup_frames,
)


class ContentModerator:
    """
    Moderator terpadu yang memadukan Gemini AI dan Local Computer Vision engine.
    Didesain khusus untuk integrasi Nextcloud (mengembalikan status REJECT/ALLOW dan kode exit 1/0).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_config()

        self.threshold_sexuality = float(self.config["thresholds"].get("sexuality", 0.6))
        self.threshold_violence = float(self.config["thresholds"].get("violence", 0.6))

        # Inisialisasi engine lokal
        self.local_engine = LocalModerationEngine()

        # Inisialisasi Gemini AI engine jika key tersedia
        self.gemini_engine = None
        gemini_cfg = self.config.get("gemini", {})
        gemini_key = gemini_cfg.get("api_key", "").strip()
        model_name = gemini_cfg.get("model", "gemini-2.5-flash")

        if gemini_key:
            try:
                self.gemini_engine = GeminiModerationEngine(api_key=gemini_key, model_name=model_name)
            except Exception as e:
                print(f"[Warning] Gagal menginisialisasi Gemini Engine: {e}")

        self.sightengine_engine = None
        sight_cfg = self.config.get("sightengine", {})
        sight_user = sight_cfg.get("api_user", "").strip()
        sight_secret = sight_cfg.get("api_secret", "").strip()
        if sight_user and sight_secret:
            try:
                self.sightengine_engine = SightengineModerationEngine(
                    api_user=sight_user,
                    api_secret=sight_secret,
                    models=sight_cfg.get("models", "nudity-2.1,violence,weapon,gore-2.0"),
                    timeout_seconds=float(sight_cfg.get("timeout_seconds", 90)),
                )
            except Exception as e:
                print(f"[Warning] Gagal menginisialisasi Sightengine: {e}")

        # Setup logging
        self._setup_logger()

    def _setup_logger(self):
        log_file = self.config.get("nextcloud", {}).get("log_file", "moderation.log")
        self.logger = logging.getLogger("NextcloudModerator")
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            handler = logging.FileHandler(log_file, encoding="utf-8")
            formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def scan_file(
        self,
        file_path: str,
        force_engine: Optional[str] = None,
        nextcloud_file_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Memindai file gambar atau video dan mengembalikan hasil analisis lengkap.
        """
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File tidak ditemukan: {abs_path}")

        engine_mode = (force_engine or self.config.get("engine", "auto")).lower()
        use_gemini = False
        use_sightengine = False

        if engine_mode == "gemini":
            if not self.gemini_engine:
                raise ValueError("Engine diatur 'gemini', namun GEMINI_API_KEY belum dikonfigurasi.")
            use_gemini = True
        elif engine_mode == "sightengine":
            if not self.sightengine_engine:
                raise ValueError("Engine diatur 'sightengine', namun SIGHTENGINE_API_USER/SECRET belum dikonfigurasi.")
            use_sightengine = True
        elif engine_mode == "local":
            use_gemini = False
        else:  # "auto"
            # Prefer Sightengine when configured, then Gemini, then local.
            use_sightengine = self.sightengine_engine is not None
            use_gemini = not use_sightengine and self.gemini_engine is not None

        # Routing berdasarkan tipe file: Video atau Gambar
        if is_video_file(abs_path):
            result = self._scan_video(abs_path, use_gemini=use_gemini, use_sightengine=use_sightengine)
        elif is_image_file(abs_path):
            result = self._scan_image(abs_path, use_gemini=use_gemini, use_sightengine=use_sightengine)
        else:
            # File tipe lain (dokumen/zip/dll): dilewatkan sebagai bersih secara default
            result = {
                "file": abs_path,
                "file_type": "other",
                "is_rejected": False,
                "verdict": "ALLOW",
                "sexuality_score": 0.0,
                "violence_score": 0.0,
                "details": "File bukan gambar/video, otomatis diizinkan.",
                "engine_used": "bypass"
            }

        # Evaluasi akhir penolakan
        s_score = result.get("sexuality_score", 0.0)
        v_score = result.get("violence_score", 0.0)

        sexuality_violated = s_score >= self.threshold_sexuality
        violence_violated = v_score >= self.threshold_violence
        is_rejected = sexuality_violated or violence_violated

        reasons = []
        if sexuality_violated:
            reasons.append(f"Sexuality score ({s_score:.2f} >= {self.threshold_sexuality})")
        if violence_violated:
            reasons.append(f"Violence score ({v_score:.2f} >= {self.threshold_violence})")

        result["is_rejected"] = is_rejected
        result["verdict"] = "REJECT" if is_rejected else "ALLOW"
        result["reasons"] = reasons
        result["timestamp"] = datetime.now().isoformat()

        # Tindakan jika file ditolak. Default "none" sengaja non-destruktif.
        action_on_reject = self.config.get("nextcloud", {}).get("action_on_reject", "none").lower()
        quarantine_dir = self.config.get("nextcloud", {}).get("quarantine_dir", "").strip()

        if is_rejected:
            if action_on_reject == "delete":
                result.update(self._delete_with_occ(nextcloud_file_id))
            elif action_on_reject == "quarantine" or quarantine_dir:
                qdir = quarantine_dir or os.path.join(Path(__file__).resolve().parent.parent, "quarantine")
                os.makedirs(qdir, exist_ok=True)
                dest = os.path.join(qdir, os.path.basename(abs_path))
                try:
                    shutil.move(abs_path, dest)
                    result["quarantined_to"] = dest
                    result["action_taken"] = "quarantined"
                except Exception as e:
                    result["quarantine_error"] = str(e)

        # Logging log hasil scan
        log_msg = (
            f"Verdict: {result['verdict']} | File: {abs_path} | "
            f"Sexuality: {s_score:.2f} | Violence: {v_score:.2f} | Engine: {result.get('engine_used')} | "
            f"Details: {result.get('details')}"
        )
        if is_rejected:
            self.logger.warning(log_msg)
        else:
            self.logger.info(log_msg)

        return result

    def _delete_with_occ(self, nextcloud_file_id: Optional[str]) -> Dict[str, Any]:
        """Delete a rejected Nextcloud file through OCC using its numeric file ID.

        This method is intentionally opt-in. It never falls back to deleting the
        absolute path directly, because the scanner may receive a temporary path
        from Workflow Script rather than the canonical Nextcloud storage path.
        """
        nc_cfg = self.config.get("nextcloud", {})
        occ_path = str(nc_cfg.get("occ_path", "")).strip()
        occ_php = str(nc_cfg.get("occ_php", "php")).strip() or "php"
        timeout = max(float(nc_cfg.get("occ_timeout_seconds", 30)), 1.0)

        if not occ_path:
            return {"delete_error": "action_on_reject=delete tetapi nextcloud.occ_path belum dikonfigurasi."}
        if not nextcloud_file_id or not str(nextcloud_file_id).isdigit():
            return {"delete_error": "action_on_reject=delete membutuhkan file ID numerik dari placeholder Workflow %i."}
        if not os.path.isfile(occ_path):
            return {"delete_error": f"File OCC tidak ditemukan: {occ_path}"}

        # Symfony Console option yang benar: files:delete --force -- <file_id>.
        # Separator "--" memastikan file ID tidak diperlakukan sebagai option.
        command = [occ_php, occ_path, "files:delete", "--force", "--", str(nextcloud_file_id)]
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"delete_error": f"Gagal menjalankan OCC: {exc}", "occ_command": command}

        if completed.returncode != 0:
            return {
                "delete_error": (completed.stderr or completed.stdout or "OCC mengembalikan error").strip(),
                "occ_exit_code": completed.returncode,
                "occ_command": command,
            }
        return {
            "action_taken": "deleted_via_occ",
            "occ_exit_code": completed.returncode,
            "occ_command": command,
        }

    def _scan_image(self, image_path: str, use_gemini: bool, use_sightengine: bool = False) -> Dict[str, Any]:
        """Pindai satu file gambar."""
        if use_sightengine and self.sightengine_engine:
            res = self.sightengine_engine.analyze_image(image_path)
            engine_name = "sightengine"
        elif use_gemini and self.gemini_engine:
            res = self.gemini_engine.analyze_image(image_path)
            engine_name = "gemini"
        else:
            res = self.local_engine.analyze_image(image_path)
            engine_name = res.get("method", "local_heuristic")

        return {
            "file": image_path,
            "file_type": "image",
            "sexuality_score": res.get("sexuality_score", 0.0),
            "violence_score": res.get("violence_score", 0.0),
            "details": res.get("details", ""),
            "engine_used": engine_name
        }

    def _scan_video(self, video_path: str, use_gemini: bool, use_sightengine: bool = False) -> Dict[str, Any]:
        """Pindai file video dengan sampling frame ffmpeg."""
        if use_sightengine and self.sightengine_engine:
            res = self.sightengine_engine.analyze_video(video_path)
            res.update({"file": video_path, "file_type": "video", "engine_used": "sightengine_video"})
            return res

        vid_cfg = self.config.get("video", {})
        interval = float(vid_cfg.get("sample_interval_seconds", 2.0))
        max_f = int(vid_cfg.get("max_frames", 15))
        ffmpeg_bin = vid_cfg.get("ffmpeg_path", "ffmpeg")

        frames = extract_video_frames(video_path, interval_seconds=interval, max_frames=max_f, ffmpeg_bin=ffmpeg_bin)
        if not frames:
            return {
                "file": video_path,
                "file_type": "video",
                "sexuality_score": 0.0,
                "violence_score": 0.0,
                "details": "Tidak dapat mengekstrak frame dari video (mungkin format tidak valid atau rusak)",
                "engine_used": "video_extractor_fallback"
            }

        try:
            if use_gemini and self.gemini_engine:
                res = self.gemini_engine.analyze_frames(frames)
                engine_name = "gemini_video"
            else:
                # Local analysis frame by frame
                max_s = 0.0
                max_v = 0.0
                worst_detail = "Video bersih"
                worst_frame = None

                for idx, frame_p in enumerate(frames):
                    f_res = self.local_engine.analyze_image(frame_p)
                    s_sc = f_res.get("sexuality_score", 0.0)
                    v_sc = f_res.get("violence_score", 0.0)

                    if s_sc > max_s:
                        max_s = s_sc
                        worst_detail = f"[Frame {idx+1}] {f_res.get('details', '')}"
                        worst_frame = idx + 1
                    if v_sc > max_v:
                        max_v = v_sc
                        worst_detail = f"[Frame {idx+1}] {f_res.get('details', '')}"
                        worst_frame = idx + 1

                    # Early stop
                    if max_s >= self.threshold_sexuality or max_v >= self.threshold_violence:
                        break

                res = {
                    "sexuality_score": round(max_s, 3),
                    "violence_score": round(max_v, 3),
                    "details": worst_detail,
                    "violation_frame": worst_frame
                }
                engine_name = "local_video"

            res.update({
                "file": video_path,
                "file_type": "video",
                "frames_analyzed": len(frames),
                "engine_used": engine_name
            })
            return res

        finally:
            cleanup_frames(frames)
