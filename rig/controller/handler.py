"""kopf operator: TaskDeclaration → SPIRE entry + CiliumNetworkPolicy."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import kopf
import kubernetes

from controller.cnp import TASK_LABEL, render_cnp, render_pod_spire_entry, render_spire_entry, spiffe_for
from controller.gateway import apply_gateway_routes
from identity.svid import parse_entry_ids

API = "bounded-autonomy.io"
KIND = "taskdeclarations"
PROP_LOG = Path(os.environ.get("BA_PROPAGATION_LOG", "/var/log/ba-propagation.jsonl"))


def _api() -> kubernetes.client.CustomObjectsApi:
    try:
        kubernetes.config.load_incluster_config()
    except kubernetes.config.ConfigException:
        kubernetes.config.load_kube_config()
    return kubernetes.client.CustomObjectsApi()


def _core() -> kubernetes.client.CoreV1Api:
    try:
        kubernetes.config.load_incluster_config()
    except kubernetes.config.ConfigException:
        kubernetes.config.load_kube_config()
    return kubernetes.client.CoreV1Api()


def _apply_cnp(body: dict) -> None:
    api = _api()
    ns = body["metadata"]["namespace"]
    name = body["metadata"]["name"]
    try:
        api.get_namespaced_custom_object(
            "cilium.io", "v2", ns, "ciliumnetworkpolicies", name
        )
        api.replace_namespaced_custom_object(
            "cilium.io", "v2", ns, "ciliumnetworkpolicies", name, body
        )
    except kubernetes.client.exceptions.ApiException as exc:
        if exc.status != 404:
            raise
        api.create_namespaced_custom_object(
            "cilium.io", "v2", ns, "ciliumnetworkpolicies", body
        )


def _delete_cnps(task_id: str, namespace: str) -> None:
    api = _api()
    existing = api.list_namespaced_custom_object(
        "cilium.io",
        "v2",
        namespace,
        "ciliumnetworkpolicies",
        label_selector=f"bounded-autonomy.io/task-id={task_id}",
    )
    for item in existing.get("items", []):
        api.delete_namespaced_custom_object(
            "cilium.io",
            "v2",
            namespace,
            "ciliumnetworkpolicies",
            item["metadata"]["name"],
        )


def _label_workload(task_id: str, namespace: str) -> None:
    core = _core()
    pods = core.list_namespaced_pod(
        namespace, label_selector="app.kubernetes.io/name=agent"
    )
    for pod in pods.items:
        body = {
            "metadata": {
                "labels": {TASK_LABEL: task_id},
                "annotations": {TASK_LABEL: task_id},
            }
        }
        core.patch_namespaced_pod(pod.metadata.name, namespace, body)


SPIRE_SOCKET = "/run/spire/sockets/server.sock"


def _spire_exec(cmd: list[str]) -> str:
    ns = os.environ.get("BA_SPIRE_NAMESPACE", "spire")
    try:
        from kubernetes.stream import stream

        core = _core()
        pods = core.list_namespaced_pod(
            ns, label_selector="app.kubernetes.io/name=spire-server"
        )
        if not pods.items:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            return (proc.stdout or "") + (proc.stderr or "")
        return stream(
            core.connect_get_namespaced_pod_exec,
            pods.items[0].metadata.name,
            ns,
            command=cmd,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            container="spire-server",
        ) or ""
    except Exception:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        return (proc.stdout or "") + (proc.stderr or "")


def _spire_create(entry: dict) -> None:
    cmd = [
        "/opt/spire/bin/spire-server",
        "entry",
        "create",
        "-socketPath",
        SPIRE_SOCKET,
        "-spiffeID",
        entry["spiffe_id"],
        "-parentID",
        entry["parent_id"],
        "-x509SVIDTTL",
        str(entry["x509_svid_ttl"]),
        "-jwtSVIDTTL",
        str(entry["jwt_svid_ttl"]),
    ]
    for sel in entry["selectors"]:
        cmd.extend(["-selector", sel])
    _spire_exec(cmd)


def _spire_entry(spec: dict) -> None:
    if os.environ.get("BA_SKIP_SPIRE") == "1":
        return
    parent = os.environ.get(
        "BA_SPIRE_PARENT",
        "spiffe://rig/spire/agent/k8s_psat/bounded-autonomy/k3d-bounded-autonomy-server-0",
    )
    _spire_create(render_pod_spire_entry(parent, spec.get("namespace", "rig")))
    _spire_create(render_spire_entry(spec, parent))


def _spire_delete_entry(spiffe_id: str) -> None:
    """Remove the registration entry at task end. Not SVID revocation."""
    if os.environ.get("BA_SKIP_SPIRE") == "1":
        return
    shown = _spire_exec(
        [
            "/opt/spire/bin/spire-server",
            "entry",
            "show",
            "-socketPath",
            SPIRE_SOCKET,
            "-spiffeID",
            spiffe_id,
        ]
    )
    for entry_id in parse_entry_ids(shown):
        _spire_exec(
            [
                "/opt/spire/bin/spire-server",
                "entry",
                "delete",
                "-socketPath",
                SPIRE_SOCKET,
                "-entryID",
                entry_id,
            ]
        )


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_: object) -> None:
    settings.persistence.finalizer = "bounded-autonomy.io/segment-controller"
    settings.scanning.disabled = True


@kopf.on.create(API, "v1", KIND)
@kopf.on.update(API, "v1", KIND)
def reconcile(spec: dict, name: str, namespace: str, logger: kopf.Logger, **_: object) -> dict:
    t0 = datetime.now(timezone.utc)
    task_id = spec["taskId"]
    _label_workload(task_id, namespace)
    if spec.get("segmentEnabled", True):
        rendered = render_cnp(name, namespace, spec)
        _apply_cnp(rendered["egress"])
        for ingress in rendered["ingress"]:
            _apply_cnp(ingress)
        _spire_entry({**spec, "namespace": namespace})
    try:
        apply_gateway_routes(spec)
        logger.info("APISIX uri-blocker applied for %s", task_id)
    except Exception as exc:
        logger.warning("APISIX allow-list update skipped: %s", exc)
    if not spec.get("segmentEnabled", True):
        t1 = datetime.now(timezone.utc)
        record = {
            "task_id": task_id,
            "crd_event_at": t0.isoformat(),
            "applied_at": t1.isoformat(),
            "propagation_ms": (t1 - t0).total_seconds() * 1000,
            "spiffe_id": spiffe_for(task_id),
            "segment": False,
        }
        PROP_LOG.parent.mkdir(parents=True, exist_ok=True)
        with PROP_LOG.open("a") as fh:
            fh.write(json.dumps(record) + "\n")
        logger.info("gateway allow-list only for %s", task_id)
        return record
    t1 = datetime.now(timezone.utc)
    record = {
        "task_id": task_id,
        "crd_event_at": t0.isoformat(),
        "applied_at": t1.isoformat(),
        "propagation_ms": (t1 - t0).total_seconds() * 1000,
        "spiffe_id": spiffe_for(task_id),
    }
    PROP_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PROP_LOG.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    logger.info("segment applied for %s", task_id)
    return record


@kopf.on.delete(API, "v1", KIND)
def teardown(spec: dict, namespace: str, logger: kopf.Logger, **_: object) -> None:
    task_id = spec["taskId"]
    _delete_cnps(task_id, namespace)
    _spire_delete_entry(spiffe_for(task_id))
    logger.info("segment and registration entry deleted for %s", task_id)


@kopf.timer(API, "v1", KIND, interval=5.0)
def expire(spec: dict, name: str, namespace: str, **_: object) -> None:
    ttl = int(spec.get("expectedDurationSeconds") or 0)
    created = spec.get("createdAt")
    if not ttl or not created:
        return
    started = datetime.fromisoformat(created.replace("Z", "+00:00"))
    if (datetime.now(timezone.utc) - started).total_seconds() < ttl:
        return
    api = _api()
    api.delete_namespaced_custom_object(
        API, "v1", namespace, KIND, name
    )
