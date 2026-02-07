#!/usr/bin/env python3
"""
Piano Note Recognizer -- CLI entry point.

Transcribes piano audio recordings (.wav / .mp3) into MIDI files and,
optionally, ABC notation for music-sheet rendering.

Usage examples:
    python main.py recording.wav
    python main.py recording.mp3 -o output.mid --abc output.abc
    python main.py recording.wav --onset-threshold 0.6 --frame-threshold 0.4
"""

import argparse
import sys
import time
from pathlib import Path

from transcriber import (
    SUPPORTED_EXTENSIONS,
    NoteEvent,
    save_midi,
    transcribe,
    validate_audio_path,
)


def _midi_pitch_to_name(pitch: int) -> str:
    """Convert a MIDI pitch number to a human-readable note name."""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = (pitch // 12) - 1
    return f"{names[pitch % 12]}{octave}"


def _print_summary(note_events: list[NoteEvent], midi_path: Path, abc_path: Path | None) -> None:
    """Print a human-readable summary of the transcription."""
    print()
    print("=" * 56)
    print("  Piano Transcription Summary")
    print("=" * 56)

    if not note_events:
        print("  WARNING: No notes detected in the recording.")
        print("  Try lowering --onset-threshold or --frame-threshold.")
    else:
        starts = [n.start_time for n in note_events]
        ends = [n.end_time for n in note_events]
        pitches = [n.midi_pitch for n in note_events]

        duration = max(ends) - min(starts)
        lowest = min(pitches)
        highest = max(pitches)

        print(f"  Notes detected : {len(note_events)}")
        print(f"  Time span      : {min(starts):.2f}s - {max(ends):.2f}s ({duration:.2f}s)")
        print(f"  Pitch range    : {_midi_pitch_to_name(lowest)} ({lowest}) - "
              f"{_midi_pitch_to_name(highest)} ({highest})")

    print(f"  MIDI output    : {midi_path}")
    if abc_path is not None:
        print(f"  ABC output     : {abc_path}")
    print("=" * 56)
    print()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="piano-transcriber",
        description="Transcribe piano audio to MIDI (and optionally ABC notation).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python main.py recording.wav\n"
            "  python main.py recording.mp3 -o output.mid --abc output.abc\n"
            "  python main.py recording.wav --onset-threshold 0.6\n"
        ),
    )

    parser.add_argument(
        "input",
        help=(
            f"Path to the piano audio file. "
            f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        ),
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Path for the output MIDI file (default: <input_stem>.mid)",
    )
    parser.add_argument(
        "--abc",
        default=None,
        metavar="ABC_PATH",
        help="If provided, also write ABC notation to this path.",
    )

    # Transcription tuning knobs
    tuning = parser.add_argument_group("transcription parameters")
    tuning.add_argument(
        "--onset-threshold",
        type=float,
        default=0.5,
        metavar="T",
        help="Note onset confidence threshold, 0-1 (default: 0.5). "
             "Higher = fewer but more confident onsets.",
    )
    tuning.add_argument(
        "--frame-threshold",
        type=float,
        default=0.3,
        metavar="T",
        help="Note frame confidence threshold, 0-1 (default: 0.3). "
             "Higher = shorter, more confident notes.",
    )
    tuning.add_argument(
        "--min-note-length",
        type=float,
        default=58,
        metavar="MS",
        help="Minimum note duration in milliseconds (default: 58, ~a 64th note).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the piano transcription pipeline."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # --- Validate input ---
    try:
        audio_path = validate_audio_path(args.input)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # --- Resolve output path ---
    if args.output is not None:
        midi_output = Path(args.output)
    else:
        midi_output = audio_path.with_suffix(".mid")

    abc_output = Path(args.abc) if args.abc else None

    # --- Transcribe ---
    print(f"Transcribing: {audio_path}")
    t0 = time.perf_counter()

    try:
        midi_data, note_events = transcribe(
            str(audio_path),
            onset_threshold=args.onset_threshold,
            frame_threshold=args.frame_threshold,
            min_note_len_ms=args.min_note_length,
        )
    except Exception as exc:
        print(f"Transcription failed: {exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - t0
    print(f"Transcription completed in {elapsed:.1f}s")

    # --- Write MIDI ---
    save_midi(midi_data, str(midi_output))
    print(f"MIDI saved to: {midi_output}")

    # --- Optionally write ABC ---
    if abc_output is not None:
        print(f"Converting to ABC notation...")
        try:
            from abc_converter import midi_to_abc

            midi_to_abc(str(midi_output), str(abc_output))
            print(f"ABC saved to: {abc_output}")
        except Exception as exc:
            print(f"ABC conversion failed: {exc}", file=sys.stderr)
            print("(MIDI file was still saved successfully.)")

    # --- Summary ---
    _print_summary(note_events, midi_output, abc_output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
