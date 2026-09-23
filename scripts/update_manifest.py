"""Regenerate MANIFEST.sha256 for every release payload file.

Usage: python scripts/update_manifest.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import verify  # noqa: E402


def main() -> None:
    rows = []
    for relative, path in sorted(verify.actual_files().items()):
        with path.open("rb") as handle:
            rows.append(f"{hashlib.file_digest(handle, 'sha256').hexdigest()}  {relative}\n")
    (ROOT / verify.MANIFEST).write_text("".join(rows), encoding="utf-8")
    print(f"wrote {len(rows)} entries to {verify.MANIFEST}")


if __name__ == "__main__":
    main()
