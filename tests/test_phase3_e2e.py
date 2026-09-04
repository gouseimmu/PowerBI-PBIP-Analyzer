"""End-to-end tests for Phase 3 (9-sheet Excel generation & Flask results)."""

import openpyxl
import pytest
from app import app
from output.excel_generator import ExcelGenerator
from tests.fixtures import create_mock_tmdl_pbip_zip

EXPECTED_9_SHEETS = [
    "Executive Summary",
    "Tables & Columns",
    "Measures & Calculated Columns",
    "Relationships & Lineage",
    "Pages & Visuals",
    "Data Sources & Queries",
    "Usage & Unused Objects",
    "DAX Recommendations",
    "Model & Date Metadata",
]


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_excel_9_sheets_generation(tmp_path):
    output_file = str(tmp_path / "full_phase3_analysis.xlsx")

    metadata = {
        "model_info": {
            "Report / Project Name": "SalesAnalytics",
            "Semantic Model Name": "SalesModel",
            "Model Format": "TMDL",
            "Culture": "en-US",
            "Compatibility Level": "1550",
            "Source Query Culture": "en-US",
            "Default Data Source Version": "powerBI_V3",
        },
        "tables": [{"Table Name": "Sales", "Table Type": "Data"}],
        "columns": [{"Table Name": "Sales", "Column Name": "Amount", "Data Type": "decimal", "Is Hidden": "No", "Column Type": "Data", "Format String": "$#,##0.00", "Source Column": "Amount", "Description": "None"}],
        "calculated_columns": [{"Table": "Sales", "Column": "Margin", "Data Type": "double", "DAX Expression": "Sales[Amount] * 0.2", "Is Hidden": "No"}],
        "measures": [{"Table": "Sales", "Measure Name": "Total Sales", "DAX Expression": "SUM(Sales[Amount])", "Format String": "$#,##0.00", "Is Hidden": "No", "Description": "None"}],
        "relationships": [],
        "key_columns": [],
        "relationship_metrics": {},
        "pages": [],
        "visuals": [],
        "data_sources": [],
        "date_table_summary": {"Date Table Exists": "No", "Date Table Name": "None"},
        "date_tables": [],
        "object_usage": [],
        "visual_usage": [],
        "dax_dependencies": [],
        "usage_lineage": [],
        "unused_objects": [],
        "phase2_summary": {},
        "dax_analysis": [
            {
                "Object Type": "Measure",
                "Table": "Sales",
                "Object Name": "Total Sales",
                "Original DAX": "SUM(Sales[Amount])",
                "Used": "Yes",
                "Usage Type": "Direct",
                "Direct Usage Count": 1,
                "Indirect Usage Count": 0,
                "Dependency Count": 1,
                "Complexity Score": 2.5,
                "Character Count": 18,
                "Line Count": 1,
                "Function Count": 1,
                "CALCULATE Count": 0,
                "FILTER Count": 0,
                "Iterator Count": 0,
                "VAR Count": 0,
                "Issue Count": 0,
                "Highest Severity": "None",
                "Analysis Status": "Complete",
            }
        ],
        "dax_improvements": [
            {
                "Object Type": "Measure",
                "Table": "Sales",
                "Object Name": "MarginPct",
                "Original DAX": "SUM(Sales[Profit]) / SUM(Sales[Revenue])",
                "Issue Category": "Reliability",
                "Severity": "Medium",
                "Issue": "Division operator '/' used",
                "Explanation": "Standard / operator does not handle divide by zero safely.",
                "Recommendation": "Use DIVIDE()",
                "Suggested DAX": "DIVIDE(SUM(Sales[Profit]), SUM(Sales[Revenue]), 0)",
                "Confidence": "High",
                "Source": "Static Rule",
                "Validation Status": "Validated",
                "Requires Manual Validation": "Yes",
            }
        ],
        "dax_complexity": [
            {
                "Object Type": "Measure",
                "Table": "Sales",
                "Object Name": "Total Sales",
                "Character Count": 18,
                "Line Count": 1,
                "Function Count": 1,
                "Referenced Measures": 0,
                "Referenced Columns": 1,
                "Referenced Tables": 1,
                "CALCULATE Count": 0,
                "FILTER Count": 0,
                "Iterator Count": 0,
                "VAR Count": 0,
                "Nesting Depth": 1,
                "Complexity Score": 2.5,
            }
        ],
        "phase3_summary": {
            "DAX Objects Analyzed": 2,
            "Measures Analyzed": 2,
            "Calculated Columns Analyzed": 0,
            "Objects With Potential Improvements": 1,
            "High Severity Issues": 0,
            "Medium Severity Issues": 1,
            "Low Severity Issues": 0,
            "Informational Findings": 0,
            "AI Suggestions": 0,
            "Static Suggestions": 1,
            "AI Failures": 0,
            "Suggestions Requiring Manual Validation": 1,
        }
    }

    ExcelGenerator.generate_report(metadata, output_file)

    wb = openpyxl.load_workbook(output_file)
    assert len(wb.sheetnames) == 9
    assert wb.sheetnames == EXPECTED_9_SHEETS


def test_flask_upload_phase3_full_pipeline(client, tmp_path):
    zip_path = str(tmp_path / "mock_tmdl_full3.zip")
    create_mock_tmdl_pbip_zip(zip_path)

    with open(zip_path, "rb") as f:
        data = {"file": (f, "SalesAnalytics.zip")}
        response = client.post("/upload", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    assert b"SalesAnalytics" in response.data
    assert b"Extraction Successful" in response.data
    assert b"Download Excel Report" in response.data
