# Shared helpers for cluster scripts. Versions from rig/versions.yaml via python.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="${ROOT}/.tools"
mkdir -p "$TOOLS"
export PATH="${TOOLS}:${PATH}"

read_pin() {
  python3 - "$ROOT/rig/versions.yaml" "$1" <<'PY'
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1]))
path = sys.argv[2].split(".")
cur = doc
for p in path:
    cur = cur[p]
print(cur)
PY
}

CILIUM_CHART="$(read_pin cluster.cilium_cli >/dev/null; read_pin cni.cilium_chart)"
K3D_VER="$(read_pin cluster.k3d)"
CILIUM_CLI="$(read_pin cluster.cilium_cli)"
HELM_VER="$(read_pin cluster.helm)"
KUBECTL_VER="$(read_pin cluster.kubectl)"
HUBBLE_VER="$(read_pin cluster.hubble_cli)"

k3d_bin() { command -v k3d >/dev/null && k3d "$@" || "${TOOLS}/k3d" "$@"; }
helm_bin() { command -v helm >/dev/null && helm "$@" || "${TOOLS}/helm" "$@"; }
kubectl_bin() { command -v kubectl >/dev/null && kubectl "$@" || "${TOOLS}/kubectl" "$@"; }
cilium_bin() { command -v cilium >/dev/null && cilium "$@" || "${TOOLS}/cilium" "$@"; }

install_tools() {
  python3 "$ROOT/scripts/install_tools.py"
}
