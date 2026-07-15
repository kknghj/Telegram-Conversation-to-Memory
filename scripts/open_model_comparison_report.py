"""Open a generated comparison.html in the default browser (does not start a server)."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="run_id or absolute path to run directory")
    args = parser.parse_args(argv)

    run = Path(args.run)
    if not run.is_absolute():
        run = ROOT / "reports" / "model_comparison" / args.run
    html_path = run / "comparison.html" if run.is_dir() else run
    if not html_path.exists():
        print(f"not found: {html_path}", file=sys.stderr)
        return 1
    webbrowser.open(html_path.resolve().as_uri())
    print(f"opened={html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
