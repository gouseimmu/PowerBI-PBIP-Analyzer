"""Comprehensive unit tests for Power BI AI Governance Platform features."""

import pytest
from analyzers.dax_dependency_analyzer import ModelCatalog, DAXDependencyAnalyzer
from analyzers.object_usage_analyzer import ObjectUsageAnalyzer
from analyzers.visual_usage_analyzer import VisualUsageAnalyzer, DirectVisualUsage
from analyzers.model_health_analyzer import ModelHealthAnalyzer
from ai.dax_optimizer import DAXOptimizer
from ai.provider import NullAIProvider
from ai.response_parser import AIResponseParser


def test_usage_classification_4_states():
    """Verify Direct, Indirect, Direct + Indirect, and Unused classification."""
    tables = [{"Table Name": "Sales"}]
    columns = [
        {"Table Name": "Sales", "Column Name": "Amount", "Column Type": "Data"},
        {"Table Name": "Sales", "Column Name": "Cost", "Column Type": "Data"},
    ]
    measures = [
        {"Table": "Sales", "Measure Name": "Total Sales", "DAX Expression": "SUM(Sales[Amount])"},
        {"Table": "Sales", "Measure Name": "Total Cost", "DAX Expression": "SUM(Sales[Cost])"},
        {"Table": "Sales", "Measure Name": "Profit", "DAX Expression": "[Total Sales] - [Total Cost]"},
        {"Table": "Sales", "Measure Name": "Unused Measure", "DAX Expression": "100"},
    ]
    calc_cols = []

    catalog = ModelCatalog(tables, columns, measures, calc_cols)
    dax_analyzer = DAXDependencyAnalyzer(catalog, measures, calc_cols)

    # Visual references [Total Sales] directly, and also [Profit] directly (which references [Total Sales] indirectly)
    direct_usages = [
        DirectVisualUsage("p1", "Overview", "v1", "Card 1", "Card", "KPI 1", "Measure", "Sales", "Total Sales", canonical_id="MEASURE:Sales[Total Sales]"),
        DirectVisualUsage("p1", "Overview", "v2", "Card 2", "Card", "KPI 2", "Measure", "Sales", "Profit", canonical_id="MEASURE:Sales[Profit]"),
    ]

    class DummyVisualAnalyzer:
        def get_visual_metrics(self):
            return {}

    usage_analyzer = ObjectUsageAnalyzer(
        catalog=catalog,
        direct_usages=direct_usages,
        dax_analyzer=dax_analyzer,
        visual_analyzer=DummyVisualAnalyzer(),
        tables=tables,
        columns=columns,
        measures=measures,
        calc_columns=calc_cols,
    )

    usage_list = usage_analyzer.get_object_usage()
    usage_map = {item["Object Name"]: item["Usage Type"] for item in usage_list}

    # Total Sales is directly referenced by v1, AND indirectly referenced by v2 -> Profit -> Total Sales
    assert usage_map["Total Sales"] == "Direct + Indirect"
    # Profit is directly referenced by v2, but not indirectly referenced by anything -> Direct
    assert usage_map["Profit"] == "Direct"
    # Total Cost is indirectly referenced by v2 -> Profit -> Total Cost -> Indirect
    assert usage_map["Total Cost"] == "Indirect"
    # Unused Measure is neither -> Unused
    assert usage_map["Unused Measure"] == "Unused"


def test_model_health_score_calculation():
    """Verify deterministic model health score calculation."""
    metadata = {
        "tables": [{"Table Name": "Sales"}],
        "columns": [{"Table Name": "Sales", "Column Name": "Col1"}],
        "measures": [{"Table": "Sales", "Measure Name": "M1"}],
        "calculated_columns": [],
        "relationships": [
            {"From Table": "Sales", "From Column": "ID", "To Table": "Dim", "To Column": "ID", "Cardinality": "M:M", "Filter Direction": "Both"}
        ],
        "object_usage": [{"Object Type": "Measure", "Table": "Sales", "Object Name": "M1", "Used": "Yes"}],
        "phase2_summary": {
            "Circular Dependencies": 1,
            "Unresolved DAX References": 2,
            "Unused Objects": 0,
        },
        "dax_analysis": [],
    }

    health = ModelHealthAnalyzer.calculate_health_score(metadata)
    assert health["score"] < 100
    assert len(health["deductions"]) >= 2
    assert any("Circular Dependencies" in d["title"] for d in health["deductions"])


def test_ai_response_validation():
    """Verify AI response parser rejects fake/invalid model entity names."""
    tables = [{"Table Name": "Sales"}]
    columns = [{"Table Name": "Sales", "Column Name": "Revenue"}]
    measures = [{"Table": "Sales", "Measure Name": "Total Sales"}]
    catalog = ModelCatalog(tables, columns, measures, [])

    # AI response referencing non-existent table "FakeTable"
    ai_raw = {
        "has_improvement": True,
        "category": "Performance",
        "severity": "High",
        "issue": "Optimize sales calculation",
        "recommendation": "Use FakeTable",
        "suggested_dax": "SUM('FakeTable'[NonExistentColumn])",
    }

    issue = AIResponseParser.parse_and_validate(ai_raw, catalog, "Sales")
    assert issue is not None
    assert issue.validation_status == "Invalid"
