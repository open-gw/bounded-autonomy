"""Render CiliumNetworkPolicy objects from a TaskDeclaration spec."""

from __future__ import annotations

from typing import Any, Iterable

# Kubernetes label values cannot hold a SPIFFE ID. The controller writes this
# label on the workload pod (no restart) so SPIRE and Cilium can select it.
# Paper 1 CNP matches the label only; Cilium mTLS is Paper 2.
TASK_LABEL = "bounded-autonomy.io/task-id"
SERVICE_PORTS = {
    "records": "8081",
    "docs": "8082",
    "search": "8083",
    "notify": "8084",
    "billing": "8085",
    "analytics": "8086",
    "audit": "8087",
    "catalog": "8088",
}


def spiffe_for(task_id: str) -> str:
    return f"spiffe://rig/task/{task_id}"


def render_cnp(
    name: str,
    namespace: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    task_id = spec["taskId"]
    services: Iterable[dict[str, str] | str] = spec["services"]
    service_names = [
        s["name"] if isinstance(s, dict) else s for s in services
    ]
    egress = [
        {
            "toEndpoints": [
                {
                    "matchLabels": {
                        "app.kubernetes.io/name": svc,
                        "app.kubernetes.io/part-of": "bounded-autonomy",
                    }
                }
            ],
            "toPorts": [
                {"ports": [{"port": SERVICE_PORTS.get(svc, "80"), "protocol": "TCP"}]}
            ],
        }
        for svc in service_names
    ]
    egress.append(
        {
            "toEndpoints": [
                {
                    "matchLabels": {
                        "app.kubernetes.io/name": "otel-collector",
                        "k8s:io.kubernetes.pod.namespace": "rig",
                    }
                }
            ],
            "toPorts": [{"ports": [{"port": "4318", "protocol": "TCP"}]}],
        }
    )
    # DNS (no Cilium DNS-proxy rules: those hijack 53 and blackhole if the
    # proxy is not ready). SPIRE uses a local agent socket, not this path.
    egress.append(
        {
            "toEndpoints": [
                {
                    "matchLabels": {
                        "k8s:io.kubernetes.pod.namespace": "kube-system",
                        "k8s:k8s-app": "kube-dns",
                    }
                }
            ],
            "toPorts": [
                {"ports": [{"port": "53", "protocol": "UDP"}]},
                {"ports": [{"port": "53", "protocol": "TCP"}]},
            ],
        }
    )
    ingress_for_services = [
        {
            "apiVersion": "cilium.io/v2",
            "kind": "CiliumNetworkPolicy",
            "metadata": {
                "name": f"{name}-ingress-{svc}",
                "namespace": namespace,
                "labels": {
                    "bounded-autonomy.io/task-id": task_id,
                    "bounded-autonomy.io/role": "ingress",
                },
            },
            "spec": {
                "endpointSelector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": svc,
                        "app.kubernetes.io/part-of": "bounded-autonomy",
                    }
                },
                # Selecting the service isolates its ingress to the task-id
                # allow-list. Namespace-wide default-deny is agent-only so
                # tool servers can still reach Postgres/MinIO/Qdrant.
                "enableDefaultDeny": {"ingress": True},
                "ingress": [
                    {
                        "fromEndpoints": [
                            {"matchLabels": {TASK_LABEL: task_id}}
                        ],
                    }
                ],
            },
        }
        for svc in service_names
    ]
    egress_cnp = {
        "apiVersion": "cilium.io/v2",
        "kind": "CiliumNetworkPolicy",
        "metadata": {
            "name": f"{name}-egress",
            "namespace": namespace,
            "labels": {
                "bounded-autonomy.io/task-id": task_id,
                "bounded-autonomy.io/role": "egress",
            },
        },
        "spec": {
            "description": f"segment for {spiffe_for(task_id)}",
            "endpointSelector": {"matchLabels": {TASK_LABEL: task_id}},
            "egress": egress,
        },
    }
    return {"egress": egress_cnp, "ingress": ingress_for_services}


def render_spire_entry(spec: dict[str, Any], parent_id: str) -> dict[str, Any]:
    task_id = spec["taskId"]
    ttl = int(spec["expectedDurationSeconds"])
    return {
        "spiffe_id": spiffe_for(task_id),
        "parent_id": parent_id,
        "selectors": [
            f"k8s:ns:{spec.get('namespace', 'rig')}",
            f"k8s:pod-label:{TASK_LABEL}:{task_id}",
        ],
        "x509_svid_ttl": ttl,
        "jwt_svid_ttl": ttl,
    }
