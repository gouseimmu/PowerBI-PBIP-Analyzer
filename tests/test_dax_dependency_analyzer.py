"""Tests for DAX Dependency Analyzer, Reference Parser, and Cycle Detector."""

import pytest
from analyzers.dax_dependency_analyzer import DAXDependencyAnalyzer, ModelCatalog, clean_dax_comments_and_strings


def test_clean_dax_comments_and_strings():
    dax = """
    // Line comment 1
    -- Line comment 2
    /* Multi-line
       comment */
    VAR Message = "Hello [FakeMeasure] in string"
    RETURN
        CALCULATE(SUM(Sales[Amount]), 'Date'[Year] = 2026)
    """
    cleaned, literals = clean_dax_comments_and_strings(dax)
    assert "//" not in cleaned
    assert "--" not in cleaned
    assert "Multi-line" not in cleaned
    assert "FakeMeasure" not in cleaned  # Inside masked string literal
    assert "Sales[Amount]" in cleaned
    assert "'Date'[Year]" in cleaned


def test_dax_reference_extractor():
    dax = """
    DIVIDE(
        [Sales YTD] - [Total Sales],
        SUM('Sales Fact'[Cost]) + Sales[Tax],
        0
    ) + COUNTROWS('Customer Dim')
    """
    refs = DAXDependencyAnalyzer.extract_dax_references(dax)
    ref_names = [(r.ref_type, r.table_name, r.object_name) for r in refs]

    assert ("unqualified_bracket", None, "Sales YTD") in ref_names
    assert ("unqualified_bracket", None, "Total Sales") in ref_names
    assert ("qualified_column", "Sales Fact", "Cost") in ref_names
    assert ("qualified_column", "Sales", "Tax") in ref_names
    assert ("table", "Customer Dim", "Customer Dim") in ref_names


def test_dax_resolution_and_edges():
    tables = [{"Table Name": "Sales"}, {"Table Name": "Date"}]
    columns = [
        {"Table Name": "Sales", "Column Name": "Amount"},
        {"Table Name": "Sales", "Column Name": "Cost"},
        {"Table Name": "Date", "Column Name": "Date"},
    ]
    calc_columns = [
        {
            "Table": "Sales",
            "Column": "Margin",
            "DAX Expression": "Sales[Amount] - Sales[Cost]"
        }
    ]
    measures = [
        {
            "Table": "Sales",
            "Measure Name": "Total Sales",
            "DAX Expression": "SUM(Sales[Amount])"
        },
        {
            "Table": "Sales",
            "Measure Name": "Sales YTD",
            "DAX Expression": "TOTALYTD([Total Sales], 'Date'[Date])"
        },
        {
            "Table": "Sales",
            "Measure Name": "Unknown Dep Measure",
            "DAX Expression": "[NonExistentMeasure] + 10"
        }
    ]

    catalog = ModelCatalog(tables, columns, measures, calc_columns)
    analyzer = DAXDependencyAnalyzer(catalog, measures, calc_columns)
    edges = analyzer.get_edges()

    # Total Sales -> Sales[Amount]
    e_sales = next(e for e in edges if e.source_name == "Total Sales" and e.target_name == "Amount")
    assert e_sales.dependency_type == "Measure -> Column"
    assert e_sales.target_table == "Sales"
    assert e_sales.resolution_status == "Resolved"

    # Sales YTD -> Total Sales
    e_ytd_meas = next(e for e in edges if e.source_name == "Sales YTD" and e.target_name == "Total Sales")
    assert e_ytd_meas.dependency_type == "Measure -> Measure"
    assert e_ytd_meas.resolution_status == "Resolved"

    # Sales YTD -> Date[Date]
    e_ytd_col = next(e for e in edges if e.source_name == "Sales YTD" and e.target_name == "Date")
    assert e_ytd_col.dependency_type == "Measure -> Column"
    assert e_ytd_col.target_table == "Date"

    # Margin (Calc Col) -> Sales[Amount] & Sales[Cost]
    e_margin_amt = next(e for e in edges if e.source_name == "Margin" and e.target_name == "Amount")
    assert e_margin_amt.dependency_type == "Calculated Column -> Column"

    # Unresolved reference
    unresolved = analyzer.get_unresolved_references()
    assert len(unresolved) == 1
    assert "NonExistentMeasure" in unresolved[0]["Referenced Text"]


def test_circular_dependency_detection():
    tables = [{"Table Name": "T"}]
    columns = []
    calc_columns = []
    measures = [
        {"Table": "T", "Measure Name": "A", "DAX Expression": "[B] + 1"},
        {"Table": "T", "Measure Name": "B", "DAX Expression": "[C] + 2"},
        {"Table": "T", "Measure Name": "C", "DAX Expression": "[A] + 3"},
    ]

    catalog = ModelCatalog(tables, columns, measures, calc_columns)
    analyzer = DAXDependencyAnalyzer(catalog, measures, calc_columns)

    cycles = analyzer.get_circular_dependencies()
    assert len(cycles) >= 1
    cycle_nodes = cycles[0]["Nodes"]
    assert any("MEASURE:T[A]" in n for n in cycle_nodes)
    assert any("MEASURE:T[B]" in n for n in cycle_nodes)
    assert any("MEASURE:T[C]" in n for n in cycle_nodes)

