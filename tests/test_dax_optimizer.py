"""Tests for DAXOptimizer orchestrator (static + AI, caching, and fallback)."""

import pytest
from ai.dax_optimizer import DAXOptimizer
from ai.provider import DAXAIProvider, NullAIProvider
from analyzers.dax_dependency_analyzer import ModelCatalog


class MockAIProvider(DAXAIProvider):
    """Mock AI provider that counts requests to test caching."""
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.request_count = 0

    @property
    def provider_name(self) -> str:
        return "MockAIProvider"

    def is_available(self) -> bool:
        return True

    def analyze_dax(self, context):
        self.request_count += 1
        if self.should_fail:
            raise RuntimeError("Simulated AI network failure")
        return {
            "has_improvement": True,
            "category": "Performance",
            "severity": "High",
            "issue": "Mock AI Optimization",
            "explanation": "Mock explanation",
            "recommendation": "Mock recommendation",
            "suggested_dax": "SUM(Sales[Amount])",
            "confidence": "High",
            "requires_manual_validation": True,
        }


def test_dax_optimizer_static_only():
    tables = [{"Table Name": "Sales"}]
    columns = [{"Table Name": "Sales", "Column Name": "Amount"}]
    measures = [
        {"Table": "Sales", "Measure Name": "SimpleSales", "DAX Expression": "SUM(Sales[Amount])"},
        {"Table": "Sales", "Measure Name": "RedundantSales", "DAX Expression": "CALCULATE(SUM(Sales[Amount]))"},
    ]
    catalog = ModelCatalog(tables, columns, measures, [])

    optimizer = DAXOptimizer(
        catalog=catalog,
        measures=measures,
        calc_columns=[],
        object_usage_map={},
        ai_provider=NullAIProvider(),
    )

    analysis_data = optimizer.get_analysis_sheet_data()
    assert len(analysis_data) == 2

    improvements = optimizer.get_improvements_sheet_data()
    assert len(improvements) >= 1
    assert any("Redundant CALCULATE" in imp["Issue"] for imp in improvements)

    complexity_data = optimizer.get_complexity_sheet_data()
    assert len(complexity_data) == 2


def test_dax_optimizer_with_caching():
    tables = [{"Table Name": "Sales"}]
    columns = [{"Table Name": "Sales", "Column Name": "Amount"}]
    # 2 measures with the exact same DAX to test caching
    measures = [
        {"Table": "Sales", "Measure Name": "M1", "DAX Expression": "SUM(Sales[Amount])"},
        {"Table": "Sales", "Measure Name": "M1", "DAX Expression": "SUM(Sales[Amount])"},
    ]
    catalog = ModelCatalog(tables, columns, measures, [])
    mock_ai = MockAIProvider()

    optimizer = DAXOptimizer(
        catalog=catalog,
        measures=measures,
        calc_columns=[],
        object_usage_map={},
        ai_provider=mock_ai,
    )

    # Second identical call should hit the cache
    assert mock_ai.request_count == 1
    metrics = optimizer.get_phase3_summary_metrics()
    assert metrics["AI Suggestions"] == 2


def test_dax_optimizer_ai_failure_fallback():
    tables = [{"Table Name": "Sales"}]
    columns = [{"Table Name": "Sales", "Column Name": "Amount"}]
    measures = [
        {"Table": "Sales", "Measure Name": "Redundant", "DAX Expression": "CALCULATE(SUM(Sales[Amount]))"},
    ]
    catalog = ModelCatalog(tables, columns, measures, [])
    failing_ai = MockAIProvider(should_fail=True)

    optimizer = DAXOptimizer(
        catalog=catalog,
        measures=measures,
        calc_columns=[],
        object_usage_map={},
        ai_provider=failing_ai,
    )

    # Static analysis must still succeed
    improvements = optimizer.get_improvements_sheet_data()
    assert len(improvements) >= 1
    assert any("Redundant CALCULATE" in imp["Issue"] for imp in improvements)
    metrics = optimizer.get_phase3_summary_metrics()
    assert metrics["AI Failures"] == 1

