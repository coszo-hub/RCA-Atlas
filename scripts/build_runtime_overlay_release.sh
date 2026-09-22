#!/bin/sh
set -eu

# Build a supplemental runtime release.  It is restored after --base-release
# by bootstrap_machine.sh, avoiding duplicate uploads of the stable corpus.

base_release=${1:?Usage: build_runtime_overlay_release.sh BASE_RELEASE [OUTPUT_DIR]}
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output_dir=${2:-"$project_root/transfer_dist"}
cache="$project_root/runtime_data/Literature/full_text_cache"

command -v zstd >/dev/null 2>&1 || { echo "zstd is required" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }
test -d "$cache" || { echo "Missing $cache" >&2; exit 1; }

mkdir -p "$output_dir"
archive="$output_dir/rca-literature-fulltext-$(date -u +%Y%m%d).tar.zst"
export COPYFILE_DISABLE=1
cd "$project_root"
tar --exclude='.DS_Store' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='.env' --exclude='.env.*' -cf - runtime_data/Literature/full_text_cache |
  zstd -T0 -10 -f -o "$archive"

python3 - "$base_release" "$archive" "$output_dir/release-manifest.json" <<'PY'
import hashlib,json,pathlib,sys
from datetime import datetime,timezone
base, archive, manifest_path=sys.argv[1:]
path=pathlib.Path(archive)
digest=hashlib.sha256()
with path.open("rb") as stream:
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
manifest={
  "schema_version":"1.1-overlay", "created_at_utc":datetime.now(timezone.utc).isoformat(),
  "base_release":base, "assets":[{"name":path.name,"bytes":path.stat().st_size,"sha256":digest.hexdigest()}],
  "restore_root":".",
}
pathlib.Path(manifest_path).write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
print(json.dumps(manifest,indent=2))
PY

echo "Overlay release assets are ready in $output_dir"
