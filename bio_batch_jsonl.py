"""Process genealogical person data in bulk and generate biographies.

This utility reads people definitions from a JSON Lines file (one JSON object per
line), from a single JSON file containing either an object or a list of
objects, or from a directory with multiple ``.json`` files. For each person it
produces a short biography using :func:`build_biography` from ``bio_writer``.

Usage examples::

    python bio_batch_jsonl.py people.jsonl --outdir out
    python bio_batch_jsonl.py people.jsonl --combined biographies.txt
    python bio_batch_jsonl.py people.jsonl --outdir out --combined biographies.txt
    python bio_batch_jsonl.py people.json
    python bio_batch_jsonl.py json_dir/
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator, Optional, Tuple

from bio_writer import build_biography

SEPARATOR = "\n" + "-" * 80 + "\n\n"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_filename(s: str) -> str:
    """Return a safe filename fragment."""
    s = s.replace(" ", "_")
    return re.sub(r"[^\w\.-]", "", s)


def _iter_people_from_jsonl(path: Path, strict: bool, stats: dict) -> Iterator[Tuple[dict, str]]:
    """Yield (person, context) from ``path`` which is a JSON Lines file."""
    try:
        fh = path.open("r", encoding="utf-8-sig")
    except OSError as exc:
        msg = f"{path}: {exc}"
        if strict:
            raise RuntimeError(msg)
        sys.stderr.write(msg + "\n")
        return
    with fh:
        for lineno, line in enumerate(fh, 1):
            text = line.strip()
            if not text:
                continue
            try:
                yield json.loads(text), f"{path}:{lineno}"
            except json.JSONDecodeError as exc:
                msg = f"{path}:{lineno}: JSON parse error: {exc}"
                if strict:
                    raise RuntimeError(msg)
                sys.stderr.write(msg + "\n")
                stats["skipped"] += 1


def _iter_people_from_json(path: Path, strict: bool, stats: dict) -> Iterator[Tuple[dict, str]]:
    """Yield (person, context) from ``path`` which is a JSON file."""
    try:
        text = path.read_text(encoding="utf-8-sig")
        data = json.loads(text)
    except Exception as exc:
        msg = f"{path}: JSON parse error: {exc}"
        if strict:
            raise RuntimeError(msg)
        sys.stderr.write(msg + "\n")
        stats["skipped"] += 1
        return
    if isinstance(data, list):
        for obj in data:
            yield obj, str(path)
    elif isinstance(data, dict):
        yield data, str(path)
    else:
        msg = f"{path}: JSON top-level must be object or list"
        if strict:
            raise RuntimeError(msg)
        sys.stderr.write(msg + "\n")
        stats["skipped"] += 1


def _iter_people_from_dir(path: Path, strict: bool, stats: dict) -> Iterator[Tuple[dict, str]]:
    """Yield people from all ``.json`` files within ``path``."""
    for file in sorted(path.glob("*.json")):
        yield from _iter_people_from_json(file, strict, stats)


def emit_bios(
    people: Iterable[Tuple[dict, str]],
    outdir: Optional[Path],
    combined: Optional[Path],
    strict: bool,
    stats: dict,
) -> None:
    """Emit biographies from ``people`` into the desired destinations."""
    to_stdout = not outdir and not combined

    combined_handle = None
    if combined:
        combined.parent.mkdir(parents=True, exist_ok=True)
        combined_handle = combined.open("w", encoding="utf-8")
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    try:
        first_combined = True
        for person, ctx in people:
            if not isinstance(person, dict):
                msg = f"{ctx}: entry is not a JSON object"
                if strict:
                    raise RuntimeError(msg)
                sys.stderr.write(msg + "\n")
                stats["skipped"] += 1
                continue
            if not person.get("henry_number") or not person.get("name"):
                msg = f"{ctx}: missing 'henry_number' or 'name'"
                if strict:
                    raise RuntimeError(msg)
                sys.stderr.write(msg + "\n")
                stats["skipped"] += 1
                continue
            try:
                bio = build_biography(person)
            except Exception as exc:
                msg = f"{ctx}: error generating biography: {exc}"
                if strict:
                    raise RuntimeError(msg)
                sys.stderr.write(msg + "\n")
                stats["skipped"] += 1
                continue

            stats["processed"] += 1

            if outdir:
                filename = _sanitize_filename(
                    f"{person['henry_number']}_{person['name']}.txt"
                )
                (outdir / filename).write_text(bio, encoding="utf-8")

            if combined_handle:
                if not first_combined:
                    combined_handle.write(SEPARATOR)
                combined_handle.write(bio)
                first_combined = False

            if to_stdout:
                sys.stdout.write(bio)
                sys.stdout.write(SEPARATOR)
    finally:
        if combined_handle:
            combined_handle.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate biographies from genealogical JSON data."
    )
    parser.add_argument("input", help="Input .jsonl/.json file or directory")
    parser.add_argument(
        "--outdir", type=Path, help="Write one biography per file into directory"
    )
    parser.add_argument(
        "--combined", type=Path, help="Write all biographies into a single file"
    )
    parser.add_argument(
        "--strict", action="store_true", help="Abort on first error"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = {"processed": 0, "skipped": 0}

    input_path = Path(args.input)
    if not input_path.exists():
        sys.stderr.write(f"{input_path}: no such file or directory\n")
        sys.exit(1)

    try:
        if input_path.is_dir():
            people_iter = _iter_people_from_dir(input_path, args.strict, stats)
        elif input_path.suffix.lower() == ".jsonl":
            people_iter = _iter_people_from_jsonl(input_path, args.strict, stats)
        elif input_path.suffix.lower() == ".json":
            people_iter = _iter_people_from_json(input_path, args.strict, stats)
        else:
            sys.stderr.write("Input must be .jsonl, .json, or a directory\n")
            sys.exit(1)

        emit_bios(people_iter, args.outdir, args.combined, args.strict, stats)
    except RuntimeError as exc:
        sys.stderr.write(str(exc) + "\n")
        sys.exit(1)
    except Exception as exc:
        sys.stderr.write(f"Unexpected error: {exc}\n")
        sys.exit(1)

    if not args.strict:
        sys.stderr.write(
            f"{stats['processed']} processadas, {stats['skipped']} ignoradas por erro\n"
        )


if __name__ == "__main__":
    main()