"""
abc_converter.py -- MIDI-to-ABC notation conversion using music21.

Provides a pluggable QuantizationStrategy so that quantization can be
guided by a reference music sheet in the future.
"""

from abc import ABC, abstractmethod
from pathlib import Path

import music21


# ---------------------------------------------------------------------------
# Quantization strategy abstraction
# ---------------------------------------------------------------------------

class QuantizationStrategy(ABC):
    """Base class for quantization strategies.

    Quantization snaps raw note timings (in seconds) to the nearest
    standard rhythmic grid positions so they can be expressed as
    conventional music notation (quarter notes, eighth notes, etc.).
    """

    @abstractmethod
    def quantize(self, score: music21.stream.Score) -> music21.stream.Score:
        """Quantize a music21 Score and return the quantized version."""
        ...


class DefaultQuantization(QuantizationStrategy):
    """Use music21's built-in quantizer (no external reference)."""

    def quantize(self, score: music21.stream.Score) -> music21.stream.Score:
        return score.quantize()


class ReferenceGuidedQuantization(QuantizationStrategy):
    """Future: align transcription against a user-provided reference score.

    The reference score provides time signature, tempo changes, and a
    rhythmic grid.  Transcribed note onsets and durations are snapped to
    the reference grid instead of being inferred from raw audio timing.

    Accepted reference formats: anything music21 can parse -- MusicXML,
    MIDI, ABC, MEI, Humdrum, etc.
    """

    def __init__(self, reference_path: str):
        ref = Path(reference_path)
        if not ref.exists():
            raise FileNotFoundError(
                f"Reference score not found: {reference_path}"
            )
        self.reference = music21.converter.parse(str(ref))

    def quantize(self, score: music21.stream.Score) -> music21.stream.Score:
        # TODO: implement reference-guided alignment.  Sketch:
        #   1. Extract tempo map & time signatures from self.reference.
        #   2. Build a beat grid (list of absolute times for each beat).
        #   3. For each note in *score*, snap onset & offset to the
        #      nearest grid position.
        #   4. Re-derive note durations from snapped positions.
        raise NotImplementedError(
            "Reference-guided quantization is not yet implemented. "
            "Contributions welcome!"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def midi_to_abc(
    midi_path: str,
    abc_path: str,
    strategy: QuantizationStrategy | None = None,
) -> Path:
    """Convert a MIDI file to ABC notation.

    Args:
        midi_path: Path to the input .mid file.
        abc_path: Destination path for the .abc output.
        strategy: Quantization strategy to use.  Defaults to
            ``DefaultQuantization`` (music21 built-in quantizer).

    Returns:
        The resolved output Path.
    """
    if strategy is None:
        strategy = DefaultQuantization()

    score = music21.converter.parse(str(midi_path))
    score = strategy.quantize(score)

    out = Path(abc_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # music21's write method handles ABC serialization
    score.write("abc", fp=str(out))
    return out
