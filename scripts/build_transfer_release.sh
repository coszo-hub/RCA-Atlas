#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output_dir=${1:-"$project_root/transfer_dist"}
catalog="$project_root/runtime_data/GraphRAG/corpus_catalog.json"

command -v zstd >/dev/null 2>&1 || { echo "zstd is required" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }
test -f "$catalog" || { echo "Missing $catalog" >&2; exit 1; }

fingerprint=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["build_fingerprint_sha256"])' "$catalog")
short_fingerprint=$(printf '%s' "$fingerprint" | cut -c1-12)
mkdir -p "$output_dir"

export COPYFILE_DISABLE=1
cd "$project_root"

make_archive() {
  archive_name=$1
  shift
  destination="$output_dir/${archive_name}-${short_fingerprint}.tar.zst"
  echo "Building $(basename "$destination")"
  tar --exclude='.DS_Store' --exclude='__pycache__' --exclude='*.pyc' \
      --exclude='.env' --exclude='.env.*' \
      --exclude='runtime_data/Literature/full_text_cache' \
      --exclude='runtime_data/FreeLLMAPI/data' \
      --exclude='runtime_data/**/__pycache__' -cf - "$@" |
    zstd -T0 -10 -f -o "$destination"
}

make_archive rca-corpus-data data
make_archive rca-source-material source_material \
  src/literature_pipeline/provenance \
  src/literature_pipeline/archive \
  src/arcada_pipeline/source_snapshot
make_archive rca-runtime-data runtime_data

python3 - "$output_dir" "$fingerprint" <<'PY'
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

root = pathlib.Path(sys.argv[1])
fingerprint = sys.argv[2]
assets = []
for path in sorted(root.glob("rca-*.tar.zst")):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    assets.append({"name": path.name, "bytes": path.stat().st_size, "sha256": digest.hexdigest()})
manifest = {
    "schema_version": "1.0",
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "catalog_fingerprint_sha256": fingerprint,
    "assets": assets,
    "restore_root": ".",
}
(root / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps(manifest, indent=2))
PY

echo "Release assets are ready in $output_dir"
