"""Sightengine moderation engine for local image/video files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

import requests


class SightengineModerationError(RuntimeError):
    """Raised when Sightengine cannot produce a trustworthy moderation result."""


class SightengineModerationEngine:
    """Moderate images and short videos through Sightengine's upload APIs."""

    IMAGE_ENDPOINT = "https://api.sightengine.com/1.0/check.json"
    VIDEO_ENDPOINT = "https://api.sightengine.com/1.0/video/check-sync.json"

    def __init__(
        self,
        api_user: str,
        api_secret: str,
        models: str = "nudity-2.1,violence,weapon,gore-2.0",
        timeout_seconds: float = 90.0,
    ) -> None:
        if not api_user or not api_secret:
            raise ValueError("SIGHTENGINE_API_USER dan SIGHTENGINE_API_SECRET wajib diisi.")
        self.api_user = api_user
        self.api_secret = api_secret
        self.models = ",".join(x.strip() for x in models.split(",") if x.strip())
        if not self.models:
            raise ValueError("Sightengine models tidak boleh kosong.")
        self.timeout_seconds = max(float(timeout_seconds), 5.0)

    def _request_file(self, endpoint: str, file_path: str) -> Dict[str, Any]:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"File tidak ditemukan: {file_path}")

        data = {
            "models": self.models,
            "api_user": self.api_user,
            "api_secret": self.api_secret,
        }
        try:
            with path.open("rb") as media:
                response = requests.post(
                    endpoint,
                    data=data,
                    files={"media": (path.name, media)},
                    timeout=self.timeout_seconds,
                )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise SightengineModerationError(f"Sightengine request gagal: {exc}") from exc
        except ValueError as exc:
            raise SightengineModerationError("Sightengine mengembalikan JSON tidak valid.") from exc

        if payload.get("status") != "success":
            error = payload.get("error") or payload.get("message") or "status bukan success"
            raise SightengineModerationError(f"Sightengine moderation gagal: {error}")
        return payload

    @staticmethod
    def _numeric_values(value: Any, ignored_keys: Iterable[str] = ()) -> list[float]:
        ignored = set(ignored_keys)
        values: list[float] = []
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ignored:
                    continue
                values.extend(SightengineModerationEngine._numeric_values(child, ignored))
        elif isinstance(value, (int, float)) and 0.0 <= float(value) <= 1.0:
            values.append(float(value))
        return values

    @classmethod
    def _sexuality_score(cls, payload: Dict[str, Any]) -> float:
        nudity = payload.get("nudity", {})
        # "none" and context are confidence values for safe/context classes,
        # not forbidden-content scores.
        values = cls._numeric_values(nudity, ignored_keys={"none", "context"})
        return max(values, default=0.0)

    @classmethod
    def _violence_score(cls, payload: Dict[str, Any]) -> float:
        values: list[float] = []
        for key in ("violence", "gore", "weapon"):
            values.extend(cls._numeric_values(payload.get(key, {}), ignored_keys={"none", "safe", "context"}))
        return max(values, default=0.0)

    @classmethod
    def _frame_scores(cls, frame: Dict[str, Any]) -> tuple[float, float]:
        return cls._sexuality_score(frame), cls._violence_score(frame)

    def analyze_image(self, image_path: str) -> Dict[str, Any]:
        payload = self._request_file(self.IMAGE_ENDPOINT, image_path)
        sexuality = self._sexuality_score(payload)
        violence = self._violence_score(payload)
        return {
            "sexuality_score": round(sexuality, 3),
            "violence_score": round(violence, 3),
            "details": self._details(payload, sexuality, violence),
            "method": "sightengine",
            "request_id": payload.get("request", {}).get("id"),
        }

    def analyze_video(self, video_path: str) -> Dict[str, Any]:
        payload = self._request_file(self.VIDEO_ENDPOINT, video_path)
        frames = payload.get("data", {}).get("frames", [])
        if not isinstance(frames, list) or not frames:
            raise SightengineModerationError("Sightengine tidak mengembalikan frame video.")

        max_sexuality = 0.0
        max_violence = 0.0
        worst_frame = None
        worst_detail = "Video bersih"
        for index, frame in enumerate(frames, start=1):
            if not isinstance(frame, dict):
                continue
            sexuality, violence = self._frame_scores(frame)
            if sexuality > max_sexuality or violence > max_violence:
                max_sexuality = max(max_sexuality, sexuality)
                max_violence = max(max_violence, violence)
                worst_frame = index
                worst_detail = self._details(frame, sexuality, violence)

        return {
            "sexuality_score": round(max_sexuality, 3),
            "violence_score": round(max_violence, 3),
            "details": f"[Frame {worst_frame}] {worst_detail}" if worst_frame else worst_detail,
            "violation_frame": worst_frame,
            "frames_analyzed": len(frames),
            "method": "sightengine_video",
            "request_id": payload.get("request", {}).get("id"),
        }

    @staticmethod
    def _details(payload: Dict[str, Any], sexuality: float, violence: float) -> str:
        labels = []
        if sexuality > 0:
            labels.append(f"Sightengine nudity/sexual score={sexuality:.3f}")
        if violence > 0:
            labels.append(f"Sightengine violence/gore/weapon score={violence:.3f}")
        return "; ".join(labels) if labels else "No flagged Sightengine moderation signal"
