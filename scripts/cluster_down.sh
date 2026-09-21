#!/usr/bin/env bash
# Tear down is k3d cluster delete. Do not helm-uninstall in place.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib.sh"
k3d_bin cluster delete "$CLUSTER_NAME" 2>/dev/null || true
rm -f /tmp/ba-cluster-up
echo "cluster down"
