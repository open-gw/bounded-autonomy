# Task 15 — k3d datapath (replaces cluster part of Task 03)

## Built

- `make down` is `k3d cluster delete bounded-autonomy` (plus the local `/tmp/ba-cluster-up` sentinel). No Helm uninstall in place.
- `make up` starts with the same delete, ignoring “not found”, then creates the cluster with flannel, kube-proxy, network-policy, and Traefik off.
- bpf and cgroup are bind-mounted on Linux and `mount --make-shared` inside the node before Cilium installs.
- Cilium values: `kubeProxyReplacement: true`, `k8sServiceHost: k3d-bounded-autonomy-server-0`, Hubble + relay. No `authentication.mutual.spire`.
- Gates: Cilium agent DS, then CoreDNS, then `cilium status --wait` (Hubble needs DNS). Helm `--wait` is not used.
- CNI binaries install to `/opt/cni/bin` (k3s 1.32 kubelet path). `cni.binPath: /bin` is wrong on this k3s and leaves CoreDNS in ContainerCreating.
- `socketLB.hostNamespaceOnly: true` so ClusterIP works from pods on Docker Desktop cgroup v2.
- Standalone SPIRE in `rig/identity/spire.yaml` (trust domain `rig`, emptyDir, k8s_psat). Generated CNPs match `bounded-autonomy.io/task-id` only.

## Acceptance (2026-09-21, this machine)

Two consecutive `make up` with no manual steps:

| Pass | UTC | `cilium status` | CoreDNS | `make up` |
| --- | --- | --- | --- | --- |
| 1 | 13:48:34Z | Cilium/Operator/Envoy/Hubble Relay OK | 1/1 Running | 0 |
| 2 | 13:53:20Z | same | 1/1 Running | 0 |

Pass 2 started with `k3d cluster delete` of pass 1. SPIRE server and agent Ready on both.

## Deviations

- Cluster name stays `bounded-autonomy` (manifests, k3d.yaml), not the illustrative `ba`.
- On Darwin/Docker Desktop the host has no bpffs, so `cluster_up.sh` strips the k3d volume binds and mounts bpf inside the node. Linux keeps the specced host binds.
- Cilium mTLS (`authentication.mode: required`) is not emitted. Paper 1 attribution is the task-id label bound to the task SVID. Mutual TLS moves to Paper 2.

## Manuscript impact

Replace “task-id label with mutual TLS” with “task-id label bound to the task's SVID”. Do not claim Cilium mutual authentication in Paper 1.
