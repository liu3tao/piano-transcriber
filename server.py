#!/usr/bin/env python3
"""
server.py -- FastAPI backend for the Piano Note Recognizer web UI.

Provides REST API endpoints for audio transcription and serves the
static frontend.  Delegates all file operations to FileManager and
all transcription logic to the existing transcriber module.

Run with:
    python server.py
    # or
    uvicorn server:app --reload
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from abc_converter import midi_to_abc
from file_manager import FileManager
from transcriber import SUPPORTED_EXTENSIONS, NoteEvent, save_midi, transcribe

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

fm = FileManager()

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _midi_pitch_to_name(pitch: int) -> str:
    """Convert a MIDI pitch number to a human-readable note name."""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = (pitch // 12) - 1
    return f"{names[pitch % 12]}{octave}"


def _build_summary(note_events: list[NoteEvent]) -> dict:
    """Build a JSON-serializable summary from note events."""
    if not note_events:
        return {
            "num_notes": 0,
            "duration_seconds": 0,
            "pitch_range": [],
            "time_span": [],
        }

    starts = [n.start_time for n in note_events]
    ends = [n.end_time for n in note_events]
    pitches = [n.midi_pitch for n in note_events]

    lowest = min(pitches)
    highest = max(pitches)

    return {
        "num_notes": len(note_events),
        "duration_seconds": round(max(ends) - min(starts), 2),
        "pitch_range": [_midi_pitch_to_name(lowest), _midi_pitch_to_name(highest)],
        "time_span": [round(min(starts), 2), round(max(ends), 2)],
    }


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Clean up stale files on startup."""
    removed = fm.cleanup_stale()
    if removed:
        print(f"Cleaned up {removed} stale file(s) from previous sessions.")
    yield


app = FastAPI(
    title="Piano Note Recognizer",
    description="Transcribe piano audio to MIDI and ABC notation.",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.post("/api/transcribe")
async def api_transcribe(
    file: UploadFile = File(...),
    onset_threshold: float = Form(0.5),
    frame_threshold: float = Form(0.3),
    min_note_length: float = Form(58),
    abc: bool = Form(False),
):
    """Upload an audio file and transcribe it to MIDI."""

    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported audio format '{ext}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )

    # Save upload
    job_id = fm.new_job()
    data = await file.read()
    upload_path = fm.save_upload(job_id, file.filename, data)

    # Transcribe
    try:
        midi_data, note_events = transcribe(
            str(upload_path),
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            min_note_len_ms=min_note_length,
        )
    except Exception as exc:
        fm.cleanup_job(job_id)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")

    # Save MIDI
    save_midi(midi_data, str(fm.midi_path(job_id)))

    # Clean up uploaded audio (no longer needed)
    fm.cleanup_job(job_id)

    # Optionally generate ABC
    abc_url = None
    if abc:
        try:
            midi_to_abc(str(fm.midi_path(job_id)), str(fm.abc_path(job_id)))
            abc_url = f"/api/files/{job_id}.abc"
        except Exception:
            pass  # ABC generation is best-effort

    # Build response
    summary = _build_summary(note_events)
    response = {
        "job_id": job_id,
        "midi_url": f"/api/files/{job_id}.mid",
        "abc_url": abc_url,
        "summary": summary,
    }

    # Persist metadata so result.html can fetch it later
    fm.save_job_meta(job_id, response)

    return response


@app.get("/api/jobs/{job_id}")
async def api_get_job(job_id: str):
    """Retrieve metadata for a completed transcription job."""
    meta = fm.load_job_meta(job_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return meta


@app.get("/api/files/{filename}")
async def api_get_file(filename: str):
    """Serve a generated output file (MIDI or ABC)."""
    path = fm.get_output_path(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, filename=filename)


# ---------------------------------------------------------------------------
# Static files (frontend) -- must be mounted last
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


# ---------------------------------------------------------------------------
# Dev server entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
