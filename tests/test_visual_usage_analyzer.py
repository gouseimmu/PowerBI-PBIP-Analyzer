"""Tests for Visual Usage Analyzer (PBIR and legacy visual field reference extraction)."""

import pytest
from analyzers.dax_dependency_analyzer import ModelCatalog
from analyzers.visual_usage_analyzer import VisualUsageAnalyzer


def test_visual_usage_pbir_extraction():
    tables = [{"Table Name": "Sales"}, {"Table Name": "Date"}]
    columns = [
        {"Table Name": "Sales", "Column Name": "Amount"},
        {"Table Name": "Date", "Column Name": "Date"},
    ]
    measures = [{"Table": "Sales", "Measure Name": "Total Sales"}]
    calc_columns = []

    catalog = ModelCatalog(tables, columns, measures, calc_columns)

    pages = [{"Page ID": "p1", "Page Name": "Overview"}]
    visuals = [
        {
            "Page ID": "p1",
            "Page Name": "Overview",
            "Visual ID": "v1",
            "Visual Name": "Card1",
            "Visual Type": "card",
            "Visual Title": "Sales KPI",
            "raw_data": {
                "query": {
                    "queryState": {
                        "Values": {
                            "projections": [
                                {
                                    "field": {
                                        "Measure": {
                                            "Expression": {"SourceRef": {"Entity": "Sales"}},
                                            "Property": "Total Sales"
                                        }
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        },
        {
            "Page ID": "p1",
            "Page Name": "Overview",
            "Visual ID": "v2",
            "Visual Name": "Chart1",
            "Visual Type": "lineChart",
            "Visual Title": "None",
            "raw_data": {
                "query": {
                    "queryState": {
                        "Category": {
                            "projections": [{"queryRef": "Date.Date"}]
                        },
                        "Y": {
                            "projections": [{"queryRef": "Sales.Amount"}]
                        }
                    }
                }
            }
        }
    ]

    analyzer = VisualUsageAnalyzer(pages, visuals, catalog)
    usages = analyzer.get_direct_usages()

    assert len(usages) == 3

    u_meas = next(u for u in usages if u.object_name == "Total Sales")
    assert u_meas.object_type == "Measure"
    assert u_meas.visual_title == "Sales KPI"
    assert u_meas.page_name == "Overview"

    u_date = next(u for u in usages if u.object_name == "Date")
    assert u_date.object_type == "Column"
    assert u_date.table == "Date"
    assert u_date.visual_title == "Untitled"  # Normalized from 'None'

    u_amt = next(u for u in usages if u.object_name == "Amount")
    assert u_amt.object_type == "Column"
    assert u_amt.table == "Sales"


def test_visual_usage_legacy_projections():
    tables = [{"Table Name": "Transactions"}]
    columns = []
    measures = [{"Table": "Transactions", "Measure Name": "Net Balance"}]
    calc_columns = []

    catalog = ModelCatalog(tables, columns, measures, calc_columns)

    pages = [{"Page ID": "p1", "Page Name": "Finance"}]
    visuals = [
        {
            "Page ID": "p1",
            "Page Name": "Finance",
            "Visual ID": "101",
            "Visual Name": "card_balance",
            "Visual Type": "card",
            "Visual Title": "Total Balance",
            "raw_data": {
                "singleVisual": {
                    "projections": {
                        "Values": [
                            {"queryRef": "Transactions.Net Balance"}
                        ]
                    }
                }
            }
        }
    ]

    analyzer = VisualUsageAnalyzer(pages, visuals, catalog)
    usages = analyzer.get_direct_usages()
    assert len(usages) == 1
    assert usages[0].object_name == "Net Balance"
    assert usages[0].table == "Transactions"
    assert usages[0].usage_type == "Direct"

