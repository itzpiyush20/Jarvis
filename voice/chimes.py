import numpy as np
import time
from pathlib import Path

try:
    import sounddevice as sd
except (ImportError, OSError):
    sd = None

try:
    import soundfile as sf
except (ImportError, OSError):
    sf = None

def _synthesize_sine_chime(tones: list[tuple[float, float]], sample_rate: int = 16000, volume: float = 0.25) -> np.ndarray:
    """
    Synthesizes smooth procedural chime waveforms with exponential decay envelopes.
    tones: list of (frequency_hz, duration_sec)
    """
    audio_segments = []
    for freq, duration in tones:
        n_samples = int(sample_rate * duration)
        t = np.linspace(0, duration, n_samples, endpoint=False)
        # Gentle attack and exponential decay to prevent clicks
        decay = np.exp(-7.0 * t / duration)
        attack_len = min(int(sample_rate * 0.01), n_samples)
        envelope = decay.copy()
        if attack_len > 0:
            envelope[:attack_len] *= np.linspace(0, 1, attack_len)
        waveform = volume * np.sin(2 * np.pi * freq * t) * envelope
        audio_segments.append(waveform)
    
    return np.concatenate(audio_segments).astype(np.float32)

def play_chime(tones: list[tuple[float, float]], volume: float = 0.22, blocking: bool = True):
    """Plays procedural chime tones through the default speaker."""
    if sd is None:
        return
    try:
        audio = _synthesize_sine_chime(tones, sample_rate=16000, volume=volume)
        sd.play(audio, samplerate=16000)
        if blocking:
            sd.wait()
    except Exception:
        # Audio playback should never crash the main loop
        pass

def is_quiet_hours() -> bool:
    """Detects whether current local IST time is during late night quiet hours (11 PM - 6 AM)."""
    import datetime
    try:
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now = datetime.datetime.now(ist_tz)
        return now.hour >= 23 or now.hour < 6
    except Exception:
        return False

def play_wake_chime():
    """Plays an alert chime when 'Jarvis' wake-word is detected (Ascending C5 -> G5). Softened at late night."""
    vol = 0.09 if is_quiet_hours() else 0.25
    play_chime([(523.25, 0.06), (783.99, 0.10)], volume=vol, blocking=False)

def play_thinking_chime():
    """Plays a soft acknowledging blip when command recording finishes (E5). Softened at late night."""
    vol = 0.07 if is_quiet_hours() else 0.18
    play_chime([(659.25, 0.09)], volume=vol, blocking=True)

def play_audio_file(file_path: str | Path, blocking: bool = True):
    """Plays an audio file (.mp3, .wav) through laptop speakers using sounddevice and soundfile."""
    if sd is None or sf is None:
        return
    try:
        data, fs = sf.read(str(file_path))
        sd.play(data, fs)
        if blocking:
            sd.wait()
    except Exception as e:
        print(f"[-] Failed to play audio file {file_path}: {e}")
