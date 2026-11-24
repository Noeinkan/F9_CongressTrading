#!/usr/bin/env bash
# Ask the SearchForAlpha lab container to write today's research digest.
#
# The lab reads this repo's SQLite and F8's DuckDB; it does not ingest filings.
# Called at the end of scripts/nightly_ingest.sh, after tonight's disclosures
# are in the database. A missing container or a docker permission problem is
# logged and does not fail the night — the ingest already succeeded.
#
# ALPHA_FLOW_CONTAINER overrides the container name (default site-alpha-lab-web).

set -euo pipefail

CONTAINER="${ALPHA_FLOW_CONTAINER:-site-alpha-lab-web}"

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  DOCKER=(sudo -n docker)
else
  echo "alpha-flow: docker is not available to $(id -un); digest not run"
  exit 0
fi

if ! "${DOCKER[@]}" ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "alpha-flow: container ${CONTAINER} is not running; digest not run"
  exit 0
fi

echo "alpha-flow: python -m lib.alpha_flow in ${CONTAINER}"
"${DOCKER[@]}" exec "$CONTAINER" python -m lib.alpha_flow
