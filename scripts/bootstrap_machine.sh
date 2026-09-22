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

base_release=$(python3 - "$download_dir/release-manifest.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1])).get("base_release", ""))
PY
)

if [ -n "$base_release" ]; then
  mkdir -p "$download_dir/base-release"
  gh release download "$base_release" --repo "$repo" --dir "$download_dir/base-release" --pattern 'release-manifest.json' --clobber
  nested_base=$(python3 - "$download_dir/base-release/release-manifest.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1])).get("base_release", ""))
PY
)
  test -z "$nested_base" || { echo "Nested base_release is not supported" >&2; exit 1; }
fi

python3 - "$release" "$download_dir/release-manifest.json" "$base_release" "${download_dir}/base-release/release-manifest.json" <<'PY' > "$download_dir/assets.tsv"
import json,pathlib,sys
release,manifest_path,base_release,base_manifest_path=sys.argv[1:]
def emit(tag, path):
    for row in json.load(open(path))["assets"]:
        print("\t".join((tag, row["name"], row["sha256"], str(row["bytes"]))))
if base_release:
    emit(base_release, base_manifest_path)
emit(release, manifest_path)
PY

while IFS="$(printf '\t')" read -r asset_release asset sha256 bytes; do
  if [ "$asset_release" = latest ]; then
    gh release download --repo "$repo" --dir "$download_dir" --pattern "$asset" --clobber
  else
    gh release download "$asset_release" --repo "$repo" --dir "$download_dir" --pattern "$asset" --clobber
  fi
  actual_sha256=$(sha256sum "$download_dir/$asset" | awk '{print $1}')
  actual_bytes=$(wc -c < "$download_dir/$asset" | tr -d ' ')
  test "$actual_sha256" = "$sha256" && test "$actual_bytes" = "$bytes" || {
    echo "Integrity check failed for $asset" >&2; exit 1;
  }
  echo "verified $asset"
done < "$download_dir/assets.tsv"

while IFS="$(printf '\t')" read -r asset_release asset sha256 bytes; do
  echo "Restoring $asset"
  zstd -dc "$download_dir/$asset" | tar -xf -
done < "$download_dir/assets.tsv"

echo "Restore complete. Review src/graphrag_runtime/README.md to start PostgreSQL and the API."
