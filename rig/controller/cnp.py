"""Render CiliumNetworkPolicy objects from a TaskDeclaration spec."""

from __future__ import annotations

from typing import Any, Iterable

from controller.declaration import declared_names
from identity.svid import POD_SPIFFE_ID, POD_X509_SVID_TTL_SECONDS, jwt_ttl_seconds
from modes import GATEWAY_LABEL, GATEWAY_NS

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
# nginx placeholders listen on 80; Services are 8085–8088. Cilium toPorts
# is evaluated after DNAT, so both the Service port and the pod port
# must be listed or |R| stops at the three real tools.
PLACEHOLDER_SERVICES = frozenset({"billing", "analytics", "audit", "catalog"})


def ports_for(svc: str) -> list[dict[str, str]]:
    service_port = SERVICE_PORTS.get(svc, "80")
    ports = [{"port": service_port, "protocol": "TCP"}]
    if svc in PLACEHOLDER_SERVICES and service_port != "80":
        ports.append({"port": "80", "protocol": "TCP"})
    return ports


def spiffe_for(task_id: str) -> str:
    return f"spiffe://rig/task/{task_id}"


def dns_allow_names(service_names: Iterable[str], extra: Iterable[str] = ("otel-collector",)) -> list[str]:
    """FQDN + search-path variants CoreDNS and the stub resolver emit.

    Restricted to declared tool services plus the collector the agent
    already has an L4 allow for. Undeclared inventory names, kubernetes,
    and the public Internet are not listed. Paper claim: DNS is CoreDNS
    for declared names only.
    """
    names: list[str] = []
    seen: set[str] = set()
    for svc in [*service_names, *extra]:
        for candidate in (
            svc,
            f"{svc}.rig",
            f"{svc}.rig.svc",
            f"{svc}.rig.svc.cluster.local",
        ):
            if candidate not in seen:
                seen.add(candidate)
                names.append(candidate)
    return names


def render_cnp(
    name: str,
    namespace: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    task_id = spec["taskId"]
    service_names = declared_names(spec)
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
            "toPorts": [{"ports": ports_for(svc)}],
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
    # APISIX is the L7 hop in gateway-only and full. full + bypass still
    # allows the gateway so the allow-list can be live while the agent
    # talks ClusterIP (the undeclared call is then a CNP drop, not a 403).
    egress.append(
        {
            "toEndpoints": [
                {
                    "matchLabels": {
                        "app.kubernetes.io/name": GATEWAY_LABEL,
                        "k8s:io.kubernetes.pod.namespace": GATEWAY_NS,
                    }
                }
            ],
            "toPorts": [{"ports": [{"port": "9080", "protocol": "TCP"}]}],
        }
    )
    # DNS: CoreDNS only, declared names (plus otel-collector). Cilium
    # DNS-proxy matchName — Task 16 used L4-only after the proxy blackholed
    # lookups; this restore is required so undeclared FQDNs are refused.
    # SPIRE uses a local agent socket, not this path.
    dns_rules = [{"matchName": n} for n in dns_allow_names(service_names)]
    for fqdn in (
        "apisix-gateway",
        "apisix-gateway.apisix",
        "apisix-gateway.apisix.svc",
        "apisix-gateway.apisix.svc.cluster.local",
    ):
        dns_rules.append({"matchName": fqdn})
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
                {
                    "ports": [{"port": "53", "protocol": "ANY"}],
                    "rules": {"dns": dns_rules},
                }
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
                            {"matchLabels": {TASK_LABEL: task_id}},
                            {
                                "matchLabels": {
                                    "app.kubernetes.io/name": GATEWAY_LABEL,
                                    "k8s:io.kubernetes.pod.namespace": GATEWAY_NS,
                                }
                            },
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
            "enableDefaultDeny": {"egress": True},
            "egress": egress,
            # reserved:host / kube-apiserver are not covered by default-deny
            # alone on this datapath; API ClusterIP and kubelet rows need an
            # explicit deny (display rows 6a/6b and 7).
            "egressDeny": [
                {
                    "toEntities": [
                        "world",
                        "host",
                        "remote-node",
                        "kube-apiserver",
                    ]
                }
            ],
        },
    }
    return {"egress": egress_cnp, "ingress": ingress_for_services}


def render_spire_entry(spec: dict[str, Any], parent_id: str) -> dict[str, Any]:
    """Task registration: JWT-SVID TTL from the declaration; X.509 is pod-level."""
    task_id = spec["taskId"]
    return {
        "spiffe_id": spiffe_for(task_id),
        "parent_id": parent_id,
        "selectors": [
            f"k8s:ns:{spec.get('namespace', 'rig')}",
            f"k8s:pod-label:{TASK_LABEL}:{task_id}",
        ],
        "x509_svid_ttl": POD_X509_SVID_TTL_SECONDS,
        "jwt_svid_ttl": jwt_ttl_seconds(spec),
    }


def render_pod_spire_entry(parent_id: str, namespace: str = "rig") -> dict[str, Any]:
    """X.509 workload identity for the agent pod. Not a task credential."""
    return {
        "spiffe_id": POD_SPIFFE_ID,
        "parent_id": parent_id,
        "selectors": [
            f"k8s:ns:{namespace}",
            "k8s:pod-label:app.kubernetes.io/name:agent",
        ],
        "x509_svid_ttl": POD_X509_SVID_TTL_SECONDS,
        "jwt_svid_ttl": POD_X509_SVID_TTL_SECONDS,
    }
