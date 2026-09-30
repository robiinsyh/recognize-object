import os
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np
from PIL import Image

try:
    import onnxruntime as ort
except ImportError:
    ort = None


class LocalModerationEngine:
    """
    Engine moderasi lokal offline untuk deteksi cepat tanpa ketergantungan internet/API luar.
    Mendukung model ONNX jika tersedia, atau fallback berbasis computer vision heuristik
    (Skin-tone surface ratio, chromaticity segmentation, and blood/gore color distribution).
    """

    def __init__(self, model_path: Optional[str] = None):
        self.onnx_session = None
        # Cek jika ada model ONNX yang disediakan
        default_model = Path(__file__).resolve().parent.parent / "models" / "nsfw.onnx"
        chosen_path = model_path or (str(default_model) if default_model.exists() else None)

        if chosen_path and os.path.exists(chosen_path) and ort is not None:
            try:
                self.onnx_session = ort.InferenceSession(chosen_path, providers=['CPUExecutionProvider'])
                self.model_input_name = self.onnx_session.get_inputs()[0].name
            except Exception as e:
                print(f"[Warning] Gagal memuat model ONNX ({e}). Menggunakan heuristic fallback.")
                self.onnx_session = None

    def analyze_image(self, image_path: str) -> Dict[str, Any]:
        """
        Menganalisis file gambar untuk mendeteksi unsur seksualitas dan kekerasan.
        """
        try:
            with Image.open(image_path) as img:
                img = img.convert("RGB")
                # Resize untuk efisiensi komputasi
                img.thumbnail((400, 400), Image.Resampling.BILINEAR)
                arr = np.array(img, dtype=np.float32)
        except Exception as e:
            return {
                "sexuality_score": 0.0,
                "violence_score": 0.0,
                "details": f"Error membaca gambar: {str(e)}",
                "method": "error"
            }

        # 1. Analisis Seksualitas / Nudity (Skin Chromaticity & Surface Ratio)
        sexuality_score, skin_detail = self._detect_nudity_heuristic(arr)

        # 2. Analisis Kekerasan / Gore (Blood/Wound red color clustering & edge contrast)
        violence_score, violence_detail = self._detect_violence_heuristic(arr)

        # 3. Jika model ONNX aktif, kombinasikan hasil
        if self.onnx_session is not None:
            onnx_sexuality = self._run_onnx_inference(arr)
            if onnx_sexuality is not None:
                sexuality_score = max(sexuality_score, onnx_sexuality)
                skin_detail += f" | ONNX model score: {onnx_sexuality:.2f}"

        details = f"{skin_detail}. {violence_detail}"

        return {
            "sexuality_score": round(float(sexuality_score), 3),
            "violence_score": round(float(violence_score), 3),
            "details": details,
            "method": "onnx+heuristic" if self.onnx_session else "local_heuristic"
        }

    def _detect_nudity_heuristic(self, rgb_arr: np.ndarray) -> tuple[float, str]:
        """
        Mendeteksi rasio kulit manusia menggunakan konversi YCbCr dan HSV.
        Rumus standar Kovac / Peer & Solina untuk segmentasi kulit universal.
        """
        r = rgb_arr[:, :, 0]
        g = rgb_arr[:, :, 1]
        b = rgb_arr[:, :, 2]

        total_pixels = rgb_arr.shape[0] * rgb_arr.shape[1]
        if total_pixels == 0:
            return 0.0, "Gambar kosong"

        # Konversi ke YCbCr sederhana
        # Y = 0.299R + 0.587G + 0.114B
        # Cb = -0.1687R - 0.3313G + 0.5B + 128
        # Cr = 0.5R - 0.4187G - 0.0813B + 128
        cb = -0.1687 * r - 0.3313 * g + 0.5 * b + 128
        cr = 0.5 * r - 0.4187 * g - 0.0813 * b + 128

        # Skin mask dalam YCbCr (Universal human skin chromaticity range)
        skin_mask = (cb >= 77) & (cb <= 127) & (cr >= 133) & (cr <= 173)

        # Tambahan filter kondisi RGB dasar
        rgb_condition = (r > 95) & (g > 40) & (b > 20) & ((r - g) > 15) & (r > b)
        combined_mask = skin_mask & rgb_condition

        skin_pixels = np.count_nonzero(combined_mask)
        skin_ratio = skin_pixels / total_pixels

        # Evaluasi proporsi kulit
        # - Foto wajah biasa / potret normal biasanya memiliki rasio kulit 10% - 25%
        # - Foto vulgar / telanjang biasanya memiliki rasio kulit > 40% - 50%
        if skin_ratio >= 0.50:
            score = min(1.0, 0.70 + (skin_ratio - 0.50) * 0.6)
            detail = f"High exposed skin coverage ({skin_ratio * 100:.1f}%)"
        elif skin_ratio >= 0.35:
            score = 0.45 + (skin_ratio - 0.35) * 1.5
            detail = f"Moderate skin coverage ({skin_ratio * 100:.1f}%)"
        else:
            score = max(0.0, skin_ratio * 0.8)
            detail = f"Normal skin coverage ({skin_ratio * 100:.1f}%)"

        return score, detail

    def _detect_violence_heuristic(self, rgb_arr: np.ndarray) -> tuple[float, str]:
        """
        Mendeteksi potensi luka/darah/gore pekat melalui analisis dominansi spektrum merah pekat (Blood/Gore Hue).
        """
        r = rgb_arr[:, :, 0]
        g = rgb_arr[:, :, 1]
        b = rgb_arr[:, :, 2]

        total_pixels = rgb_arr.shape[0] * rgb_arr.shape[1]
        if total_pixels == 0:
            return 0.0, "Gambar kosong"

        # Deteksi pixel merah darah/luka pekat:
        # R tinggi, G dan B rendah (R > 120, G < 60, B < 60, dan R > 2.5 * max(G, B))
        max_gb = np.maximum(g, b)
        blood_mask = (r >= 110) & (max_gb <= 75) & (r > 2.2 * (max_gb + 1))

        blood_pixels = np.count_nonzero(blood_mask)
        blood_ratio = blood_pixels / total_pixels

        # Analisis rasio
        if blood_ratio >= 0.15:
            score = min(1.0, 0.75 + (blood_ratio - 0.15) * 1.5)
            detail = f"Extremely high deep-red/blood concentration ({blood_ratio * 100:.1f}%)"
        elif blood_ratio >= 0.07:
            score = 0.45 + (blood_ratio - 0.07) * 3.0
            detail = f"Elevated red/gore concentration ({blood_ratio * 100:.1f}%)"
        else:
            score = max(0.0, blood_ratio * 3.0)
            detail = f"No excessive blood/gore pattern ({blood_ratio * 100:.1f}%)"

        return score, detail

    def _run_onnx_inference(self, rgb_arr: np.ndarray) -> Optional[float]:
        """Menjalankan inferensi model ONNX jika model tersedia."""
        if self.onnx_session is None:
            return None
        try:
            # Resize ke 224x224 untuk model klasifikasi standar
            from PIL import Image
            pil_img = Image.fromarray(rgb_arr.astype(np.uint8)).resize((224, 224))
            inp = np.array(pil_img, dtype=np.float32) / 255.0
            # [H, W, C] -> [1, C, H, W]
            inp = np.transpose(inp, (2, 0, 1))
            inp = np.expand_dims(inp, axis=0)

            outputs = self.onnx_session.run(None, {self.model_input_name: inp})
            # Misal output probabilitas binary [safe, nsfw]
            probs = outputs[0][0]
            if len(probs) >= 2:
                # Softmax jika belum
                exp_p = np.exp(probs - np.max(probs))
                softmax_p = exp_p / np.sum(exp_p)
                return float(softmax_p[1])
            return float(probs[0])
        except Exception:
            return None
