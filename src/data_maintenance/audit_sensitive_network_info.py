#!/usr/bin/env python3
"""Audit ingestible Graph-RAG text for sensitive network configuration.

Public provenance URLs and documented credential placeholders are classified
as informational.  Private addresses, MAC addresses, internal hostnames,
credential-bearing URLs, and plausible embedded secrets are findings.
Reports contain hashes and redacted previews rather than secret values.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


TEXT_SUFFIXES = {".json", ".jsonl", ".md"}
IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
# Requiring non-identifier boundaries avoids treating corpus IDs such as
# ``paper::10.1007/...`` and ``...A301::desc`` as compressed IPv6 literals.
IPV6_RE = re.compile(r"(?<![A-Za-z0-9_:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![A-Za-z0-9_:])")
MAC_RE = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f])")
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
INTERNAL_HOST_RE = re.compile(r"\b(?:localhost|host\.docker\.internal)\b", re.I)
SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "assigned_secret": re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|password|passwd|secret|authorization|bearer)\b\s*[:=]\s*[\"']?([A-Za-z0-9_./+=:-]{8,})"),
}
NETWORK_KEYS = re.compile(r"(?i)^(?:ip(?:_?address)?|ipv4|ipv6|mac(?:_?address)?|gateway|subnet|netmask|dns(?:_?server)?|hostname|host_?name|server_?address|ssh_?host|snmp_?community)$")
PLACEHOLDER_RE = re.compile(r"(?i)^(?:api_?)?(?:username|token|password|key|secret)|example|placeholder|redacted|your[_-]")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _redacted(value: str) -> str:
    if len(value) <= 6:
        return "[REDACTED]"
    return value[:2] + "…" + value[-2:]


def _location(root: Path, path: Path, line_number: int | None = None, json_key: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"path": path.relative_to(root).as_posix()}
    if line_number is not None:
        out["line"] = line_number
    if json_key is not None:
        out["json_key"] = json_key
    return out


def _classify_ip(value: str) -> str | None:
    if value == "::":
        return None
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if address.is_loopback:
        return "loopback_ip"
    if address.is_link_local:
        return "link_local_ip"
    if address.is_private:
        return "private_ip"
    if address.is_multicast:
        return "multicast_ip"
    if address.is_reserved or address.is_unspecified:
        return "reserved_ip"
    return "public_ip"


def _walk_json(value: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, child
            yield from _walk_json(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_json(child, f"{prefix}[{index}]")


def audit(roots: list[Path]) -> dict[str, Any]:
    roots = [root.resolve() for root in roots]
    sensitive: list[dict[str, Any]] = []
    informational: Counter[str] = Counter()
    public_hosts: Counter[str] = Counter()
    files_scanned = 0
    bytes_scanned = 0
    seen: set[tuple[str, str, int | None, str]] = set()

    def add(kind: str, raw: str, root: Path, path: Path, line_number: int | None = None, json_key: str | None = None) -> None:
        marker = (kind, str(path), line_number, _hash(raw))
        if marker in seen:
            return
        seen.add(marker)
        sensitive.append({
            "kind": kind,
            **_location(root, path, line_number, json_key),
            "value_sha256": _hash(raw),
            "redacted_preview": _redacted(raw),
        })

    for root in roots:
        paths = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.casefold() in TEXT_SUFFIXES)
        for path in paths:
            if path.suffix.casefold() not in TEXT_SUFFIXES:
                continue
            files_scanned += 1
            bytes_scanned += path.stat().st_size
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), 1):
                for match in IPV4_RE.finditer(line):
                    raw = match.group(0)
                    kind = _classify_ip(raw)
                    if kind == "public_ip":
                        informational[kind] += 1
                    elif kind:
                        add(kind, raw, root, path, line_number)
                for match in IPV6_RE.finditer(line):
                    raw = match.group(0)
                    kind = _classify_ip(raw)
                    if kind == "public_ip":
                        informational[kind] += 1
                    elif kind:
                        add(kind, raw, root, path, line_number)
                for match in MAC_RE.finditer(line):
                    add("mac_address", match.group(0), root, path, line_number)
                for match in INTERNAL_HOST_RE.finditer(line):
                    add("internal_hostname", match.group(0), root, path, line_number)
                for match in URL_RE.finditer(line):
                    raw = match.group(0).rstrip(".,);]")
                    parsed = urlparse(raw)
                    if parsed.hostname:
                        public_hosts[parsed.hostname.casefold()] += 1
                    if parsed.username or parsed.password:
                        user = parsed.username or ""
                        password = parsed.password or ""
                        if PLACEHOLDER_RE.search(user) or PLACEHOLDER_RE.search(password):
                            informational["credential_placeholder_url"] += 1
                        else:
                            add("credential_bearing_url", raw, root, path, line_number)
                    if re.search(r"(?i)[?&]X-Amz-(?:Credential|Signature|Security-Token)=", raw):
                        if re.search(r"(?i)[?&]X-Amz-(?:Credential|Signature|Security-Token)=(?:(?:%5B|\[)?REDACTED)", raw):
                            informational["redacted_presigned_url"] += 1
                        else:
                            add("aws_presigned_url", raw, root, path, line_number)
                for pattern_name, pattern in SECRET_PATTERNS.items():
                    for match in pattern.finditer(line):
                        raw = match.group(1) if pattern_name == "assigned_secret" and match.lastindex else match.group(0)
                        if PLACEHOLDER_RE.search(raw):
                            informational["credential_placeholder"] += 1
                        else:
                            add(pattern_name, raw, root, path, line_number)

                if path.suffix.casefold() in {".json", ".jsonl"} and line.strip():
                    try:
                        parsed_json = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    for key_path, value in _walk_json(parsed_json):
                        key = re.split(r"\.|\[", key_path)[-1].rstrip("]")
                        if NETWORK_KEYS.fullmatch(key) and value not in (None, "", [], {}):
                            raw = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
                            ip_kind = _classify_ip(raw) if isinstance(value, str) else None
                            if ip_kind == "public_ip":
                                informational["public_ip_network_field"] += 1
                            elif ip_kind:
                                add(ip_kind + "_network_field", raw, root, path, line_number, key_path)
                            elif key.casefold() in {"hostname", "host_name", "server_address", "ssh_host", "snmp_community", "mac", "mac_address", "gateway", "subnet", "netmask", "dns", "dns_server"}:
                                add("sensitive_network_field", raw, root, path, line_number, key_path)

    sensitive.sort(key=lambda item: (item["path"], item.get("line", 0), item["kind"]))
    return {
        "schema_version": "1.0",
        "audited_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "roots": [str(root) for root in roots],
        "files_scanned": files_scanned,
        "bytes_scanned": bytes_scanned,
        "sensitive_finding_count": len(sensitive),
        "sensitive_findings_by_kind": dict(sorted(Counter(item["kind"] for item in sensitive).items())),
        "sensitive_findings": sensitive,
        "informational_counts": dict(sorted(informational.items())),
        "public_host_count": len(public_hosts),
        "public_hosts": [{"host": host, "occurrences": count} for host, count in public_hosts.most_common()],
        "policy": {
            "retained": "Public provenance and live-tool URLs plus documented credential placeholders.",
            "findings": "Private/link-local/loopback addresses, MACs, internal hostnames, credential-bearing URLs, plausible embedded secrets, and sensitive network configuration fields.",
        },
        "passed": len(sensitive) == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "files_scanned", "bytes_scanned", "sensitive_finding_count", "sensitive_findings_by_kind", "informational_counts", "public_host_count")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
