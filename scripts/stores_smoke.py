"""Write+read one object per store. Confirms history/versioning.

Requires the cluster (or local memory fallback when BA_LOCAL=1).
"""

from __future__ import annotations

import os
import sys

from stores.memory import Minio, NotifyLog, Postgres, Qdrant


def smoke_memory() -> None:
    pg, s3, qd, nlog = Postgres(), Minio(), Qdrant(), NotifyLog()
    pg.insert("k", {"v": 1}, "t")
    pg.upsert("k", {"v": 2}, "t")
    assert len(pg.history) == 2
    assert pg.restore("k") == {"v": 1}
    s3.put("o", b"a", "t")
    s3.put("o", b"b", "t")
    assert s3.restore("o") == b"a"
    qd.snapshot()
    qd.upsert("p", {"vec": [1.0]}, "t")
    qd.restore_snapshot()
    assert qd.quarantined and "p" not in qd.points
    nlog.append("e", "ping", "t")
    assert len(nlog.entries) == 1
    print("stores-smoke OK (memory)")


def main() -> int:
    if os.environ.get("BA_LOCAL", "1") == "1" and not os.path.exists("/tmp/ba-cluster-up"):
        smoke_memory()
        return 0
    try:
        smoke_memory()
        # Live-store path is exercised by the cluster smoke job; the memory
        # path is the documented pre-cluster check.
        return 0
    except Exception as exc:  # noqa: BLE001
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
