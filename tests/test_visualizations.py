"""Guard evidence, denominator weighting, full/demo scope, and shipped exports."""

import copy
import hashlib
import json
import sqlite3
import struct
from pathlib import Path

import pandas as pd
import pytest

from scdi.visualizations import (
    FIGURES,
    availability_bands,
    load_chart_data,
    pareto_products,
    reconcile_findings,
)

ROOT = Path(__file__).resolve().parents[1]


def test_pareto_is_stable_and_includes_the_threshold_crossing_product():
    products = pd.DataFrame({"product_id": [5, 2, 8], "normalized_sales": [4.0, 4.0, 2.0]})
    result = pareto_products(products)
    assert result["product_id"].tolist() == [2, 5, 8]
    assert result["rank"].tolist() == [1, 2, 3]
    assert result["cumulative_share"].tolist() == pytest.approx([0.4, 0.8, 1.0])
    assert result.loc[result["cumulative_share"].ge(0.8), "rank"].iloc[0] == 2


def test_zero_sales_exposure_bands_use_counts_not_an_average_of_rates():
    hours = pd.DataFrame(
        {
            "stockout_hours": [0, 1, 4, 16],
            "observed_days": [50, 100, 1, 10],
            "zero_sales_days": [2, 1, 1, 8],
        }
    )
    bands = availability_bands(hours)
    partial = bands.loc[bands["stockout_hours_band"].eq("1–4")].iloc[0]
    assert partial["observed_days"] == 101
    assert partial["zero_sales_rate"] == pytest.approx(2 / 101)
    assert bands["observed_days"].sum() == hours["observed_days"].sum()
    assert bands["zero_sales_days"].sum() == hours["zero_sales_days"].sum()
    assert bands.iloc[-1]["zero_sales_rate"] == 0.8


def test_demo_subset_is_rejected_before_building_full_data_figures(tmp_path):
    database = tmp_path / "demo.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE metadata (key TEXT, value TEXT)")
        db.execute("INSERT INTO metadata VALUES ('scope', 'demo')")
    with pytest.raises(ValueError, match="demo subset"):
        load_chart_data(database, {})


def test_published_visualizations_match_analysis_scope_and_export_hashes():
    findings_path = ROOT / "docs/evidence/findings.json"
    findings = json.loads(findings_path.read_text())
    manifest = json.loads((ROOT / "docs/evidence/visualizations.json").read_text())
    reconcile_findings(manifest["metrics"], findings)
    assert manifest["findings_sha256"] == hashlib.sha256(findings_path.read_bytes()).hexdigest()
    assert set(manifest["charts"]) == set(FIGURES)
    assert manifest["charts"]["historical-demand-stockouts"]["data_rows"] == 97
    assert manifest["charts"]["product-pareto"]["data_rows"] == 865
    assert manifest["charts"]["forecast-comparison"]["data_rows"] == 5
    assert manifest["charts"]["stockout-risk-matrix"]["data_rows"] == 50_000
    assert manifest["charts"]["stockout-risk-matrix"]["sampled"] is False
    assert manifest["source"]["license"] == "CC BY 4.0"
    for chart in manifest["charts"].values():
        for kind, export in chart["files"].items():
            content = (ROOT / "docs/assets" / export["filename"]).read_bytes()
            assert hashlib.sha256(content).hexdigest() == export["sha256"]
            if kind == "png":
                assert content[:8] == b"\x89PNG\r\n\x1a\n"
                assert list(struct.unpack(">II", content[16:24])) == chart["png_dimensions"]


def test_reconciliation_refuses_a_changed_holdout_comparison():
    findings = json.loads((ROOT / "docs/evidence/findings.json").read_text())
    manifest = json.loads((ROOT / "docs/evidence/visualizations.json").read_text())
    mutated = copy.deepcopy(manifest["metrics"])
    mutated["forecast"]["ses_alpha0.3"]["wape"] = 0.374
    with pytest.raises(ValueError, match="ses_alpha0.3 wape"):
        reconcile_findings(mutated, findings)
