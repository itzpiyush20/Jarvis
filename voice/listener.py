import io
import os
import sys
import time
import wave
import queue
import logging
import threading
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
from voice.tts import generate_speech_file
from voice.chimes import play_wake_chime, play_thinking_chime, play_audio_file

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("JarvisVoiceListener")

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
        Records the user's spoken voice command after wake-word activation
        using adaptive energy silence detection. Returns WAV audio bytes.
        """
        logger.info("🎙️ [LISTENING] Jarvis is listening for your command...")
        recorded_frames = []
        silence_threshold = 300.0  # RMS threshold for speech activity in int16
        speech_started = False
        silent_chunks = 0
        max_silent_chunks = int(1.4 / 0.08)  # ~1.4 seconds of silence to conclude speech
        timeout_chunks = int(4.5 / 0.08)    # 4.5 seconds timeout if user doesn't start speaking
        max_duration_chunks = int(18.0 / 0.08) # 18s maximum command limit
        total_chunks = 0

        # Drain any residual audio in queue before recording
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

        while self.running and total_chunks < max_duration_chunks:
            try:
                chunk = self.audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            total_chunks += 1
            recorded_frames.append(chunk)

            # Compute RMS audio energy
            rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))

            if rms > silence_threshold:
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
                        logger.info("⏱️ [TIMEOUT] No speech detected after wake word.")
                        return None

        if not speech_started or len(recorded_frames) < 5:
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
            return

        print(f"\n" + "—" * 60)
        print(f" 🗣️ You: {clean_query}")
        print("—" * 60)

        # 2. Gather context and query brain
        logger.info("⚡ [THINKING] Processing query with Jarvis Brain...")
        context = self._gather_context(clean_query)
        reply = self.brain.ask(clean_query, context=context)

        print(f" 🤖 Jarvis: {reply}")
        print("—" * 60 + "\n")

        # 3. Synthesize speech
        logger.info("🎙️ [SYNTHESIZING] Synthesizing neural speech reply...")
        try:
            import asyncio
            filename = f"desktop_reply_{int(time.time())}.mp3"
            audio_path = asyncio.run(generate_speech_file(reply, filename=filename))
            
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


if __name__ == "__main__":
    start_voice_service()
