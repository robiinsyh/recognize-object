import json
import warnings
from typing import Dict, Any, List
from PIL import Image

warnings.filterwarnings("ignore", message=".*automatic function calling.*")

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


class GeminiModerationEngine:
    """
    Engine moderasi multimodal berbasis Google Gemini Vision API.
    Mendeteksi unsur pornografi/seksualitas dan kekerasan/senjata/gore dengan akurasi tinggi.
    """

    FALLBACK_MODELS = ["gemini-3.7-flash", "gemini-3.5-flash-lite"]

    def __init__(self, api_key: str, model_name: str = "gemini-3.7-flash"):
        if genai is None:
            raise ImportError("Paket 'google-genai' belum terinstall. Jalankan: pip install google-genai")
        
        self.api_key = api_key
        self.model_name = model_name
        self.client = genai.Client(api_key=api_key)

    def analyze_image(self, image_path: str) -> Dict[str, Any]:
        """
        Menganalisis sebuah gambar menggunakan Gemini Vision API.
        """
        prompt = (
            "You are a strict automated content moderation system for Nextcloud file upload filtering. "
            "Analyze this image carefully for two specific forbidden categories:\n"
            "1. SEXUALITY: Nudity (full or partial), sexually explicit acts, lingerie/revealing underwear poses, suggestive anime/drawings, pornography, genitalia.\n"
            "2. VIOLENCE: Weapons (guns, firearms, tactical knives), severe physical assault/abuse, gore, open wounds, decapitation, heavy blood, torture.\n\n"
            "Respond ONLY with a JSON object strictly following this structure:\n"
            "{\n"
            '  "sexuality_score": <float between 0.0 and 1.0>,\n'
            '  "violence_score": <float between 0.0 and 1.0>,\n'
            '  "details": "<short description of any sexual or violent element found, or \'Clean image\'>"\n'
            "}"
        )

        try:
            with Image.open(image_path) as img:
                img_copy = img.copy()

            models_to_try = [self.model_name] + [m for m in self.FALLBACK_MODELS if m != self.model_name]
            last_err = None

            for m in models_to_try:
                try:
                    response = self.client.models.generate_content(
                        model=m,
                        contents=[img_copy, prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.0
                        )
                    )
                    result_text = response.text.strip()
                    data = json.loads(result_text)
                    return {
                        "sexuality_score": float(data.get("sexuality_score", 0.0)),
                        "violence_score": float(data.get("violence_score", 0.0)),
                        "details": str(data.get("details", "")),
                        "method": f"gemini ({m})"
                    }
                except Exception as e:
                    last_err = e
                    continue

            raise last_err

        except Exception as e:
            return {
                "sexuality_score": 0.0,
                "violence_score": 0.0,
                "details": f"Gemini API error: {str(e)}",
                "method": "gemini_error"
            }

    def analyze_frames(self, frame_paths: List[str]) -> Dict[str, Any]:
        """
        Menganalisis serangkaian frame video untuk mencari apakah ada satu saja frame
        yang melanggar aturan seksualitas atau kekerasan.
        """
        max_sexuality = 0.0
        max_violence = 0.0
        worst_detail = "Video bersih"
        violation_frame = None

        for idx, frame_path in enumerate(frame_paths):
            res = self.analyze_image(frame_path)
            s_score = res.get("sexuality_score", 0.0)
            v_score = res.get("violence_score", 0.0)

            if s_score > max_sexuality:
                max_sexuality = s_score
                if s_score >= 0.5:
                    worst_detail = f"[Frame {idx+1}] {res.get('details', '')}"
                    violation_frame = idx + 1

            if v_score > max_violence:
                max_violence = v_score
                if v_score >= 0.5:
                    worst_detail = f"[Frame {idx+1}] {res.get('details', '')}"
                    violation_frame = idx + 1

            # Early stopping: jika sudah jelas melanggar batas parah (> 0.8), langsung stop
            if max_sexuality >= 0.8 or max_violence >= 0.8:
                break

        return {
            "sexuality_score": round(max_sexuality, 3),
            "violence_score": round(max_violence, 3),
            "details": worst_detail,
            "violation_frame": violation_frame,
            "method": f"gemini_video ({self.model_name})"
        }
