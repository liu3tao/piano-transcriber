# Piano Note Recognizer

A CLI tool that transcribes piano audio recordings into MIDI files and optionally ABC notation for music-sheet rendering. Powered by Spotify's [basic-pitch](https://github.com/spotify/basic-pitch) neural network for polyphonic note detection.

## Features

- Reads `.wav`, `.mp3`, `.ogg`, and `.flac` audio files
- Detects polyphonic piano notes (chords, arpeggios, complex passages)
- Outputs standard `.mid` (MIDI) files
- Optionally exports ABC notation (`.abc`) for sheet-music rendering
- Configurable detection thresholds for tuning accuracy vs. sensitivity

## Installation

Requires Python 3.10+.

```bash
pip install -r requirements.txt
```

> **Note:** `basic-pitch` installs TensorFlow automatically. On first run, the
> neural-network model (~200 MB) will be downloaded and cached.

## Usage

### Basic: audio to MIDI

```bash
python main.py recording.wav
# -> produces recording.mid
```

### Specify output path

```bash
python main.py recording.mp3 -o my_transcription.mid
```

### With ABC notation output

```bash
python main.py recording.wav -o output.mid --abc output.abc
```

### Full options

```
usage: piano-transcriber [-h] [-o OUTPUT] [--abc ABC_PATH]
                         [--onset-threshold T] [--frame-threshold T]
                         [--min-note-length MS]
                         input

positional arguments:
  input                 Path to the piano audio file

options:
  -h, --help            show this help message and exit
  -o, --output OUTPUT   Path for the output MIDI file (default: <input>.mid)
  --abc ABC_PATH        Also write ABC notation to this path

transcription parameters:
  --onset-threshold T   Note onset confidence, 0-1 (default: 0.5)
  --frame-threshold T   Note frame confidence, 0-1 (default: 0.3)
  --min-note-length MS  Minimum note duration in ms (default: 58)
```

## Tuning Parameters

The three transcription parameters let you trade off between sensitivity and precision:

| Parameter | Effect of raising | Effect of lowering |
|---|---|---|
| `--onset-threshold` | Fewer notes detected, higher confidence | More notes, may include false positives |
| `--frame-threshold` | Shorter notes, only most confident frames kept | Longer notes, may bleed into silence |
| `--min-note-length` | Very short notes discarded (reduces noise) | Keeps fast ornamental notes (trills, grace notes) |

**Suggested starting points:**

- Clean studio recording: defaults work well (`0.5` / `0.3` / `58`)
- Noisy or reverberant recording: raise onset to `0.6`, frame to `0.4`
- Fast passages with ornaments: lower min-note-length to `30`

## Project Structure

```
piano_transcriber/
├── main.py            # CLI entry point
├── transcriber.py     # Audio-to-MIDI using basic-pitch
├── abc_converter.py   # MIDI-to-ABC with pluggable quantization
├── requirements.txt   # Python dependencies
└── README.md          # This file
```

## Architecture Notes

### Quantization Strategy

The ABC converter uses a pluggable `QuantizationStrategy` abstraction. The
default strategy uses music21's built-in quantizer. A `ReferenceGuidedQuantization`
class is stubbed out for future use -- it would accept a reference music score
(MusicXML, MIDI, ABC, etc.) to guide quantization, improving output quality for
pieces with rubato or complex rhythms.

## License

MIT
