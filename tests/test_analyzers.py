"""Tests for RelationshipAnalyzer and DateTableAnalyzer."""

from analyzers.relationship_analyzer import RelationshipAnalyzer, normalize_cardinality, normalize_filter_direction, normalize_status
from analyzers.date_table_analyzer import DateTableAnalyzer


def test_cardinality_normalization():
    assert normalize_cardinality("manyToOne") == "M:1"
    assert normalize_cardinality("oneToMany") == "1:M"
    assert normalize_cardinality("oneToOne") == "1:1"
    assert normalize_cardinality("manyToMany") == "M:M"
    assert normalize_cardinality(None, from_card="many", to_card="one") == "M:1"
    assert normalize_cardinality(None, from_card="one", to_card="many") == "1:M"
    assert normalize_cardinality("invalid_card") == "Unknown"


def test_filter_direction_normalization():
    assert normalize_filter_direction("oneDirection") == "Single"
    assert normalize_filter_direction("bothDirections") == "Both"
    assert normalize_filter_direction("single") == "Single"
    assert normalize_filter_direction("both") == "Both"
    assert normalize_filter_direction("automatic") == "Single"
    assert normalize_filter_direction("unknown_value") == "Unknown"


def test_relationship_analyzer_key_columns():
    raw_rels = [
        {
            "fromTable": "Sales",
            "fromColumn": "CustomerID",
            "toTable": "Customer",
            "toColumn": "CustomerID",
            "cardinality": "manyToOne",
            "crossFilteringBehavior": "oneDirection",
            "isActive": True,
        },
        {
            "fromTable": "Orders",
            "fromColumn": "OrderID",
            "toTable": "Invoices",
            "toColumn": "OrderID",
            "cardinality": "oneToOne",
            "crossFilteringBehavior": "bothDirections",
            "isActive": False,
        }
    ]

    analyzer = RelationshipAnalyzer(raw_rels)
    rels = analyzer.get_relationships()
    assert len(rels) == 2
    assert rels[0]["Cardinality"] == "M:1"
    assert rels[0]["Filter Direction"] == "Single"
    assert rels[0]["Status"] == "Active"

    assert rels[1]["Cardinality"] == "1:1"
    assert rels[1]["Filter Direction"] == "Both"
    assert rels[1]["Status"] == "Inactive"

    # Check key columns
    keys = analyzer.get_key_columns()
    assert len(keys) == 4
    # Sales side
    assert keys[0]["Table"] == "Sales"
    assert keys[0]["Relationship Role"] == "From (Many)"
    assert keys[0]["Related Table"] == "Customer"
    # Customer side
    assert keys[1]["Table"] == "Customer"
    assert keys[1]["Relationship Role"] == "To (One)"
    assert keys[1]["Related Table"] == "Sales"

    metrics = analyzer.get_summary_metrics()
    assert metrics["Total Relationships"] == 2
    assert metrics["Active Relationships"] == 1
    assert metrics["Inactive Relationships"] == 1
    assert metrics["M:1 Relationships"] == 1
    assert metrics["1:1 Relationships"] == 1
    assert metrics["Single-direction Relationships"] == 1
    assert metrics["Both-direction Relationships"] == 1


def test_date_table_analyzer_explicit():
    tables = [
        {
            "name": "Calendar",
            "dataCategory": "Time",
            "columns": [{"name": "Date", "isKey": True, "dataCategory": "Time"}]
        },
        {
            "name": "Sales",
            "columns": [{"name": "SalesDate", "dataType": "dateTime"}]
        },
        {
            # Should NOT be classified as Date Table merely due to column name 'Date'
            "name": "Orders",
            "columns": [{"name": "Date", "dataType": "string"}]
        }
    ]

    analyzer = DateTableAnalyzer(tables)
    summary = analyzer.get_date_table_summary()
    assert summary["Date Table Exists"] == "Yes"
    assert summary["Date Table Name"] == "Calendar"

    details = analyzer.get_date_tables_list()
    assert len(details) == 1
    assert details[0]["Table Name"] == "Calendar"


def test_date_table_analyzer_none():
    tables = [
        {
            "name": "Sales",
            "columns": [{"name": "OrderDate", "dataType": "dateTime"}]
        }
    ]

    analyzer = DateTableAnalyzer(tables)
    summary = analyzer.get_date_table_summary()
    assert summary["Date Table Exists"] == "No"
    assert summary["Date Table Name"] == "None"
    assert len(analyzer.get_date_tables_list()) == 0

