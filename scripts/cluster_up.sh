#!/usr/bin/env bash
# Bring up the Paper 1 cluster. Pins: rig/versions.yaml
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib.sh"
install_tools
k3d_bin cluster create --config "$ROOT/rig/cluster/k3d.yaml" --wait
helm_bin repo add cilium https://helm.cilium.io --force-update
helm_bin repo update cilium
# k3s API address for Cilium's kubeProxyReplacement
API_HOST="$(kubectl_bin get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')"
helm_bin upgrade --install cilium cilium/cilium \
  --version "$CILIUM_CHART" \
  --namespace kube-system \
  --values "$ROOT/rig/cluster/cilium-values.yaml" \
  --set "k8sServiceHost=${API_HOST}" \
  --wait --timeout 10m
cilium_bin status --wait
kubectl_bin apply -f "$ROOT/rig/cluster/namespace.yaml"
kubectl_bin apply -f "$ROOT/rig/controller/crd.yaml"
kubectl_bin apply -f "$ROOT/rig/stores/manifests.yaml"
kubectl_bin apply -f "$ROOT/rig/telemetry/manifests.yaml"
kubectl_bin apply -f "$ROOT/rig/lineage/marquez.yaml"
# Runtime image for tools/controller/agent. k3d import after docker build.
docker build -t ba-runtime:paper1 -f "$ROOT/rig/images/Dockerfile" "$ROOT"
k3d_bin image import ba-runtime:paper1 -c bounded-autonomy
kubectl_bin apply -f "$ROOT/rig/cluster/services.yaml"
kubectl_bin apply -f "$ROOT/rig/controller/deploy.yaml"
kubectl_bin apply -f "$ROOT/rig/observer/probe-job.yaml"
touch /tmp/ba-cluster-up
echo "cluster up. next: make run PROFILE=long-multistep MODE=full SEED=1"
