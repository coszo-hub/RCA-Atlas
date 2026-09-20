#!/bin/sh
set -eu

release=latest
repo=${GITHUB_REPOSITORY:-}
download_dir=.artifacts

while [ "$#" -gt 0 ]; do
  case "$1" in
    --release) release=$2; shift 2 ;;
    --repo) repo=$2; shift 2 ;;
    --download-dir) download_dir=$2; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

command -v gh >/dev/null 2>&1 || { echo "GitHub CLI (gh) is required" >&2; exit 1; }
command -v zstd >/dev/null 2>&1 || { echo "zstd is required" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }

if [ -z "$repo" ]; then
  remote=$(git remote get-url origin 2>/dev/null || true)
  repo=$(printf '%s' "$remote" | sed -E 's#^git@github.com:##; s#^https://github.com/##; s#\.git$##')
fi
test -n "$repo" || { echo "Pass --repo OWNER/REPO or configure origin" >&2; exit 1; }

mkdir -p "$download_dir"
if [ "$release" = latest ]; then
  gh release download --repo "$repo" --dir "$download_dir" --pattern 'release-manifest.json' --clobber
else
  gh release download "$release" --repo "$repo" --dir "$download_dir" --pattern 'release-manifest.json' --clobber
fi

python3 - "$download_dir/release-manifest.json" <<'PY' > "$download_dir/asset-names.txt"
import json,sys
for row in json.load(open(sys.argv[1]))["assets"]:
    print(row["name"])
PY

while IFS= read -r asset; do
  if [ "$release" = latest ]; then
    gh release download --repo "$repo" --dir "$download_dir" --pattern "$asset" --clobber
  else
    gh release download "$release" --repo "$repo" --dir "$download_dir" --pattern "$asset" --clobber
  fi
done < "$download_dir/asset-names.txt"

python3 - "$download_dir/release-manifest.json" "$download_dir" <<'PY'
import hashlib,json,pathlib,sys
manifest=json.load(open(sys.argv[1]))
root=pathlib.Path(sys.argv[2])
for row in manifest["assets"]:
    path=root/row["name"]
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != row["sha256"] or path.stat().st_size != row["bytes"]:
        raise SystemExit(f"Integrity check failed for {path.name}")
    print(f"verified {path.name}")
PY

while IFS= read -r asset; do
  echo "Restoring $asset"
  zstd -dc "$download_dir/$asset" | tar -xf -
done < "$download_dir/asset-names.txt"

echo "Restore complete. Review src/graphrag_runtime/README.md to start PostgreSQL and the API."

