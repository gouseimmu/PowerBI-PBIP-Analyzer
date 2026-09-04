"""Tests for Static DAX Quality Analyzer and Safe Suggestion Generator."""

import pytest
from analyzers.dax_quality_analyzer import DAXQualityAnalyzer


def test_division_safety_rule():
    dax = "SUM(Sales[Profit]) / SUM(Sales[Revenue])"
    issues, highest = DAXQualityAnalyzer.analyze_expression("Measure", "Sales", "ProfitMargin", dax)

    assert any("DIVIDE" in i.issue or "Division" in i.issue for i in issues)
    div_issue = next(i for i in issues if "Division" in i.issue)
    assert div_issue.suggested_dax == "DIVIDE(SUM(Sales[Profit]), SUM(Sales[Revenue]), 0)"
    assert div_issue.validation_status == "Validated"
    assert highest in ["Low", "Medium"]


def test_redundant_calculate_rule():
    dax = "CALCULATE(SUM(Sales[Amount]))"
    issues, highest = DAXQualityAnalyzer.analyze_expression("Measure", "Sales", "TotalSales", dax)

    assert any("Redundant CALCULATE" in i.issue for i in issues)
    calc_issue = next(i for i in issues if "Redundant CALCULATE" in i.issue)
    assert calc_issue.suggested_dax == "SUM(Sales[Amount])"
    assert calc_issue.validation_status == "Validated"


def test_filter_over_table_rule():
    dax = 'CALCULATE(SUM(Sales[Amount]), FILTER(Sales, Sales[Status] = "Active"))'
    issues, highest = DAXQualityAnalyzer.analyze_expression("Measure", "Sales", "ActiveSales", dax)

    assert any("FILTER() used over entire table" in i.issue for i in issues)
    f_issue = next(i for i in issues if "FILTER() used over entire table" in i.issue)
    assert f_issue.category == "Performance"
    assert f_issue.severity == "Medium"
    assert f_issue.validation_status == "Needs Review"


def test_repeated_expressions_without_var():
    dax = "DIVIDE([Sales YTD] - [Sales LY], [Sales LY], 0)"
    issues, highest = DAXQualityAnalyzer.analyze_expression("Measure", "Sales", "SalesGrowth", dax)

    assert any("Repeated reference" in i.issue for i in issues)
    rep_issue = next(i for i in issues if "Repeated reference" in i.issue)
    assert "Sales LY" in rep_issue.issue


def test_iterator_review_rule():
    dax = "SUMX(Sales, Sales[Quantity] * Sales[Price])"
    issues, highest = DAXQualityAnalyzer.analyze_expression("Measure", "Sales", "TotalRevenue", dax)

    assert any("Iterator function SUMX" in i.issue for i in issues)
    it_issue = next(i for i in issues if "SUMX" in i.issue)
    assert it_issue.severity == "Informational"


def test_deep_nesting_rule():
    dax = "IF(A > 1, IF(B > 2, IF(C > 3, IF(D > 4, 1, 0), 0), 0), 0)"
    issues, highest = DAXQualityAnalyzer.analyze_expression("Measure", "Sales", "DeepNested", dax)

    assert any("Deep nesting" in i.issue for i in issues)
    nest_issue = next(i for i in issues if "Deep nesting" in i.issue)
    assert nest_issue.category == "Maintainability"

