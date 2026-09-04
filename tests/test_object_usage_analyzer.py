"""Tests for ObjectUsageAnalyzer (Direct vs Indirect classification, Lineage, Unused Objects)."""

import pytest
from analyzers.dax_dependency_analyzer import DAXDependencyAnalyzer, ModelCatalog
from analyzers.visual_usage_analyzer import VisualUsageAnalyzer, DirectVisualUsage
from analyzers.object_usage_analyzer import ObjectUsageAnalyzer


def test_direct_vs_indirect_lineage():
    tables = [
        {"Table Name": "Sales"},
        {"Table Name": "Customer"},
        {"Table Name": "Date"},
    ]
    columns = [
        {"Table Name": "Sales", "Column Name": "Amount"},
        {"Table Name": "Sales", "Column Name": "Cost"},
        {"Table Name": "Sales", "Column Name": "UnusedCol"},
        {"Table Name": "Date", "Column Name": "Date"},
    ]
    calc_columns = [
        {
            "Table": "Sales",
            "Column": "Margin Percent",
            "DAX Expression": "DIVIDE(Sales[Amount] - Sales[Cost], Sales[Amount], 0)"
        },
        {
            "Table": "Sales",
            "Column": "UnusedCalcCol",
            "DAX Expression": "Sales[Amount] * 0.1"
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
            "Measure Name": "Sales Growth",
            "DAX Expression": "DIVIDE([Sales YTD] - [Total Sales], [Total Sales], 0)"
        },
        {
            "Table": "Sales",
            "Measure Name": "UnusedMeasure",
            "DAX Expression": "AVERAGE(Sales[Amount])"
        }
    ]

    catalog = ModelCatalog(tables, columns, measures, calc_columns)
    dax_analyzer = DAXDependencyAnalyzer(catalog, measures, calc_columns)

    # Simulate Visual that directly references [Sales Growth] only
    direct_usages = [
        DirectVisualUsage(
            page_id="p1",
            page_name="Overview",
            visual_id="v1",
            visual_name="Card1",
            visual_type="card",
            visual_title="Growth KPI",
            object_type="Measure",
            table="Sales",
            object_name="Sales Growth",
            usage_type="Direct",
            canonical_id="MEASURE:Sales[Sales Growth]",
        )
    ]

    visual_analyzer = VisualUsageAnalyzer([], [], catalog)
    visual_analyzer.direct_usages = direct_usages
    visual_analyzer.visuals_with_parsed_refs = 1

    obj_analyzer = ObjectUsageAnalyzer(
        catalog=catalog,
        direct_usages=direct_usages,
        dax_analyzer=dax_analyzer,
        visual_analyzer=visual_analyzer,
        tables=tables,
        columns=columns,
        measures=measures,
        calc_columns=calc_columns,
    )

    obj_usage = {item["Object Name"]: item for item in obj_analyzer.get_object_usage()}

    # 1. Sales Growth must be DIRECT
    assert obj_usage["Sales Growth"]["Used"] == "Yes"
    assert obj_usage["Sales Growth"]["Usage Type"] == "Direct"
    assert obj_usage["Sales Growth"]["Direct Usage Count"] == 1

    # 2. Sales YTD must be INDIRECT
    assert obj_usage["Sales YTD"]["Used"] == "Yes"
    assert obj_usage["Sales YTD"]["Usage Type"] == "Indirect"
    assert obj_usage["Sales YTD"]["Direct Usage Count"] == 0
    assert obj_usage["Sales YTD"]["Indirect Usage Count"] >= 1

    # 3. Total Sales must be INDIRECT
    assert obj_usage["Total Sales"]["Used"] == "Yes"
    assert obj_usage["Total Sales"]["Usage Type"] == "Indirect"

    # 4. Sales[Amount] must be INDIRECT
    assert obj_usage["Amount"]["Used"] == "Yes"
    assert obj_usage["Amount"]["Usage Type"] == "Indirect"

    # 5. Date[Date] must be INDIRECT
    assert obj_usage["Date"]["Used"] == "Yes"
    assert obj_usage["Date"]["Usage Type"] == "Indirect"

    # 6. Unused objects
    assert obj_usage["UnusedMeasure"]["Used"] == "No"
    assert obj_usage["UnusedMeasure"]["Usage Type"] == "Unused"
    assert obj_usage["UnusedCalcCol"]["Used"] == "No"
    assert obj_usage["UnusedCol"]["Used"] == "No"

    # 7. Check Unused Objects List
    unused_list = [u["Object Name"] for u in obj_analyzer.get_unused_objects()]
    assert "UnusedMeasure" in unused_list
    assert "UnusedCalcCol" in unused_list
    assert "UnusedCol" in unused_list

    # 8. Check Usage Lineage
    lineage = obj_analyzer.get_usage_lineage()
    assert len(lineage) > 0
    paths = [l["Dependency Path"] for l in lineage]
    assert any("Sales Growth -> Sales YTD" in p for p in paths)
    assert any("Sales Growth -> Sales YTD -> Total Sales" in p or "Sales Growth -> Total Sales" in p for p in paths)

