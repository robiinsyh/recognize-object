#!/usr/bin/env python3
"""Offline tests for Sightengine response normalization."""

from moderator.sightengine_engine import SightengineModerationEngine


IMAGE_RESPONSE = {
    "status": "success",
    "request": {"id": "req-image"},
    "nudity": {
        "sexual_activity": 0.81,
        "sexual_display": 0.72,
        "none": 0.12,
        "context": {"indoor_other": 0.99},
    },
    "gore": {"prob": 0.18},
    "weapon": {"firearm": 0.66},
}

VIDEO_RESPONSE = {
    "status": "success",
    "request": {"id": "req-video"},
    "data": {
        "frames": [
            {"info": {"position": 0}, "nudity": {"sexual_activity": 0.10, "none": 0.9}},
            {"info": {"position": 2000}, "nudity": {"sexual_activity": 0.20, "none": 0.8}, "violence": {"fight": 0.77}},
        ]
    },
}


def test_image_scores():
    sexuality = SightengineModerationEngine._sexuality_score(IMAGE_RESPONSE)
    violence = SightengineModerationEngine._violence_score(IMAGE_RESPONSE)
    assert sexuality == 0.81
    assert violence == 0.66


def test_video_scores():
    frames = VIDEO_RESPONSE["data"]["frames"]
    scores = [SightengineModerationEngine._frame_scores(frame) for frame in frames]
    assert scores == [(0.1, 0.0), (0.2, 0.77)]


if __name__ == "__main__":
    test_image_scores()
    test_video_scores()
    print("Sightengine normalization tests passed")
