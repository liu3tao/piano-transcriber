"""
transcriber.py -- Audio-to-MIDI transcription using Spotify's basic-pitch.

Wraps basic_pitch.inference.predict with configurable thresholds and returns
a PrettyMIDI object along with structured note events.
"""

import os
import tempfile
import warnings
from pathlib import Path
from typing import List, NamedTuple, Tuple

# Suppress noisy TensorFlow / TensorRT warnings before TF is imported.
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

# Suppress the pkg_resources deprecation warning from resampy.
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

import pretty_midi  # noqa: E402
from basic_pitch.inference import predict  # noqa: E402

# Formats that soundfile/libsndfile can decode natively (no ffmpeg fallback).
_NATIVE_EXTENSIONS = {".wav", ".flac", ".ogg"}

# Additional formats we accept -- these get converted to wav first via pydub.
_CONVERT_EXTENSIONS = {".mp3", ".webm"}

SUPPORTED_EXTENSIONS = _NATIVE_EXTENSIONS | _CONVERT_EXTENSIONS


class NoteEvent(NamedTuple):
    """A single detected note."""
    start_time: float   # seconds
    end_time: float     # seconds
    midi_pitch: int     # MIDI note number (0-127)
    velocity: int       # MIDI velocity (0-127)


def validate_audio_path(audio_path: str) -> Path:
    """Validate that the audio file exists and has a supported extension."""
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported audio format '{path.suffix}'. "
            f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return path


def _convert_to_wav(audio_path: Path) -> tuple[str, str]:
    """Convert a non-native audio file to a temporary .wav file.

    Uses pydub (which delegates to ffmpeg) for the conversion.

    Args:
        audio_path: Path to the source audio file.

    Returns:
        A tuple of (path_to_temp_wav, path_to_temp_wav) -- the second
        value is the same path, returned so the caller can clean it up.
    """
    from pydub import AudioSegment

    fmt = audio_path.suffix.lstrip(".").lower()
    audio = AudioSegment.from_file(str(audio_path), format=fmt)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    os.close(tmp_fd)
    audio.export(tmp_path, format="wav")
    return tmp_path, tmp_path


def transcribe(
    audio_path: str,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    min_note_len_ms: float = 58,
) -> Tuple[pretty_midi.PrettyMIDI, List[NoteEvent]]:
    """Transcribe an audio file to MIDI using basic-pitch.

    Args:
        audio_path: Path to the input audio file (.wav, .mp3, .ogg, .flac).
        onset_threshold: Confidence threshold for note onsets (0-1).
            Higher values mean fewer but more confident note starts.
        frame_threshold: Confidence threshold for note frames (0-1).
            Higher values mean shorter, more confident notes.
        min_note_len_ms: Minimum note duration in milliseconds.
            Notes shorter than this are discarded. Default 58ms (~a 64th note).

    Returns:
        A tuple of (PrettyMIDI object, list of NoteEvent).
    """
    path = validate_audio_path(audio_path)

    # If the format needs conversion (e.g. .webm, .mp3), convert to a
    # temporary .wav first so that soundfile can read it directly and we
    # avoid the deprecated audioread fallback in librosa.
    tmp_wav = None
    try:
        predict_path = str(path)
        if path.suffix.lower() in _CONVERT_EXTENSIONS:
            predict_path, tmp_wav = _convert_to_wav(path)

        model_output, midi_data, _raw_note_events = predict(
            predict_path,
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            minimum_note_length=min_note_len_ms,
        )
    finally:
        # Clean up the temporary wav file if we created one.
        if tmp_wav is not None:
            try:
                os.unlink(tmp_wav)
            except OSError:
                pass

    # Extract note events from the PrettyMIDI object (stable API)
    # rather than parsing basic-pitch's internal raw format.
    note_events: List[NoteEvent] = []
    for instrument in midi_data.instruments:
        for note in instrument.notes:
            note_events.append(
                NoteEvent(
                    start_time=round(note.start, 4),
                    end_time=round(note.end, 4),
                    midi_pitch=note.pitch,
                    velocity=note.velocity,
                )
            )
    note_events.sort(key=lambda n: (n.start_time, n.midi_pitch))

    return midi_data, note_events


def save_midi(midi_data: pretty_midi.PrettyMIDI, output_path: str) -> Path:
    """Write a PrettyMIDI object to a .mid file.

    Args:
        midi_data: The PrettyMIDI object from transcription.
        output_path: Destination file path.

    Returns:
        The resolved output Path.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    midi_data.write(str(out))
    return out
