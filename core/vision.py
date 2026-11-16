import io
import os
import time
import base64
import json
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

try:
    from PIL import ImageGrab, Image
except (ImportError, ModuleNotFoundError):
    ImageGrab = None
    Image = None

try:
    import cv2
except (ImportError, ModuleNotFoundError):
    cv2 = None

import config

logger = logging.getLogger("JarvisVision")

class VisionManager:
    """
    Visual Perception & Multimodal Intelligence Engine for Jarvis.
    Enables Jarvis to see using live screen capture and laptop webcam feeds,
    analyzed in real time using Google Gemini Multimodal Vision models.
    """

    def __init__(self, api_key: str = config.GEMINI_API_KEY, models: Optional[List[str]] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.models = models or [
            "gemini-flash-lite-latest",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "gemini-3.8-flash"
        ]

    # =====================================================================
    # 1. SCREEN CAPTURE
    # =====================================================================

    def capture_screen(self, max_dimension: int = 1920, quality: int = 80) -> Optional[bytes]:
        """
        Captures the current active desktop screen, scales if necessary to preserve bandwidth,
        and returns JPEG image bytes.
        """
        if ImageGrab is None:
            logger.debug("[-] Pillow / ImageGrab is not available in this environment.")
            return None

        try:
            img = ImageGrab.grab()
            # Downscale if larger than max_dimension
            width, height = img.size
            if max(width, height) > max_dimension:
                scale = max_dimension / float(max(width, height))
                new_size = (int(width * scale), int(height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # Convert RGBA to RGB for JPEG encoding
            if img.mode != "RGB":
                img = img.convert("RGB")

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            return buf.getvalue()
        except Exception as e:
            logger.error(f"[-] Screen capture failed: {e}")
            return None

    def save_screen_to_file(self, filename: Optional[str] = None) -> Optional[Path]:
        """Captures desktop screen and saves directly to disk in the temp cache directory."""
        img_bytes = self.capture_screen()
        if not img_bytes:
            return None

        if not filename:
            filename = f"screenshot_{int(time.time())}.jpg"

        file_path = config.AUDIO_DIR / filename
        try:
            file_path.write_bytes(img_bytes)
            return file_path
        except Exception as e:
            logger.error(f"[-] Failed to save screenshot to file: {e}")
            return None

    # =====================================================================
    # 2. WEBCAM CAPTURE
    # =====================================================================

    def capture_webcam(self, device_index: int = 0, quality: int = 85) -> Optional[bytes]:
        """
        Captures a single frame from the laptop webcam using OpenCV.
        Returns JPEG bytes or None if camera is unavailable or locked.
        """
        try:
            import cv2
        except ImportError:
            logger.warning("[-] OpenCV (cv2) is not installed; webcam capture unavailable.")
            return None

        cap = None
        # Try MSMF and default DirectShow backends on Windows
        for backend in [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]:
            try:
                cap = cv2.VideoCapture(device_index, backend)
                if cap and cap.isOpened():
                    break
            except Exception:
                cap = None

        if not cap or not cap.isOpened():
            logger.debug("[-] Webcam hardware is not opened or accessible.")
            return None

        try:
            # Discard first few frames to allow sensor auto-exposure to stabilize
            for _ in range(4):
                cap.read()

            ret, frame = cap.read()
            if not ret or frame is None:
                return None

            # Encode BGR OpenCV frame to JPEG bytes
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            success, encoded_img = cv2.imencode(".jpg", frame, encode_param)
            if success:
                return encoded_img.tobytes()
            return None
        except Exception as e:
            logger.error(f"[-] Webcam frame reading failed: {e}")
            return None
        finally:
            if cap:
                cap.release()

    def save_webcam_to_file(self, filename: Optional[str] = None) -> Optional[Path]:
        """Captures a webcam snapshot and saves it to disk."""
        img_bytes = self.capture_webcam()
        if not img_bytes:
            return None

        if not filename:
            filename = f"webcam_{int(time.time())}.jpg"

        file_path = config.AUDIO_DIR / filename
        try:
            file_path.write_bytes(img_bytes)
            return file_path
        except Exception as e:
            logger.error(f"[-] Failed to save webcam snapshot: {e}")
            return None

    # =====================================================================
    # 3. GEMINI MULTIMODAL VISION REASONING
    # =====================================================================

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        system_instruction: str = "",
        mime_type: str = "image/jpeg"
    ) -> str:
        """
        Sends an image along with a reasoning prompt to Gemini Multimodal Vision API.
        """
        if not self.api_key:
            return "Sir, the Gemini API key is missing. Please configure GEMINI_API_KEY in your .env file."

        if not image_bytes:
            return "Sir, no image data was received for visual analysis."

        encoded_img = base64.b64encode(image_bytes).decode("utf-8")

        parts = [
            {
                "inlineData": {
                    "mimeType": mime_type,
                    "data": encoded_img
                }
            },
            {
                "text": prompt
            }
        ]

        payload: Dict[str, Any] = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 900
            }
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        last_error = ""
        for model in self.models:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=22) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    candidates = result.get("candidates", [])
                    if candidates:
                        text = candidates[0]["content"]["parts"][0]["text"].strip()
                        return text
            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code} ({model})"
                continue
            except Exception as e:
                last_error = f"{e} ({model})"
                continue

        return f"Apologies, Sir. Visual analysis could not be completed ({last_error}). Please try again."

    # =====================================================================
    # 4. HIGH-LEVEL PERCEPTION AGENTS
    # =====================================================================

    def inspect_screen(self, user_query: str = "") -> Tuple[bool, str, Optional[bytes]]:
        """
        Captures the screen and executes multimodal analysis.
        Returns (success_bool, analysis_text, raw_jpeg_bytes).
        """
        img_bytes = self.capture_screen()
        if not img_bytes:
            return False, "Sir, I was unable to capture the desktop screen.", None

        prompt = user_query.strip() if user_query else "Describe and analyze what is currently visible on my screen in detail."
        system_inst = (
            f"You are Jarvis, {config.USER_NAME}'s executive AI assistant. "
            "You have eyes on their computer screen. Analyze the visual layout, open applications, code, terminal outputs, "
            "errors, charts, or documents accurately and concisely. "
            "Address {config.USER_NAME} politely as Sir. Avoid raw multi-asterisk markers in running prose."
        )

        analysis = self.analyze_image(img_bytes, prompt, system_instruction=system_inst)
        return True, analysis, img_bytes

    def inspect_webcam(self, user_query: str = "") -> Tuple[bool, str, Optional[bytes]]:
        """
        Captures a frame from the laptop webcam and executes multimodal analysis.
        Returns (success_bool, analysis_text, raw_jpeg_bytes).
        """
        img_bytes = self.capture_webcam()
        if not img_bytes:
            return False, "Sir, I am unable to access the camera hardware. Please ensure your webcam is connected and camera privacy access is enabled in Windows Settings.", None

        prompt = user_query.strip() if user_query else "Describe what you see in front of the camera, including any objects, people, documents, or surroundings."
        system_inst = (
            f"You are Jarvis, {config.USER_NAME}'s executive AI assistant. "
            "You are looking through their laptop webcam. Carefully describe any objects held in hand, documents, "
            "facial expressions, or environment clearly and naturally. "
            "Address {config.USER_NAME} politely as Sir."
        )

        analysis = self.analyze_image(img_bytes, prompt, system_instruction=system_inst)
        return True, analysis, img_bytes

    def verify_presence(self) -> Tuple[bool, str]:
        """
        Quick webcam snapshot to check if the user is present in front of the workstation.
        """
        img_bytes = self.capture_webcam()
        if not img_bytes:
            return False, "Camera is offline or inaccessible."

        prompt = (
            "Look at this camera frame. Is a person currently seated or present in front of the desk/laptop? "
            "Answer with either 'PRESENT: [brief description]' or 'ABSENT: [brief description]'."
        )
        res = self.analyze_image(img_bytes, prompt)
        is_present = "PRESENT" in res.upper()
        return is_present, res
