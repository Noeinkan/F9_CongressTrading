#!/usr/bin/env bash
# Ask the SearchForAlpha lab container to write today's research digest.
#
# The lab reads this repo's SQLite and F8's DuckDB; it does not ingest filings.
# Called at the end of scripts/nightly_ingest.sh, after tonight's disclosures
# are in the database. A missing container or a docker permission problem is
# logged and does not fail the night — the ingest already succeeded.
#
# nightly_ingest.sh drops to `deploy`, which is not in the docker group. It is
# allowed exactly one command through sudo, by /etc/sudoers.d/f9-alpha-flow:
#
#   deploy ALL=(root) NOPASSWD: /usr/bin/docker exec site-alpha-lab-web python -m lib.alpha_flow
#
# sudo matches the arguments literally, so CMD must stay word-for-word the
# same as that rule. As root, or as a docker-group user, plain docker is used.

set -uo pipefail

CMD=(/usr/bin/docker exec site-alpha-lab-web python -m lib.alpha_flow)

if [ "$(id -u)" -eq 0 ] || docker info >/dev/null 2>&1; then
  RUN=("${CMD[@]}")
else
  RUN=(sudo -n "${CMD[@]}")
fi

echo "alpha-flow: ${RUN[*]}"
if ! "${RUN[@]}"; then
  echo "alpha-flow: digest not run (lab container down, or /etc/sudoers.d/f9-alpha-flow missing)"
fi
exit 0
