"""
file_manager.py -- Manages upload and output file lifecycle.

Provides a single FileManager class that owns the uploads/ and outputs/
directories.  All file creation, lookup, and cleanup is routed through
this class so that server.py never touches the filesystem directly.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any


class FileManager:
    """Manages uploaded audio files, generated outputs, and job metadata."""

    def __init__(
        self,
        base_dir: Path | None = None,
        max_age_seconds: int = 3600,
    ):
        """Initialize the file manager.

        Args:
            base_dir: Root directory containing uploads/ and outputs/.
                Defaults to the directory where this module lives.
            max_age_seconds: Maximum age (in seconds) before a file is
                considered stale and eligible for cleanup.  Default 1 hour.
        """
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent

        self._uploads_dir = base_dir / "uploads"
        self._outputs_dir = base_dir / "outputs"
        self._max_age = max_age_seconds

        # Ensure directories exist
        self._uploads_dir.mkdir(parents=True, exist_ok=True)
        self._outputs_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Job lifecycle
    # ------------------------------------------------------------------

    def new_job(self) -> str:
        """Generate a unique job ID (8-character hex string)."""
        return uuid.uuid4().hex[:8]

    def save_upload(self, job_id: str, filename: str, data: bytes) -> Path:
        """Save uploaded audio to ``uploads/{job_id}{ext}``.

        Args:
            job_id: Unique job identifier.
            filename: Original filename from the upload (used for extension).
            data: Raw file bytes.

        Returns:
            Path to the saved upload file.
        """
        ext = Path(filename).suffix.lower()
        dest = self._uploads_dir / f"{job_id}{ext}"
        dest.write_bytes(data)
        return dest

    def get_upload_path(self, job_id: str) -> Path | None:
        """Look up the uploaded file for a job.

        Returns:
            The path if found, otherwise None.
        """
        matches = list(self._uploads_dir.glob(f"{job_id}.*"))
        return matches[0] if matches else None

    def midi_path(self, job_id: str) -> Path:
        """Return the canonical output path for a job's MIDI file."""
        return self._outputs_dir / f"{job_id}.mid"

    def abc_path(self, job_id: str) -> Path:
        """Return the canonical output path for a job's ABC file."""
        return self._outputs_dir / f"{job_id}.abc"

    def job_meta_path(self, job_id: str) -> Path:
        """Return the path for a job's metadata JSON file."""
        return self._outputs_dir / f"{job_id}.json"

    def save_job_meta(self, job_id: str, meta: dict[str, Any]) -> Path:
        """Persist job metadata (summary, URLs, etc.) as JSON.

        Args:
            job_id: Unique job identifier.
            meta: Dictionary to serialize.

        Returns:
            Path to the saved JSON file.
        """
        dest = self.job_meta_path(job_id)
        dest.write_text(json.dumps(meta, indent=2))
        return dest

    def load_job_meta(self, job_id: str) -> dict[str, Any] | None:
        """Load previously saved job metadata.

        Returns:
            The metadata dict, or None if the job doesn't exist.
        """
        path = self.job_meta_path(job_id)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def get_output_path(self, filename: str) -> Path | None:
        """Safely resolve an output filename.

        Prevents path traversal attacks by ensuring the resolved path
        stays within the outputs directory.

        Args:
            filename: The requested filename (e.g. ``a1b2c3.mid``).

        Returns:
            The resolved Path if valid and exists, otherwise None.
        """
        # Reject anything with path separators or parent references
        if "/" in filename or "\\" in filename or ".." in filename:
            return None

        candidate = (self._outputs_dir / filename).resolve()

        # Ensure it hasn't escaped the outputs directory
        if not str(candidate).startswith(str(self._outputs_dir.resolve())):
            return None

        return candidate if candidate.exists() else None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_job(self, job_id: str) -> None:
        """Remove the uploaded audio for a job (keeps outputs for download)."""
        upload = self.get_upload_path(job_id)
        if upload is not None:
            try:
                upload.unlink()
            except OSError:
                pass

    def cleanup_stale(self) -> int:
        """Delete files older than ``max_age_seconds`` in both directories.

        Returns:
            The number of files removed.
        """
        cutoff = time.time() - self._max_age
        removed = 0

        for directory in (self._uploads_dir, self._outputs_dir):
            for f in directory.iterdir():
                if f.is_file() and f.stat().st_mtime < cutoff:
                    try:
                        f.unlink()
                        removed += 1
                    except OSError:
                        pass

        return removed

    def cleanup_all(self) -> None:
        """Remove everything in both uploads/ and outputs/."""
        for directory in (self._uploads_dir, self._outputs_dir):
            for f in directory.iterdir():
                if f.is_file():
                    try:
                        f.unlink()
                    except OSError:
                        pass
