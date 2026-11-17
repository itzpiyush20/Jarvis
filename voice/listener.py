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
from voice.hud import show_hud_listening, show_hud_thinking, show_hud_speaking, hide_hud

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("JarvisVoiceListener")

_INSTANCE_LOCK_HANDLE = None

def acquire_instance_lock(mutex_name: str = "Global\\JarvisVoiceListenerMutex") -> bool:
    """
    Ensures only a single instance of the Jarvis voice listener runs at a time.
    Uses Win32 Named Mutex on Windows for robust system-wide locking that survives
    reserved network port ranges, with a TCP socket fallback for other platforms.
    """
    global _INSTANCE_LOCK_HANDLE
    if sys.platform == "win32":
        try:
            import win32event, win32api, winerror
            mutex = win32event.CreateMutex(None, False, mutex_name)
            if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
                return False
            _INSTANCE_LOCK_HANDLE = mutex
            return True
        except Exception:
            pass

    # Cross-platform fallback: Port binding
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 47282))
        _INSTANCE_LOCK_HANDLE = s
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

        # Software mic gain — amplifies quiet laptop mics before processing
        self.mic_gain = 1.0  # Will be calibrated in _calibrate_mic_gain()

        self.brain = JarvisBrain()
        self.memory = MemoryManager()
        self.google = GoogleServices()

        logger.info(f"[*] Initializing openWakeWord ONNX engine ('{self.wake_model_name}')...")
        self.oww_model = Model(
            wakeword_models=[self.wake_model_name],
            inference_framework="onnx"
        )
        logger.info("[+] openWakeWord ONNX engine loaded successfully.")

        # Pre-cache instant wake-word acknowledgment audio for zero-latency response
        self.ack_audio_path = config.AUDIO_DIR / "jarvis_ack.mp3"
        self._ensure_ack_audio()

    def _calibrate_mic_gain(self):
        """
        Auto-calibrates software gain by sampling ~1 second of ambient room audio.
        Targets a comfortable RMS of ~300 for the wake-word model.
        If MIC_GAIN is set to a number in config, uses that instead.
        """
        if isinstance(config.MIC_GAIN, (int, float)):
            self.mic_gain = float(config.MIC_GAIN)
            logger.info(f"[*] Using fixed MIC_GAIN from config: {self.mic_gain:.1f}x")
            return

        logger.info("[*] Auto-calibrating microphone gain (stay quiet for 1 second)...")
        calibration_frames = []
        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self.chunk_size,
                device=self.device_index,
            ) as cal_stream:
                for _ in range(int(1.0 / (self.chunk_size / self.sample_rate))):  # ~1 second
                    data = cal_stream.read(self.chunk_size)[0]
                    calibration_frames.append(data.flatten().astype(np.float32))

            if calibration_frames:
                all_audio = np.concatenate(calibration_frames)
                ambient_rms = np.sqrt(np.mean(all_audio ** 2))
                peak = np.max(np.abs(all_audio))

                logger.info(f"    Ambient RMS: {ambient_rms:.1f}, Peak: {peak:.0f}")

                if ambient_rms < 5.0:
                    # Very quiet mic — needs significant boost
                    # Target: amplify so that normal speech (~50x ambient) reaches RMS ~500
                    self.mic_gain = min(20.0, max(5.0, 300.0 / max(ambient_rms * 30, 1.0)))
                elif ambient_rms < 50.0:
                    # Somewhat quiet
                    self.mic_gain = min(10.0, max(2.0, 300.0 / max(ambient_rms * 10, 1.0)))
                else:
                    # Mic is already loud enough
                    self.mic_gain = 1.0

                logger.info(f"[+] Auto-calibrated MIC_GAIN: {self.mic_gain:.1f}x")
            else:
                self.mic_gain = 10.0
                logger.warning("[!] No calibration data captured. Using default gain: 10x")
        except Exception as e:
            self.mic_gain = 10.0
            logger.warning(f"[!] Mic calibration failed ({e}). Using default gain: 10x")

    def _amplify(self, audio_int16: np.ndarray) -> np.ndarray:
        """Applies software gain to int16 audio, clipping to prevent overflow."""
        if self.mic_gain == 1.0:
            return audio_int16
        amplified = audio_int16.astype(np.float32) * self.mic_gain
        return np.clip(amplified, -32768, 32767).astype(np.int16)

    def _ensure_ack_audio(self):
        """Pre-synthesizes the instant verbal acknowledgment to avoid runtime TTS delay in the background."""
        if self.ack_audio_path.exists() and self.ack_audio_path.stat().st_size > 500:
            return

        def _bg_generate():
            try:
                speak_to_file("At your service, Sir. How may I assist you?", filename="jarvis_ack.mp3")
            except Exception:
                pass

        threading.Thread(target=_bg_generate, daemon=True, name="AckAudioGen").start()

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
        if any(k in lower for k in ["battery", "power", "charging", "laptop", "hardware", "system status", "specs", "ram", "cpu", "storage", "disk"]):
            telemetry = self.brain.system_commander.get_system_telemetry()
            ctx += f"\nLive Workstation Telemetry:\n{telemetry}\n"
        if any(k in lower for k in ["clipboard", "copied"]):
            clip = self.brain.system_commander.get_clipboard_text()
            if clip:
                ctx += f"\nWorkstation Clipboard Content:\n\"\"\"\n{clip[:2000]}\n\"\"\"\n"
        return ctx

    def _record_command(self, stream: sd.InputStream) -> bytes | None:
        """
        Records the user's spoken voice command after wake-word activation.
        Uses adaptive dynamic ambient baseline calibration to catch soft and normal speech.
        """
        logger.info("🎙️ [LISTENING] Jarvis is listening for your command...")
        notify_user("🎙️ Jarvis", "Listening for your command, Sir...")
        show_hud_listening("Listening for your command...")

        recorded_frames = []
        # Pre-populate with recent chunks in queue so no words right after wake-word are lost
        while not self.audio_queue.empty():
            try:
                recorded_frames.append(self.audio_queue.get_nowait())
            except queue.Empty:
                break

        # Compute dynamic ambient noise floor from the first available frames
        sample_energies = [np.sqrt(np.mean(f.astype(np.float32) ** 2)) for f in recorded_frames if len(f) > 0]
        ambient_baseline = np.mean(sample_energies) if sample_energies else 2.0
        # Dynamic voice threshold: baseline * 1.15 or minimum 3.0 for responsive soft-speech pickup
        voice_threshold = max(ambient_baseline * 1.15, 3.0)

        logger.debug(f"Ambient baseline RMS: {ambient_baseline:.1f}, Voice threshold: {voice_threshold:.1f}")

        speech_started = False
        silent_chunks = 0
        max_silent_chunks = int(0.55 / 0.08)  # ~550ms silence after speech concludes command (fast cutoff)
        timeout_chunks = int(2.5 / 0.08)     # 2.5s window for speech to begin
        max_duration_chunks = int(8.0 / 0.08) # 8s maximum command limit
        total_chunks = len(recorded_frames)

        while self.running and total_chunks < max_duration_chunks:
            try:
                chunk = self.audio_queue.get(timeout=0.15)
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

        if len(recorded_frames) < 6:
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
        show_hud_thinking("Transcribing speech...")

        # 1. Transcribe audio using Gemini Native Audio
        logger.info("🧠 [TRANSCRIBING] Transcribing speech via Gemini Native Audio...")
        transcription = self.brain.transcribe_audio(wav_bytes, mime_type="audio/wav")
        clean_query = transcription.strip().strip('"\'') if transcription else ""

        # If user just called "Jarvis" and paused, answer immediately with instant acknowledgment
        if not clean_query or len(clean_query) < 2:
            logger.info("[*] Wake word acknowledged without further command. Responding with verbal greeting.")
            show_hud_speaking("At your service, Sir.")
            if self.ack_audio_path.exists():
                play_audio_file(self.ack_audio_path, blocking=True)
            else:
                try:
                    audio_path = speak_to_file("At your service, Sir. How may I assist you?", filename="jarvis_ack.mp3")
                    play_audio_file(audio_path, blocking=True)
                except Exception as e:
                    logger.error(f"[-] Acknowledgment playback error: {e}")
            hide_hud()
            return

        print(f"\n" + "—" * 60)
        print(f" 🗣️ You: {clean_query}")
        print("—" * 60)
        notify_user("🗣️ You", clean_query)
        show_hud_thinking(clean_query)

        # 2. Gather context and query brain (Common Sense Voice Channel)
        logger.info("⚡ [THINKING] Processing query with Jarvis Brain (Voice Mode)...")
        context = self._gather_context(clean_query)
        reply = self.brain.ask(clean_query, context=context, channel="voice")

        print(f" 🤖 Jarvis: {reply}")
        print("—" * 60 + "\n")
        notify_user(f"🤖 {config.ASSISTANT_NAME}", reply[:160])
        show_hud_speaking(reply)

        # 3. Synthesize speech
        logger.info("🎙️ [SYNTHESIZING] Synthesizing neural speech reply...")
        try:
            filename = f"desktop_reply_{int(time.time())}.mp3"
            audio_path = speak_to_file(reply, filename=filename)
            
            # 4. Play speech through laptop speakers
            if audio_path.exists() and audio_path.stat().st_size > 500:
                logger.info(f"🔊 [SPEAKING] Playing response through speakers...")
                play_audio_file(audio_path, blocking=True)
            logger.info("[✓] Finished speaking.")
        except Exception as e:
            logger.error(f"[-] Speech playback error: {e}", exc_info=True)
        finally:
            hide_hud()

    def listen_loop(self):
        """Continuous wake-word listening loop with automatic crash recovery and device reconnect."""
        if sd is None or self.oww_model is None:
            logger.warning("[-] Audio hardware or wake-word model not available. Exiting listen loop.")
            return

        self.running = True
        self._calibrate_mic_gain()
        logger.info("=" * 60)
        logger.info(f" 🎙️ Jarvis Desktop Voice Service ACTIVE")
        logger.info(f" • Wake Word : Say 'Jarvis' or 'Hey Jarvis'")
        logger.info(f" • Sensitivity Threshold : {self.threshold}")
        logger.info(f" • Software Mic Gain     : {self.mic_gain:.1f}x")
        logger.info(f" • Device : Default System Microphone")
        logger.info("=" * 60)

        while self.running:
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

                    # Drain any stale audio from before the stream was ready
                    while not self.audio_queue.empty():
                        try:
                            self.audio_queue.get_nowait()
                        except queue.Empty:
                            break

                    consecutive_hits = 0

                    while self.running:
                        try:
                            chunk = self.audio_queue.get(timeout=0.5)
                        except queue.Empty:
                            continue

                        # Flatten 2D chunk to 1D array and amplify for openwakeword
                        audio_frame = self._amplify(chunk.flatten())
                        prediction = self.oww_model.predict(audio_frame)
                        score = prediction.get(self.wake_model_name, 0.0)

                        # Use a rolling hit counter: a single frame above
                        # threshold triggers immediately, but even very low
                        # scores that accumulate over consecutive frames
                        # (indicating the user is speaking) also trigger.
                        if score >= self.threshold:
                            consecutive_hits += 1
                        elif score >= self.threshold * 0.4:
                            # Partial confidence — keep the streak alive
                            consecutive_hits = max(consecutive_hits, 1)
                        else:
                            consecutive_hits = 0

                        if consecutive_hits >= 1 and score >= self.threshold:
                            logger.info(f"\n🔔 [WAKE WORD DETECTED] 'Jarvis' detected! (Confidence: {score:.2f})")
                            notify_user("🔔 Jarvis Awake", f"Wake-word detected! Listening...")
                            consecutive_hits = 0
                            
                            # Play wake chime non-blocking so recording starts instantly without delay
                            play_wake_chime()

                            # Record command
                            wav_data = self._record_command(stream)
                            if wav_data:
                                self.process_voice_interaction(wav_data)
                            
                            # Reset model internal buffers after interaction
                            self.oww_model.reset()
                            # Drain audio queue to avoid echo/residual triggering
                            while not self.audio_queue.empty():
                                try:
                                    self.audio_queue.get_nowait()
                                except queue.Empty:
                                    break
                            time.sleep(0.1)  # Brief acoustic settle
                            logger.info("🟢 [READY] Resuming wake-word listening for 'Jarvis'...")

            except Exception as e:
                if not self.running:
                    break
                logger.error(f"[-] Audio input stream error (auto-reconnecting in 2s): {e}")
                time.sleep(2)

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
