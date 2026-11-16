import io
import os
import sys
import time
import wave
import queue
import logging
import threading
import socket
from pathlib import Path
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import sounddevice as sd
except (ImportError, OSError):
    sd = None

try:
    from openwakeword.model import Model
except (ImportError, OSError):
    Model = None

import config
from core.brain import JarvisBrain
from core.memory import MemoryManager
from integrations.google_services import GoogleServices
from voice.tts import generate_speech_file, speak_to_file
from voice.chimes import play_wake_chime, play_thinking_chime, play_audio_file
from voice.ui_notify import notify_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("JarvisVoiceListener")

_INSTANCE_LOCK_SOCKET = None

def acquire_instance_lock(port: int = 47281) -> bool:
    """Ensures only a single instance of the Jarvis voice listener runs at a time."""
    global _INSTANCE_LOCK_SOCKET
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", port))
        _INSTANCE_LOCK_SOCKET = s
        return True
    except (socket.error, OSError):
        return False

class DesktopVoiceAssistant:
    """
    Hands-free, low-latency, autonomous desktop voice listener for Jarvis.
    Continuously listens for 'Jarvis' / 'Hey Jarvis' wake word on the laptop's
    microphone, records the user's spoken command, reasons with Gemini Brain,
    and replies aloud through the laptop's speakers.
    """

    def __init__(
        self,
        wake_model_name: str = config.WAKE_WORD_MODEL,
        threshold: float = config.WAKE_WORD_THRESHOLD,
        device_index: int | None = config.MIC_DEVICE_INDEX,
    ):
        if sd is None:
            raise RuntimeError("sounddevice (PortAudio) is not installed or available on this system.")
        if Model is None:
            raise RuntimeError("openwakeword is not installed or available on this system.")

        self.wake_model_name = wake_model_name
        self.threshold = threshold
        self.device_index = device_index
        self.sample_rate = 16000
        self.chunk_size = 1280  # 80ms chunk for openwakeword at 16kHz
        self.running = False
        self.audio_queue = queue.Queue()

        self.brain = JarvisBrain()
        self.memory = MemoryManager()
        self.google = GoogleServices()

        logger.info(f"[*] Initializing openWakeWord ONNX engine ('{self.wake_model_name}')...")
        self.oww_model = Model(
            wakeword_models=[self.wake_model_name],
            inference_framework="onnx"
        )
        logger.info("[+] openWakeWord ONNX engine loaded successfully.")

    def _audio_callback(self, indata, frames, time_info, status):
        """Streaming callback from sounddevice capturing 16-bit PCM chunks."""
        if status:
            logger.debug(f"Audio stream status: {status}")
        self.audio_queue.put(indata.copy())

    def _gather_context(self, query: str) -> str:
        """Retrieves relevant Calendar, Gmail, or Task context based on query keywords."""
        lower = query.lower()
        ctx = ""
        if any(k in lower for k in ["schedule", "calendar", "meeting", "events", "agenda"]):
            if self.google.is_configured():
                agenda = self.google.format_daily_agenda()
                ctx += f"\nCurrent Calendar Agenda:\n{agenda}\n"
        if any(k in lower for k in ["email", "gmail", "inbox", "mail"]):
            if self.google.is_configured():
                unreads = self.google.get_unread_emails(max_results=3)
                ctx += f"\nRecent Unread Emails: {unreads}\n"
        if any(k in lower for k in ["task", "todo", "reminder", "notes"]):
            pending = self.memory.get_pending_tasks()
            ctx += f"\nPending Tasks in Database: {pending}\n"
        return ctx

    def _record_command(self, stream: sd.InputStream) -> bytes | None:
        """
        Records the user's spoken voice command after wake-word activation.
        Uses adaptive dynamic ambient baseline calibration to catch soft and normal speech.
        """
        logger.info("🎙️ [LISTENING] Jarvis is listening for your command...")
        notify_user("🎙️ Jarvis", "Listening for your command, Sir...")

        recorded_frames = []
        # Pre-populate with recent chunks in queue so no words right after wake-word are lost
        while not self.audio_queue.empty():
            try:
                recorded_frames.append(self.audio_queue.get_nowait())
            except queue.Empty:
                break

        # Compute dynamic ambient noise floor from the first available frames
        sample_energies = [np.sqrt(np.mean(f.astype(np.float32) ** 2)) for f in recorded_frames if len(f) > 0]
        ambient_baseline = np.mean(sample_energies) if sample_energies else 15.0
        # Dynamic voice threshold: baseline * 1.3 or minimum 25.0
        voice_threshold = max(ambient_baseline * 1.3, 25.0)

        logger.debug(f"Ambient baseline RMS: {ambient_baseline:.1f}, Voice threshold: {voice_threshold:.1f}")

        speech_started = False
        silent_chunks = 0
        max_silent_chunks = int(1.3 / 0.08)  # ~1.3s silence after speech concludes command
        timeout_chunks = int(5.0 / 0.08)     # 5.0s window for speech to begin
        max_duration_chunks = int(14.0 / 0.08) # 14s maximum command limit
        total_chunks = len(recorded_frames)

        while self.running and total_chunks < max_duration_chunks:
            try:
                chunk = self.audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            total_chunks += 1
            recorded_frames.append(chunk)

            rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))

            if rms > voice_threshold:
                if not speech_started:
                    logger.info("🗣️ [SPEECH DETECTED] User speaking...")
                    speech_started = True
                silent_chunks = 0
            else:
                if speech_started:
                    silent_chunks += 1
                    if silent_chunks >= max_silent_chunks:
                        logger.info("🔇 [SPEECH ENDED] Silence detected. Concluding recording.")
                        break
                else:
                    if total_chunks >= timeout_chunks:
                        logger.info("⏱️ [TIMEOUT] Concluding audio capture.")
                        break

        if len(recorded_frames) < 8:
            return None

        # Concatenate PCM audio and wrap in WAV format
        full_audio = np.concatenate(recorded_frames, axis=0)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(full_audio.tobytes())

        return wav_buffer.getvalue()

    def process_voice_interaction(self, wav_bytes: bytes):
        """Transcribes audio, queries Gemini brain, synthesizes speech, and plays response."""
        play_thinking_chime()

        # 1. Transcribe audio using Gemini
        logger.info("🧠 [TRANSCRIBING] Transcribing speech via Gemini Native Audio...")
        transcription = self.brain.transcribe_audio(wav_bytes, mime_type="audio/wav")
        clean_query = transcription.strip().strip('"\'')

        if not clean_query or len(clean_query) < 2:
            logger.warning("[-] Could not discern clear speech from recording.")
            notify_user("Jarvis", "No clear speech detected.")
            return

        print(f"\n" + "—" * 60)
        print(f" 🗣️ You: {clean_query}")
        print("—" * 60)
        notify_user("🗣️ You", clean_query)

        # 2. Gather context and query brain
        logger.info("⚡ [THINKING] Processing query with Jarvis Brain...")
        context = self._gather_context(clean_query)
        reply = self.brain.ask(clean_query, context=context)

        print(f" 🤖 Jarvis: {reply}")
        print("—" * 60 + "\n")
        notify_user(f"🤖 {config.ASSISTANT_NAME}", reply[:160])

        # 3. Synthesize speech
        logger.info("🎙️ [SYNTHESIZING] Synthesizing neural speech reply...")
        try:
            filename = f"desktop_reply_{int(time.time())}.mp3"
            audio_path = speak_to_file(reply, filename=filename)
            
            # 4. Play speech through laptop speakers
            logger.info(f"🔊 [SPEAKING] Playing response through speakers...")
            play_audio_file(audio_path, blocking=True)
            logger.info("[✓] Finished speaking.")
        except Exception as e:
            logger.error(f"[-] Speech playback error: {e}", exc_info=True)

    def listen_loop(self):
        """Continuous wake-word listening loop."""
        if sd is None or self.oww_model is None:
            logger.warning("[-] Audio hardware or wake-word model not available. Exiting listen loop.")
            return

        self.running = True
        logger.info("=" * 60)
        logger.info(f" 🎙️ Jarvis Desktop Voice Service ACTIVE")
        logger.info(f" • Wake Word : Say 'Jarvis' or 'Hey Jarvis'")
        logger.info(f" • Sensitivity Threshold : {self.threshold}")
        logger.info(f" • Device : Default System Microphone")
        logger.info("=" * 60)

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self.chunk_size,
                device=self.device_index,
                callback=self._audio_callback,
            ) as stream:
                logger.info("🟢 [READY] Listening in background for 'Jarvis'...")
                notify_user("🟢 Jarvis Online", "Listening for 'Jarvis' or 'Hey Jarvis'")

                while self.running:
                    try:
                        chunk = self.audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue

                    # Flatten 2D chunk to 1D array for openwakeword
                    audio_frame = chunk.flatten()
                    prediction = self.oww_model.predict(audio_frame)
                    score = prediction.get(self.wake_model_name, 0.0)

                    if score >= self.threshold:
                        logger.info(f"\n🔔 [WAKE WORD DETECTED] 'Jarvis' detected! (Confidence: {score:.2f})")
                        notify_user("🔔 Jarvis Awake", f"Wake-word detected! Listening...")
                        
                        # Play wake chime
                        play_wake_chime()

                        # Record command
                        wav_data = self._record_command(stream)
                        if wav_data:
                            self.process_voice_interaction(wav_data)
                        
                        # Reset model internal buffers after interaction
                        self.oww_model.reset()
                        time.sleep(0.3)  # Brief acoustic settle
                        logger.info("🟢 [READY] Resuming wake-word listening for 'Jarvis'...")

        except Exception as e:
            logger.error(f"[-] Audio input stream error: {e}", exc_info=True)
        finally:
            self.running = False
            logger.info("[*] Jarvis Desktop Voice Service terminated.")

    def stop(self):
        """Stops the listening loop."""
        self.running = False


def start_voice_service():
    """Convenience launcher for the standalone desktop voice assistant."""
    if not acquire_instance_lock():
        print("[*] Jarvis Voice Assistant is already active and listening in the background.")
        return

    pid_file = config.AUDIO_DIR / "jarvis.pid"
    try:
        pid_file.write_text(str(os.getpid()))
    except Exception:
        pass

    try:
        assistant = DesktopVoiceAssistant()
        assistant.listen_loop()
    except KeyboardInterrupt:
        print("\n[*] Stopping Jarvis Voice Service. Goodbye, Sir.")
        try:
            assistant.stop()
        except Exception:
            pass
    except Exception as e:
        print(f"\n[!] Could not start desktop voice service: {e}")
    finally:
        try:
            pid_file.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    start_voice_service()
