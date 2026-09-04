"""Tests for DAX Pattern & Complexity Analyzer."""

import pytest
from analyzers.dax_pattern_analyzer import DAXPatternAnalyzer


def test_simple_dax_complexity():
    dax = "SUM(Sales[Amount])"
    metrics = DAXPatternAnalyzer.analyze_complexity(dax)
    assert metrics.function_count == 1
    assert metrics.calculate_count == 0
    assert metrics.filter_count == 0
    assert metrics.iterator_count == 0
    assert metrics.var_count == 0
    assert metrics.nesting_depth == 1
    assert metrics.referenced_columns == 1
    assert metrics.complexity_score > 0


def test_complex_dax_complexity():
    dax = """
    VAR SalesTotal = SUM(Sales[Amount])
    VAR PriorYearSales = CALCULATE(
        SUM(Sales[Amount]),
        SAMEPERIODLASTYEAR('Date'[Date])
    )
    VAR Growth = DIVIDE(SalesTotal - PriorYearSales, PriorYearSales, 0)
    RETURN
        IF(
            ISBLANK(SalesTotal),
            0,
            Growth
        )
    """
    metrics = DAXPatternAnalyzer.analyze_complexity(dax)
    assert metrics.var_count == 3
    assert metrics.calculate_count == 1
    assert metrics.function_count >= 5
    assert metrics.nesting_depth >= 2
    assert metrics.line_count >= 5
    assert metrics.referenced_columns >= 2


def test_iterator_and_filter_counting():
    dax = """
    CALCULATE(
        SUMX(
            FILTER(Sales, Sales[Quantity] > 10),
            Sales[Quantity] * Sales[UnitPrice]
        ),
        USERELATIONSHIP(Sales[OrderDate], 'Date'[Date])
    )
    """
    metrics = DAXPatternAnalyzer.analyze_complexity(dax)
    assert metrics.calculate_count == 1
    assert metrics.filter_count == 1
    assert metrics.iterator_count >= 2  # SUMX and FILTER
    assert metrics.nesting_depth >= 3

