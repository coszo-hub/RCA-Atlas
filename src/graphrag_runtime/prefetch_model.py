#!/usr/bin/env python3
"""Fetch and verify the pinned FastEmbed model for later offline use."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
from pathlib import Path

from build_embeddings import (
    FASTEMBED_VERSION,
    MODEL_NAME,
    MODEL_REVISION,
    MODEL_SHA256,
    MODEL_SOURCE_REPOSITORY,
    sha256_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    os.environ.pop("HF_HUB_OFFLINE", None)
    try:
        from fastembed import TextEmbedding
    except ImportError:
        print(f"error: install fastembed=={FASTEMBED_VERSION}", file=sys.stderr)
        return 2
    installed_version = importlib.metadata.version("fastembed")
    if installed_version != FASTEMBED_VERSION:
        print(f"error: fastembed {installed_version} != {FASTEMBED_VERSION}", file=sys.stderr)
        return 2
    # FastEmbed establishes its expected cache layout. Hash verification below
    # rejects silently changed upstream artifacts.
    TextEmbedding(model_name=MODEL_NAME, cache_dir=str(args.cache_dir), threads=args.threads)
    candidates = list(args.cache_dir.rglob("model_optimized.onnx"))
    matches = [path for path in candidates if sha256_file(path) == MODEL_SHA256]
    if len(matches) != 1:
        print(f"error: expected one model with SHA-256 {MODEL_SHA256}, found {len(matches)}", file=sys.stderr)
        return 2
    result = {
        "model_name": MODEL_NAME,
        "model_source_repository": MODEL_SOURCE_REPOSITORY,
        "model_revision": MODEL_REVISION,
        "model_sha256": MODEL_SHA256,
        "model_path": str(matches[0].resolve()),
        "fastembed_version": FASTEMBED_VERSION,
        "verified": True,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
