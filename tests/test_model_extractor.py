"""Tests for ModelExtractor and TMDLParser."""

import pytest
from extractors.pbip_reader import PBIPReader
from extractors.model_extractor import ModelExtractor
from tests.fixtures import create_mock_tmdl_pbip_zip, create_mock_bim_pbip_zip


def test_tmdl_model_extraction(tmp_path):
    zip_path = str(tmp_path / "mock_tmdl.zip")
    create_mock_tmdl_pbip_zip(zip_path)

    with PBIPReader.read_zip(zip_path) as project:
        extractor = ModelExtractor(project)
        info = extractor.get_model_info()
        assert info["Report / Project Name"] == "SalesAnalytics"
        assert info["Model Format"] == "TMDL"

        tables = extractor.get_tables()
        table_names = [t["Table Name"] for t in tables]
        assert "Customer" in table_names
        assert "Sales" in table_names
        assert "Date" in table_names

        columns = extractor.get_columns()
        col_names = [c["Column Name"] for c in columns]
        assert "CustomerKey" in col_names
        assert "Customer Name" in col_names
        assert "Margin Percent" in col_names

        # Check calculated columns
        calc_cols = extractor.get_calculated_columns()
        calc_names = [c["Column"] for c in calc_cols]
        assert "Full Name" in calc_names
        assert "Margin Percent" in calc_names
        
        # Verify DAX expression captured
        margin_col = next(c for c in calc_cols if c["Column"] == "Margin Percent")
        assert "DIVIDE" in margin_col["DAX Expression"]

        # Check measures
        measures = extractor.get_measures()
        meas_names = [m["Measure Name"] for m in measures]
        assert "Customer Count" in meas_names
        assert "Total Sales" in meas_names
        assert "Total Margin" in meas_names

        total_sales_meas = next(m for m in measures if m["Measure Name"] == "Total Sales")
        assert "VAR Total" in total_sales_meas["DAX Expression"]
        assert total_sales_meas["Format String"] == "$#,##0.00"
        assert total_sales_meas["Description"] == "Sum of sales revenue"


def test_bim_json_model_extraction(tmp_path):
    zip_path = str(tmp_path / "mock_bim.zip")
    create_mock_bim_pbip_zip(zip_path)

    with PBIPReader.read_zip(zip_path) as project:
        extractor = ModelExtractor(project)
        info = extractor.get_model_info()
        assert info["Report / Project Name"] == "FinanceReport"
        assert info["Model Format"] == "BIM_JSON"

        tables = extractor.get_tables()
        table_names = [t["Table Name"] for t in tables]
        assert "Transactions" in table_names
        assert "Accounts" in table_names

        calc_cols = extractor.get_calculated_columns()
        assert len(calc_cols) == 1
        assert calc_cols[0]["Column"] == "IsCredit"
        assert "IF(" in calc_cols[0]["DAX Expression"]

        measures = extractor.get_measures()
        assert len(measures) == 1
        assert measures[0]["Measure Name"] == "Net Balance"
        assert measures[0]["DAX Expression"] == "SUM(Transactions[Amount])"

