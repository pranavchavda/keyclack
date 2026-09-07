"""Sample-pack loading + a low-latency mixing audio engine.

The engine is a single PortAudio output stream with a callback that mixes any
number of overlapping voices, so fast typing layers naturally (like a real
keyboard's polyphony) instead of cutting the previous click short.
"""

from __future__ import annotations

import json
import os
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf


# --------------------------------------------------------------------------
# Sample pack
# --------------------------------------------------------------------------

class Pack:
    """A directory of recorded switch sounds described by manifest.json."""

    def __init__(self, directory: str, target_rate: int = 48000):
        self.directory = os.path.abspath(directory)
        self.target_rate = target_rate
        self.name = os.path.basename(self.directory.rstrip("/"))
        self.manifest: dict = {}
        self.samples: dict[str, np.ndarray] = {}  # role -> mono float32 @rate
        self._load()

    def _load(self) -> None:
        man_path = os.path.join(self.directory, "manifest.json")
        if not os.path.isdir(self.directory):
            raise FileNotFoundError(f"Pack directory not found: {self.directory}")
        with open(man_path, encoding="utf-8") as fh:
            self.manifest = json.load(fh)
        for role, fname in self.manifest.items():
            if role in ("id", "caption"):
                continue
            if not isinstance(fname, str) or not fname:
                continue
            path = os.path.join(self.directory, fname)
            if not os.path.isfile(path):
                continue
            data, rate = sf.read(path, dtype="float32", always_2d=True)
            # mono
            data = data.mean(axis=1)
            if rate != self.target_rate:
                data = self._resample(data, rate, self.target_rate)
            if data.size:
                self.samples[role] = data.astype(np.float32, copy=False)

    @staticmethod
    def _resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
        n_out = int(round(x.size * sr_out / sr_in))
        idx = np.arange(n_out) * (sr_in / sr_out)
        src = np.arange(x.size)
        return np.interp(idx, src, x).astype(np.float32)

    @property
    def caption(self) -> str:
        return self.manifest.get("caption", self.name)

    def contains(self, role: str) -> bool:
        return role in self.samples


# --------------------------------------------------------------------------
# Mixing engine
# --------------------------------------------------------------------------

class Mixer:
    """Thread-safe polyphonic voice pool consumed by the audio callback."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pending: list[np.ndarray] = []
        self._voices: list[list] = []  # [array, position]

    def play(self, data: np.ndarray) -> None:
        if data is None or data.size == 0:
            return
        with self._lock:
            self._pending.append(data)

    def _render(self, frames: int, out: np.ndarray) -> float:
        """Mix `frames` samples into `out` (flat 1-D float32). Returns peak."""
        with self._lock:
            if self._pending:
                self._voices.extend([[d, 0] for d in self._pending])
                self._pending.clear()
            voices = self._voices
            alive = []
            peak = 0.0
            for voice in voices:
                data, pos = voice
                take = data[pos : pos + frames]
                if take.size:
                    out[: take.size] += take
                    v = float(np.abs(take).max())
                    if v > peak:
                        peak = v
                    pos += take.size
                if pos < data.size:
                    alive.append([data, pos])
            self._voices = alive
        return peak


class AudioEngine:
    """Single output stream mixing key voices at low latency."""

    def __init__(self, device: str = "default", sample_rate: int = 48000,
                 volume: float = 0.9, blocksize: int = 128,
                 channels: int = 1):
        self.device = device if device and device != "default" else None
        self.sample_rate = sample_rate
        self.volume = float(np.clip(volume, 0.0, 1.0))
        self.blocksize = blocksize
        self.channels = channels
        self.mixer = Mixer()
        self._stream = None
        self.peak_log = 0.0
        self._lock = threading.Lock()

    # -- helpers ----------------------------------------------------------
    def play_role(self, pack: Pack, role: str) -> None:
        data = pack.samples.get(role)
        if data is None or data.size == 0:
            return
        with self._lock:
            vol = self.volume
        if vol <= 0:
            return
        self.mixer.play(data * vol)

    # -- lifecycle --------------------------------------------------------
    def start(self) -> None:
        if self._stream is not None:
            return

        def callback(outdata, frames, time_info, status):
            out = np.zeros(frames, dtype=np.float32)
            peak = self.mixer._render(frames, out)
            if peak > self.peak_log:
                self.peak_log = peak
            if self.channels == 1:
                outdata[:, 0] = out
            else:
                outdata[:, 0] = out
                outdata[:, 1] = out

        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
            channels=self.channels,
            dtype="float32",
            device=self.device,
            callback=callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    def peak_since(self, reset: bool = True) -> float:
        with self._lock:
            p = self.peak_log
            if reset:
                self.peak_log = 0.0
        return p

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        return False


def list_audio_devices() -> list[str]:
    try:
        return [d["name"] for d in sd.query_devices()
                if d["max_output_channels"] > 0]
    except Exception:
        return []
