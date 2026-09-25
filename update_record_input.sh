#!/usr/bin/env bash
set -euo pipefail

repo_path=.input/3ll3d00d/beqfilters
repo_url=${BEQCATALOGUE_FILTER_REPO_URL:-https://github.com/3ll3d00d/beqfilters.git}
mkdir -p "$(dirname "$repo_path")"
if [[ -d "$repo_path/.git" ]]; then
    git -C "$repo_path" pull --ff-only
elif [[ -e "$repo_path" ]]; then
    echo "Refusing to replace non-git path $repo_path" >&2
    exit 1
else
    git clone "$repo_url" "$repo_path"
fi
