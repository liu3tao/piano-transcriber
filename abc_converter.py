"""
abc_converter.py -- MIDI-to-ABC notation conversion.

Builds ABC notation directly from MIDI files using pretty_midi,
bypassing music21's ABC writer (which produces malformed output
for polyphonic piano transcriptions).

Also provides a pluggable QuantizationStrategy abstraction for
future reference-guided quantization.
"""

from abc import ABC, abstractmethod
from pathlib import Path

import music21
import pretty_midi


# ---------------------------------------------------------------------------
# Quantization strategy abstraction
# ---------------------------------------------------------------------------

class QuantizationStrategy(ABC):
    """Base class for quantization strategies."""

    @abstractmethod
    def quantize(self, score: music21.stream.Score) -> music21.stream.Score:
        """Quantize a music21 Score and return the quantized version."""
        ...


class DefaultQuantization(QuantizationStrategy):
    """Use music21's built-in quantizer (no external reference)."""

    def quantize(self, score: music21.stream.Score) -> music21.stream.Score:
        return score.quantize()


class ReferenceGuidedQuantization(QuantizationStrategy):
    """Future: align transcription against a user-provided reference score."""

    def __init__(self, reference_path: str):
        ref = Path(reference_path)
        if not ref.exists():
            raise FileNotFoundError(
                f"Reference score not found: {reference_path}"
            )
        self.reference = music21.converter.parse(str(ref))

    def quantize(self, score: music21.stream.Score) -> music21.stream.Score:
        raise NotImplementedError(
            "Reference-guided quantization is not yet implemented. "
            "Contributions welcome!"
        )


# ---------------------------------------------------------------------------
# Direct MIDI-to-ABC converter
# ---------------------------------------------------------------------------

_NOTE_NAMES = ["C", "^C", "D", "^D", "E", "F", "^F", "G", "^G", "A", "^A", "B"]

# Standard musical durations in eighth-note units (with L:1/8).
# Sorted descending so we snap to the longest that fits.
_STANDARD_EIGHTHS = [32, 24, 16, 12, 8, 6, 4, 3, 2, 1]


def _midi_pitch_to_abc(midi_pitch: int) -> str:
    """Convert a MIDI pitch number (0-127) to an ABC note token."""
    octave = (midi_pitch // 12) - 1
    note_idx = midi_pitch % 12
    name = _NOTE_NAMES[note_idx]

    # ABC reference: uppercase C D E F G A B = octave 4 (middle C = C4)
    #                lowercase c d e f g a b = octave 5
    if octave <= 4:
        commas = max(0, 4 - octave)
        return name + "," * commas
    else:
        if name[0] == "^":
            name = "^" + name[1].lower()
        else:
            name = name[0].lower()
        ticks = max(0, octave - 5)
        return name + "'" * ticks


def _snap_to_standard(eighths: float) -> int:
    """Snap a duration (in eighth-note units) to the nearest standard value."""
    best = 1
    best_dist = abs(eighths - 1)
    for s in _STANDARD_EIGHTHS:
        dist = abs(eighths - s)
        if dist < best_dist:
            best = s
            best_dist = dist
    return best


def _eighths_to_abc_len(n: int) -> str:
    """Convert a duration in eighth-note units to an ABC length string.

    With L:1/8 as the default unit length:
      1 eighth  = '' (empty)
      2 eighths = '2'
      3 eighths = '3'
      4 eighths = '4'  (half note)
      6 eighths = '6'  (dotted half)
      8 eighths = '8'  (whole note)
      etc.
    Half an eighth (shouldn't happen after snapping) -> '/2'
    """
    if n <= 0:
        return ""
    if n == 1:
        return ""
    return str(n)


def _build_abc_from_midi(midi_path: str, title: str = "Transcription") -> str:
    """Build an ABC notation string directly from a MIDI file.

    Uses eighth-note quantization grid to produce simple, clean ABC
    that renders reliably in abcjs.
    """
    pm = pretty_midi.PrettyMIDI(str(midi_path))

    # Collect all notes
    all_notes = []
    for inst in pm.instruments:
        for note in inst.notes:
            all_notes.append(note)

    if not all_notes:
        return f"X:1\nT:{title}\nM:4/4\nL:1/8\nK:C\nz8|\n"

    all_notes.sort(key=lambda n: (n.start, n.pitch))

    # Estimate tempo
    tempos = pm.get_tempo_changes()
    bpm = tempos[1][0] if len(tempos[1]) > 0 else 120.0
    eighth_dur = 60.0 / bpm / 2  # seconds per eighth note

    # Quantize note onsets and durations to eighth-note grid
    quantized = []
    for note in all_notes:
        onset_eighths = max(0, round(note.start / eighth_dur))
        dur_eighths = max(1, round((note.end - note.start) / eighth_dur))
        # Snap duration to a standard musical value
        dur_eighths = _snap_to_standard(dur_eighths)
        quantized.append((onset_eighths, dur_eighths, note.pitch))

    # Group notes by onset time into chords
    events = {}
    for onset, dur, pitch in quantized:
        if onset not in events:
            events[onset] = []
        events[onset].append((dur, pitch))

    sorted_onsets = sorted(events.keys())

    # Build ABC body
    beats_per_measure = 8  # 8 eighth notes = 4/4 time
    measures_per_line = 4
    tokens = []
    current_pos = 0  # in eighth-note units
    beat_in_measure = 0
    measure_count = 0

    for onset in sorted_onsets:
        note_group = events[onset]

        # Insert rest if there's a gap
        gap = onset - current_pos
        if gap > 0:
            # Break rest into standard durations
            remaining = gap
            while remaining > 0:
                rest_dur = _snap_to_standard(remaining)
                if rest_dur > remaining:
                    # Find the largest standard that fits
                    for s in _STANDARD_EIGHTHS:
                        if s <= remaining:
                            rest_dur = s
                            break
                    else:
                        rest_dur = 1
                tokens.append("z" + _eighths_to_abc_len(rest_dur))
                beat_in_measure += rest_dur
                remaining -= rest_dur

                # Check for barlines
                while beat_in_measure >= beats_per_measure:
                    beat_in_measure -= beats_per_measure
                    measure_count += 1
                    if measure_count % measures_per_line == 0:
                        tokens.append("|\n")
                    else:
                        tokens.append("|")

        # Use shortest duration in the chord group
        dur = min(d for d, _ in note_group)
        pitches = sorted(set(p for _, p in note_group))

        # Build note/chord token
        if len(pitches) == 1:
            token = _midi_pitch_to_abc(pitches[0]) + _eighths_to_abc_len(dur)
        else:
            chord_str = "".join(_midi_pitch_to_abc(p) for p in pitches)
            token = "[" + chord_str + "]" + _eighths_to_abc_len(dur)

        tokens.append(token)
        current_pos = onset + dur
        beat_in_measure += dur

        # Check for barlines
        while beat_in_measure >= beats_per_measure:
            beat_in_measure -= beats_per_measure
            measure_count += 1
            if measure_count % measures_per_line == 0:
                tokens.append("|\n")
            else:
                tokens.append("|")

    # Final barline
    if tokens and not tokens[-1].rstrip().endswith("|"):
        tokens.append("|]")

    body = " ".join(tokens)
    # Clean up whitespace around barlines
    body = body.replace(" |\n ", "|\n").replace(" | ", " |")

    qpm = int(round(bpm))
    header = (
        f"X:1\n"
        f"T:{title}\n"
        f"M:4/4\n"
        f"L:1/8\n"
        f"Q:1/4={qpm}\n"
        f"K:C\n"
    )

    return header + body + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def midi_to_abc(
    midi_path: str,
    abc_path: str,
    strategy: QuantizationStrategy | None = None,
) -> Path:
    """Convert a MIDI file to ABC notation.

    Uses a direct MIDI-to-ABC builder for robust output that avoids
    music21's ABC writer issues with polyphonic piano transcriptions.

    Args:
        midi_path: Path to the input .mid file.
        abc_path: Destination path for the .abc output.
        strategy: Quantization strategy (reserved for future use).

    Returns:
        The resolved output Path.
    """
    abc_text = _build_abc_from_midi(midi_path)

    out = Path(abc_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(abc_text)
    return out
