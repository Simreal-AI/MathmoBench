#!/usr/bin/env python3
"""Verify this extracted release against its embedded SHA-256 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST = "MANIFEST.sha256"
IGNORED_DIRECTORIES = {
    ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv",
    "__pycache__", "build", "dist",
}
IGNORED_SUFFIXES = (".pyc", ".pyo", ".tmp")
IGNORED_FILE_NAMES = {".DS_Store"}


def safe_path(value: str) -> str:
    if not value or "\\" in value or "\x00" in value:
        raise ValueError(f"unsafe manifest path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe manifest path: {value!r}")
    return path.as_posix()


def ignored(path: PurePosixPath) -> bool:
    return any(
        part in IGNORED_DIRECTORIES or part.endswith(".egg-info")
        for part in path.parts
    ) or path.name in IGNORED_FILE_NAMES or path.name.endswith(IGNORED_SUFFIXES)


def expected_files() -> dict[str, str]:
    rows: dict[str, str] = {}
    for number, line in enumerate((ROOT / MANIFEST).read_text(encoding="utf-8").splitlines(), 1):
        if len(line) < 67 or line[64:66] != "  ":
            raise ValueError(f"invalid manifest line {number}")
        digest, path = line[:64], safe_path(line[66:])
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError(f"invalid SHA-256 on manifest line {number}")
        if path == MANIFEST or path in rows:
            raise ValueError(f"duplicate or self-referential manifest path: {path}")
        rows[path] = digest
    if not rows:
        raise ValueError("manifest is empty")
    return rows


def actual_files() -> dict[str, Path]:
    rows: dict[str, Path] = {}
    for current, directory_names, file_names in os.walk(ROOT, topdown=True, followlinks=False):
        directory = Path(current)
        kept_directories = []
        for name in sorted(directory_names):
            path = directory / name
            relative = PurePosixPath(path.relative_to(ROOT).as_posix())
            if ignored(relative):
                continue
            if path.is_symlink():
                raise ValueError(f"release contains a symlink: {relative}")
            if not stat.S_ISDIR(path.stat(follow_symlinks=False).st_mode):
                raise ValueError(f"release contains a special directory entry: {relative}")
            kept_directories.append(name)
        directory_names[:] = kept_directories
        for name in sorted(file_names):
            path = directory / name
            relative = PurePosixPath(path.relative_to(ROOT).as_posix())
            if relative.as_posix() == MANIFEST or ignored(relative):
                continue
            if path.is_symlink():
                raise ValueError(f"release contains a symlink: {relative}")
            if not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
                raise ValueError(f"release contains a special file: {relative}")
            rows[relative.as_posix()] = path
    return rows


def verify() -> int:
    expected = expected_files()
    actual = actual_files()
    if set(expected) != set(actual):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise ValueError(f"release file set differs; missing={missing}, extra={extra}")
    for relative in sorted(expected):
        with actual[relative].open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != expected[relative]:
            raise ValueError(f"SHA-256 mismatch: {relative}")
    return len(expected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tests", action="store_true", help="run the bundled unit tests after integrity checks")
    args = parser.parse_args()
    count = verify()
    tests = None
    if args.run_tests:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=ROOT,
            env=environment,
            check=False,
        )
        tests = completed.returncode
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)
    print(json.dumps({"status": "passed", "files": count, "tests_returncode": tests}, indent=2))


if __name__ == "__main__":
    main()
