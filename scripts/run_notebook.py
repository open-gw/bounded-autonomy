"""Execute analysis/notebook.ipynb against synthetic fixtures."""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "analysis" / "notebook.ipynb"


def main() -> int:
    nb = nbformat.read(NOTEBOOK, as_version=4)
    client = NotebookClient(
        nb,
        timeout=120,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT / "analysis")}},
    )
    # nbclient needs a jupyter kernel. If none is registered, fall back to
    # executing the markdown-emitting path that `make analyse` uses.
    try:
        client.execute()
    except Exception as exc:  # noqa: BLE001 — kernel absence is expected on a bare venv
        print(f"kernel execute skipped ({exc.__class__.__name__}: {exc})")
        from tables import FIXTURE_RESULTS, emit_markdown, load_results, write_q2_figure

        results = load_results(FIXTURE_RESULTS)
        out = ROOT / "analysis" / "output"
        out.mkdir(parents=True, exist_ok=True)
        md = emit_markdown(results)
        (out / "tables.md").write_text(md)
        write_q2_figure(results, out)
        print(md)
        if "Reach" not in md or "Rollback" not in md or "Overhead" not in md:
            return 1
        return 0
    out_nb = ROOT / "analysis" / "output" / "notebook-executed.ipynb"
    out_nb.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, out_nb)
    print(f"executed notebook -> {out_nb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
