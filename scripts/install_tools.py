"""Install pinned CLIs into .tools/. Idempotent. Pins: rig/versions.yaml."""

from __future__ import annotations

import io
import platform
import stat
import tarfile
import urllib.request
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".tools"
PINS = yaml.safe_load((ROOT / "rig" / "versions.yaml").read_text())


def _arch() -> tuple[str, str]:
    sys = platform.system().lower()  # darwin | linux
    mach = platform.machine().lower()
    goarch = {"x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}[mach]
    return sys, goarch


def _chmod_x(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _fetch(url: str) -> bytes:
    print(f"fetch {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def _install_binary(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_fetch(url))
    _chmod_x(dest)


def _install_from_tarball(url: str, member_suffix: str, dest: Path) -> None:
    data = _fetch(url)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
        matching = [m for m in tar.getmembers() if m.isfile() and m.name.endswith(member_suffix)]
        if not matching:
            names = [m.name for m in tar.getmembers()[:20]]
            raise FileNotFoundError(f"no {member_suffix} in {url}; saw {names}")
        src = tar.extractfile(matching[0])
        assert src is not None
        dest.write_bytes(src.read())
    _chmod_x(dest)


def main() -> int:
    TOOLS.mkdir(exist_ok=True)
    sys, arch = _arch()
    cluster = PINS["cluster"]

    k3d = TOOLS / "k3d"
    if not k3d.exists():
        _install_binary(
            f"https://github.com/k3d-io/k3d/releases/download/{cluster['k3d']}/k3d-{sys}-{arch}",
            k3d,
        )

    helm = TOOLS / "helm"
    if not helm.exists():
        ver = cluster["helm"]  # v3.17.2
        _install_from_tarball(
            f"https://get.helm.sh/helm-{ver}-{sys}-{arch}.tar.gz",
            "/helm",
            helm,
        )

    kubectl = TOOLS / "kubectl"
    if not kubectl.exists():
        ver = cluster["kubectl"]
        _install_binary(
            f"https://dl.k8s.io/release/{ver}/bin/{sys}/{arch}/kubectl",
            kubectl,
        )

    cilium = TOOLS / "cilium"
    if not cilium.exists():
        ver = cluster["cilium_cli"]
        _install_from_tarball(
            f"https://github.com/cilium/cilium-cli/releases/download/{ver}/cilium-{sys}-{arch}.tar.gz",
            "cilium",
            cilium,
        )

    hubble = TOOLS / "hubble"
    if not hubble.exists():
        ver = cluster["hubble_cli"]
        _install_from_tarball(
            f"https://github.com/cilium/hubble/releases/download/{ver}/hubble-{sys}-{arch}.tar.gz",
            "hubble",
            hubble,
        )

    print(f"tools in {TOOLS}: {', '.join(p.name for p in sorted(TOOLS.iterdir()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
