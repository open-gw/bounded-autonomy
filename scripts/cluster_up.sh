#!/usr/bin/env bash
# Bring up the Paper 1 cluster. Pins: rig/versions.yaml
# Always delete first. Never helm-uninstall Cilium into a leftover k3d cluster.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib.sh"
install_tools

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

echo "deleting k3d cluster ${CLUSTER_NAME} if present"
k3d_bin cluster delete "$CLUSTER_NAME" 2>/dev/null || true
rm -f /tmp/ba-cluster-up

CFG="$ROOT/rig/cluster/k3d.yaml"
CLEANUP_CFG=""
# Host volume binds in k3d.yaml are not safe as written:
# - Darwin has no bpffs; bind-mounting /sys/fs/bpf hides the in-node mount.
# - Linux cgroup v2 (nsdelegate) + Docker cgroupns=private: bind-mounting
#   host /sys/fs/cgroup makes kubelet write cgroup.procs under kubepods/
#   that do not exist on the host hierarchy (FailedCreatePodSandBox).
# Always rewrite: drop cgroup; drop bpf on Darwin. bpf is mounted inside
# the node below when the host bind is absent.
CFG="$(mktemp)"
CLEANUP_CFG="$CFG"
"$PYTHON" - "$ROOT/rig/cluster/k3d.yaml" "$CFG" <<'PY'
import platform, sys, yaml
doc = yaml.safe_load(open(sys.argv[1]))
if platform.system() == "Darwin":
    doc.pop("volumes", None)
else:
    vols = [
        v
        for v in (doc.get("volumes") or [])
        if "/sys/fs/cgroup" not in str(v.get("volume", ""))
    ]
    if vols:
        doc["volumes"] = vols
    else:
        doc.pop("volumes", None)
yaml.safe_dump(doc, open(sys.argv[2], "w"), sort_keys=False)
PY

k3d_bin cluster create --config "$CFG" --wait
if [[ -n "$CLEANUP_CFG" ]]; then
  rm -f "$CLEANUP_CFG"
fi

echo "sharing bpf and cgroup mounts on ${NODE_NAME}"
docker exec "$NODE_NAME" sh -c 'mountpoint -q /sys/fs/bpf || mount -t bpf bpffs /sys/fs/bpf'
docker exec "$NODE_NAME" mount --make-shared /sys/fs/bpf
docker exec "$NODE_NAME" mount --make-shared /sys/fs/cgroup

k3d_bin kubeconfig merge "$CLUSTER_NAME" --kubeconfig-merge-default --kubeconfig-switch-context

helm_bin repo add cilium https://helm.cilium.io --force-update
helm_bin repo update cilium

# Do not helm --wait: Hubble relay needs CoreDNS, CoreDNS needs the CNI.
# Gate on cilium status, then CoreDNS, then the rest.
echo "installing Cilium ${CILIUM_CHART} (kube-proxy replacement, no bundled SPIRE)"
helm_bin upgrade --install cilium cilium/cilium \
  --version "$CILIUM_CHART" \
  --namespace kube-system \
  --values "$ROOT/rig/cluster/cilium-values.yaml"

echo "waiting for Cilium datapath"
# --wait includes Hubble relay, which needs CoreDNS, which needs the CNI.
# Wait for the agent first, then CoreDNS, then the full status (Hubble included).
kubectl_bin -n kube-system rollout status ds/cilium --timeout=300s
kubectl_bin -n kube-system rollout status deploy/cilium-operator --timeout=180s
echo "waiting for CoreDNS"
kubectl_bin -n kube-system rollout status deploy/coredns --timeout=180s
cilium_bin status --wait --wait-duration 5m --interactive=false
echo "DATAPATH_READY cilium green and CoreDNS Ready"

kubectl_bin apply -f "$ROOT/rig/cluster/namespace.yaml"
kubectl_bin apply -f "$ROOT/rig/controller/crd.yaml"
kubectl_bin apply -f "$ROOT/rig/identity/spire.yaml"
kubectl_bin -n spire rollout status deploy/spire-server --timeout=180s
kubectl_bin -n spire rollout status ds/spire-agent --timeout=180s
kubectl_bin apply -f "$ROOT/rig/stores/manifests.yaml"
kubectl_bin apply -f "$ROOT/rig/telemetry/manifests.yaml"
kubectl_bin apply -f "$ROOT/rig/lineage/marquez.yaml"

docker build -t ba-runtime:paper1 -f "$ROOT/rig/images/Dockerfile" "$ROOT"
k3d_bin image import ba-runtime:paper1 -c "$CLUSTER_NAME"
kubectl_bin apply -f "$ROOT/rig/cluster/services.yaml"
kubectl_bin apply -f "$ROOT/rig/controller/deploy.yaml"
touch /tmp/ba-cluster-up
echo "cluster up. next: make run PROFILE=long-multistep MODE=full SEED=1"
