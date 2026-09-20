#!/usr/bin/env python3
"""Remove private network details and expired signed credentials from a corpus.

The sanitizer preserves public provenance URLs. It redacts private IPv4 values,
localhost references, AWS presigned credential/signature values, and matching
text rendered into corpus images. It then refreshes affected image references
and manifest hashes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import ipaddress
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


TEXT_SUFFIXES = {".json", ".jsonl", ".md"}
IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
LOCALHOST_URL_RE = re.compile(r"(?i)https?://(?:localhost|host\.docker\.internal)(?::\d+)?(?:/[^\s\"'<>]*)?")
LOCALHOST_RE = re.compile(r"(?i)\b(?:localhost|host\.docker\.internal)\b")
AWS_QUERY_RE = re.compile(r"(?i)(X-Amz-(?:Credential|Signature|Security-Token)=)([^&\s\"'\\]+)")
REDACTED_ADDRESS = "[REDACTED PRIVATE NETWORK ADDRESS]"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_private_ipv4(raw: str) -> bool:
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return False
    return address.version == 4 and (
        address.is_private or address.is_loopback or address.is_link_local or address.is_reserved
    )


def private_ipv4s(text: str) -> list[str]:
    return [match.group(0) for match in IPV4_RE.finditer(text) if is_private_ipv4(match.group(0))]


def sanitize_text(text: str, counts: Counter[str]) -> str:
    def replace_ip(match: re.Match[str]) -> str:
        raw = match.group(0)
        if is_private_ipv4(raw):
            counts["private_ipv4_values"] += 1
            return REDACTED_ADDRESS
        return raw

    text = IPV4_RE.sub(replace_ip, text)
    text, n = AWS_QUERY_RE.subn(r"\1[REDACTED]", text)
    counts["aws_signed_query_values"] += n
    text, n = LOCALHOST_URL_RE.subn("[REDACTED INTERNAL URL]", text)
    counts["internal_urls"] += n
    text, n = LOCALHOST_RE.subn("[REDACTED INTERNAL HOST]", text)
    counts["internal_hostnames"] += n
    return text


def walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_strings(child)


def find_sensitive_image_paths(metadata_file: Path, corpus_root: Path) -> set[Path]:
    found: set[Path] = set()
    if metadata_file.suffix == ".jsonl":
        candidates = []
        for line in metadata_file.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                candidates.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    elif metadata_file.suffix == ".json":
        try:
            candidates = [json.loads(metadata_file.read_text(encoding="utf-8", errors="replace"))]
        except json.JSONDecodeError:
            candidates = []
    else:
        candidates = []
    for record in candidates:
        if not any(private_ipv4s(value) for value in walk_strings(record)):
            continue
        stack = [record]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                for key in ("image_path", "page_image_path"):
                    if isinstance(value.get(key), str):
                        path = (metadata_file.parent / value[key]).resolve()
                        if path.is_file() and corpus_root in path.parents:
                            found.add(path)
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
    return found


def redact_image(path: Path) -> int:
    result = subprocess.run(
        ["tesseract", str(path), "stdout", "tsv"],
        check=True,
        capture_output=True,
        text=True,
    )
    rectangles: list[tuple[int, int, int, int]] = []
    for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
        token = row.get("text", "")
        if not private_ipv4s(token):
            continue
        left, top = int(row["left"]), int(row["top"])
        width, height = int(row["width"]), int(row["height"])
        margin = max(3, height // 5)
        rectangles.append((left - margin, top - margin, left + width + margin, top + height + margin))
    if not rectangles:
        raise RuntimeError(f"Metadata contained a private address but no matching image text was found: {path}")
    with Image.open(path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    for box in rectangles:
        draw.rectangle(box, fill="black")
        draw.text((box[0] + 3, box[1] + 2), "REDACTED", fill="white")
    image.save(path, format="JPEG", quality=95, optimize=True)
    return len(rectangles)


def refresh_image_hashes(value: Any, base: Path) -> bool:
    changed = False
    if isinstance(value, dict):
        for path_key, hash_key in (("image_path", "image_sha256"), ("page_image_path", "page_image_sha256")):
            rel = value.get(path_key)
            if isinstance(rel, str):
                target = (base / rel).resolve()
                if target.is_file() and hash_key in value:
                    digest = sha256(target)
                    if value[hash_key] != digest:
                        value[hash_key] = digest
                        changed = True
        for child in value.values():
            changed = refresh_image_hashes(child, base) or changed
    elif isinstance(value, list):
        for child in value:
            changed = refresh_image_hashes(child, base) or changed
    return changed


def refresh_metadata_image_hashes(path: Path) -> bool:
    if path.suffix == ".jsonl":
        rows = []
        changed = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            changed = refresh_image_hashes(row, path.parent) or changed
            rows.append(row)
        if changed:
            path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        return changed
    if path.suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        changed = refresh_image_hashes(value, path.parent)
        if changed:
            path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return changed
    return False


def refresh_manifests(data_root: Path) -> int:
    updated = 0
    for path in data_root.rglob("manifest.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        changed = False
        files = value.get("files")
        if isinstance(files, dict):
            for rel, meta in files.items():
                target = path.parent / rel
                if target.is_file() and isinstance(meta, dict) and "sha256" in meta:
                    digest = sha256(target)
                    if meta["sha256"] != digest:
                        meta["sha256"] = digest
                        changed = True
        canonical = value.get("canonical_work_file")
        if isinstance(canonical, str) and (path.parent / canonical).is_file() and "canonical_literature_sha256" in value:
            digest = sha256(path.parent / canonical)
            if value["canonical_literature_sha256"] != digest:
                value["canonical_literature_sha256"] = digest
                changed = True
        if changed:
            path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            updated += 1
    return updated


def refresh_archive_checksums(root: Path) -> int:
    updated = 0
    for path in root.rglob("*checksums.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        changed = False
        for rel in list(value):
            target = path.parent / rel
            if target.is_file() and isinstance(value[rel], str) and re.fullmatch(r"[0-9a-f]{64}", value[rel]):
                digest = sha256(target)
                if value[rel] != digest:
                    value[rel] = digest
                    changed = True
        if changed:
            path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            updated += 1
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    project = args.project_root.resolve()
    data_root = project / "data"
    scan_roots = [data_root, project / "src" / "literature_pipeline"]
    text_files = sorted(
        path for root in scan_roots if root.exists()
        for path in root.rglob("*") if path.is_file() and path.suffix.casefold() in TEXT_SUFFIXES
    )
    image_paths: set[Path] = set()
    for path in text_files:
        if path.is_relative_to(data_root) and path.suffix in {".json", ".jsonl"}:
            image_paths.update(find_sensitive_image_paths(path, data_root))

    counts: Counter[str] = Counter()
    for path in sorted(image_paths):
        counts["image_redaction_rectangles"] += redact_image(path)
        counts["images_redacted"] += 1

    for path in text_files:
        original = path.read_text(encoding="utf-8", errors="replace")
        cleaned = sanitize_text(original, counts)
        if cleaned != original:
            path.write_text(cleaned, encoding="utf-8")
            counts["text_files_changed"] += 1

    for path in sorted(p for p in data_root.rglob("*") if p.is_file() and p.suffix in {".json", ".jsonl"}):
        if refresh_metadata_image_hashes(path):
            counts["metadata_files_rehashed"] += 1
    counts["manifests_rehashed"] = refresh_manifests(data_root)
    counts["archive_checksum_files_rehashed"] = refresh_archive_checksums(project / "src" / "literature_pipeline")
    print(json.dumps(dict(sorted(counts.items())), indent=2))


if __name__ == "__main__":
    main()
