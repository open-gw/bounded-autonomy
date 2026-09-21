"""Install pinned CLIs into .tools/. Idempotent."""

from __future__ import annotations

import os
import platform
import stat
import tarfile
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".tools"
PINS = yaml.safe_load((ROOT / "rig" / "versions.yaml").read_text())


def _arch() -> tuple[str, str]:
    sys = platform.system().lower()
    mach = platform.machine().lower()
    goarch = {"x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}[mach]
    return sys, goarch


def _chmod_x(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"fetch {url}")
    urllib.request.urlretrieve(url, dest)


def main() -> int:
    TOOLS.mkdir(exist_ok=True)
    sys, arch = _arch()
    k3d = PINS["cluster"]["k3d"]
    k3d_bin = TOOLS / "k3d"
    if not k3d_bin.exists():
        url = f"https://github.com/k3d-io/k3d/releases/download/{k3d}/k3d-{sys}-{arch}"
        _download(url, k3d_bin)
        _chmod_x(k3d_bin)
    print(f"tools in {TOOLS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
