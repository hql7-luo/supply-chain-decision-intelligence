"""Generate five portfolio charts from the verified full analysis database."""

from __future__ import annotations

import argparse
from pathlib import Path

from scdi.visualizations import build_visualizations

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=ROOT / "data/processed/decision_intelligence.sqlite"
    )
    parser.add_argument("--findings", type=Path, default=ROOT / "docs/evidence/findings.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets")
    parser.add_argument("--manifest", type=Path, default=ROOT / "docs/evidence/visualizations.json")
    args = parser.parse_args()
    result = build_visualizations(args.database, args.findings, args.output, args.manifest)
    print(f"Generated {len(result['charts'])} full-data PNG/SVG figures; all metrics reconcile.")


if __name__ == "__main__":
    main()
