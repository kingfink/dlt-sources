#!/usr/bin/env bash
set -euo pipefail

# Cut a GitHub release for the current commit and attach the built Python
# distributions. Run from a clean checkout of the commit you want to release,
# normally master after the release PR has merged.
#
# Usage: scripts/release.sh vX.Y.Z

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

tag="${1:-}"
if [[ -z "$tag" ]]; then
  echo "Usage: scripts/release.sh <tag>   (e.g. scripts/release.sh v0.2.0)" >&2
  exit 1
fi

if [[ ! "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Tag must look like vX.Y.Z (got: $tag)" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found. Install it: https://cli.github.com/" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty. Commit or stash changes before releasing." >&2
  exit 1
fi

echo "Verifying release metadata..."
python3 scripts/release_metadata.py verify "$tag"

echo "Building Python distributions..."
uv build

release_assets=(dist/*.tar.gz dist/*.whl)
if [[ ! -e "${release_assets[0]}" ]]; then
  echo "No release assets found in dist/." >&2
  exit 1
fi

echo "Creating GitHub release $tag with Python distributions attached..."
if gh release view "$tag" >/dev/null 2>&1; then
  echo "Release $tag already exists; refreshing distribution assets."
  gh release upload "$tag" "${release_assets[@]}" --clobber
else
  gh release create "$tag" \
    "${release_assets[@]}" \
    --title "tailor-made-dlt-sources $tag" \
    --generate-notes \
    --target "$(git rev-parse HEAD)"
fi

echo "Done. Release $tag published with dist/ artifacts attached."
