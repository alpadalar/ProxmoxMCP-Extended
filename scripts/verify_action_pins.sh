#!/usr/bin/env bash
# Verify that every `uses: owner/repo@<sha> # vX.Y.Z` pin in .github/workflows/*.yml
# points at the commit the tag resolves to on GitHub.
# Read-only: only GET requests through `gh api` are made (no POST, no --method, no writes).
set -u

cd "$(dirname "$0")/.."

status=0
seen=0
while IFS= read -r line; do
  # line looks like: path:NN:      - uses: owner/repo@sha # vX.Y.Z
  spec="$(sed -E 's/^.*uses:[[:space:]]*([^[:space:]]+)[[:space:]]+#[[:space:]]*(v[^[:space:]]+).*$/\1 \2/' <<<"$line")"
  ref="${spec%% *}"
  tag="${spec##* }"
  repo="${ref%@*}"
  sha="${ref#*@}"
  seen=$((seen + 1))

  info="$(gh api "repos/${repo}/git/ref/tags/${tag}" --jq '.object.type + " " + .object.sha' 2>&1)" || {
    echo "MISMATCH ${repo}@${tag}: cannot resolve tag (${info})"
    status=1
    continue
  }
  type="${info%% *}"
  resolved="${info##* }"
  if [ "$type" = "tag" ]; then
    resolved="$(gh api "repos/${repo}/git/tags/${resolved}" --jq .object.sha 2>&1)" || {
      echo "MISMATCH ${repo}@${tag}: cannot dereference annotated tag"
      status=1
      continue
    }
  fi
  if [ "$resolved" = "$sha" ]; then
    echo "OK       ${repo}@${tag} -> ${sha} (${type})"
  else
    echo "MISMATCH ${repo}@${tag}: pinned ${sha}, tag resolves to ${resolved}"
    status=1
  fi
done < <(grep -h -E '^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]*[^.][^[:space:]]*@[0-9a-f]{40}[[:space:]]+#' .github/workflows/*.yml | sort -u)

if [ "$seen" -eq 0 ]; then
  echo "no pinned actions found" >&2
  exit 1
fi
exit "$status"
