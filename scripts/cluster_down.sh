#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib.sh"
k3d_bin cluster delete bounded-autonomy || true
rm -f /tmp/ba-cluster-up
echo "cluster down"
