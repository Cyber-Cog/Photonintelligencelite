"""Per-job ephemeral filesystem lifecycle.

Every job gets an unguessable UUID directory. Raw uploads are streamed to disk (never
buffered fully in memory), gzip is decompressed in bounded chunks with a decompression-ratio
cap to guard against decompression bombs, and the whole directory is deleted at the end of
the job lifecycle. See docs/architecture_decisions.md §7 and docs/PRD.md §14.
"""
from __future__ import annotations

import gzip
import shutil
from dataclasses import dataclass
from pathlib import Path


class UploadTooLargeError(Exception):
    pass


class DecompressionBombError(Exception):
    pass


@dataclass(frozen=True)
class JobPaths:
    root: Path

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def canonical_dir(self) -> Path:
        return self.root / "canonical"

    @property
    def results_dir(self) -> Path:
        return self.root / "results"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def charts_dir(self) -> Path:
        return self.root / "charts"

    def ensure(self) -> "JobPaths":
        for d in (self.raw_dir, self.canonical_dir, self.results_dir, self.reports_dir, self.charts_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self


def job_paths(job_root: Path, job_id: str) -> JobPaths:
    return JobPaths(root=job_root / job_id).ensure()


def sanitize_filename(filename: str) -> str:
    keep = "".join(c for c in filename if c.isalnum() or c in "._- ")
    return keep.strip() or "upload.csv"


async def save_upload_stream(upload_file, dest_path: Path, max_bytes: int) -> int:
    """Stream an UploadFile to disk, enforcing a byte cap without buffering the whole file."""
    total = 0
    chunk_size = 1024 * 1024
    with open(dest_path, "wb") as out:
        while True:
            chunk = await upload_file.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                out.close()
                dest_path.unlink(missing_ok=True)
                raise UploadTooLargeError(f"Upload exceeds the {max_bytes // (1024 * 1024)} MB limit for this deployment.")
            out.write(chunk)
    return total


def decompress_gzip_bounded(gz_path: Path, dest_path: Path, max_decompressed_bytes: int, max_ratio: int) -> int:
    """Decompress a .gz file in bounded chunks, enforcing an absolute size cap and a
    decompression-ratio cap (defends against decompression-bomb uploads).
    """
    compressed_size = gz_path.stat().st_size or 1
    written = 0
    chunk_size = 1024 * 1024
    with gzip.open(gz_path, "rb") as gz, open(dest_path, "wb") as out:
        while True:
            chunk = gz.read(chunk_size)
            if not chunk:
                break
            written += len(chunk)
            if written > max_decompressed_bytes:
                out.close()
                dest_path.unlink(missing_ok=True)
                raise UploadTooLargeError(f"Decompressed upload exceeds the {max_decompressed_bytes // (1024 * 1024)} MB limit for this deployment.")
            if written / compressed_size > max_ratio:
                out.close()
                dest_path.unlink(missing_ok=True)
                raise DecompressionBombError("Compressed file expands far beyond the expected ratio and was rejected as unsafe.")
            out.write(chunk)
    return written


def delete_job_dir(job_root: Path, job_id: str) -> None:
    path = job_root / job_id
    shutil.rmtree(path, ignore_errors=True)
