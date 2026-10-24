#!/bin/bash
# Keeps the two newest versions of the app on R2 and deletes the rest, both
# the archive (legend-lore/v<version>/) and latest/, where each publish adds
# its files beside the old ones. version.json and anything outside
# legend-lore/ are left alone.
#
# publish-release.yml runs it after each publish; prune-r2.yml runs it by
# hand. `--dryrun` prints what it would delete. Needs the env those
# workflows set: R2_BUCKET, R2_ENDPOINT and the AWS_* keys.
set -euo pipefail

KEEP=2
DRYRUN=""
if [ "${1:-}" = "--dryrun" ]; then DRYRUN="--dryrun"; fi

r2() { aws "$@" --endpoint-url "$R2_ENDPOINT"; }

VERSIONS=$(r2 s3api list-objects-v2 --bucket "$R2_BUCKET" --prefix legend-lore/v --delimiter / \
  --query 'CommonPrefixes[].Prefix' --output text \
  | tr '\t' '\n' | sed -n 's#^legend-lore/v\([0-9][0-9.]*\)/$#\1#p' | sort -V)
KEPT=$(echo "$VERSIONS" | tail -n "$KEEP")
if [ -z "$KEPT" ]; then
  echo "No versions found under legend-lore/v*/; nothing to prune."
  exit 0
fi
echo "Versions on R2: $(echo $VERSIONS)"
echo "Keeping: $(echo $KEPT)"

kept() { echo "$KEPT" | grep -qxF "$1"; }

for v in $VERSIONS; do
  if ! kept "$v"; then
    r2 s3 rm "s3://$R2_BUCKET/legend-lore/v$v/" --recursive $DRYRUN
  fi
done

for key in $(r2 s3api list-objects-v2 --bucket "$R2_BUCKET" --prefix legend-lore/latest/ \
  --query 'Contents[].Key' --output text | tr '\t' '\n'); do
  v=$(echo "$key" | sed -n 's#^legend-lore/latest/Legend-Lore-\([0-9][0-9.]*\)-.*$#\1#p')
  if [ -n "$v" ] && ! kept "$v"; then
    r2 s3 rm "s3://$R2_BUCKET/$key" $DRYRUN
  fi
done
