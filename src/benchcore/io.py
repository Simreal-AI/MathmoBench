from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"Duplicate JSON key: {key}")
        output[key] = value
    return output


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"Non-finite JSON number is forbidden: {value}")


def strict_json_loads(payload: str) -> Any:
    return json.loads(
        payload,
        object_pairs_hook=_object_without_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )


def canonical_sha256(value: Any) -> str:
    """Hash compact canonical JSON (sorted keys, no whitespace, UTF-8)."""
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def tree_manifest(root: str | Path) -> list[dict[str, Any]]:
    directory = Path(root).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("tree manifest root must be a directory")
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"tree manifest rejects symlink: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"tree manifest rejects special file: {path}")
        rows.append(
            {
                "path": path.relative_to(directory).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return rows


def tree_sha256(root: str | Path) -> str:
    return canonical_sha256(tree_manifest(root))


def load_json(path: str | Path) -> Any:
    return strict_json_loads(Path(path).read_text(encoding="utf-8"))


def load_jsonl(path: str | Path, *, id_field: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        row = strict_json_loads(raw)
        if not isinstance(row, dict):
            raise ValueError(f"JSONL line {line_number} is not an object")
        if id_field is not None:
            identity = row.get(id_field)
            if not isinstance(identity, str) or not identity:
                raise ValueError(f"JSONL line {line_number} lacks {id_field}")
            if identity in seen:
                raise ValueError(f"Duplicate {id_field}: {identity}")
            seen.add(identity)
        rows.append(row)
    return rows


def atomic_json(path: str | Path, value: Any) -> None:
    """Atomically publish a JSON receipt so interrupted grading cannot look complete."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
