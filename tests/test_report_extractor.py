"""Tests for ReportExtractor on PBIR (pages & visuals)."""

import pytest
from extractors.pbip_reader import PBIPReader
from extractors.report_extractor import ReportExtractor
from tests.fixtures import create_mock_tmdl_pbip_zip, create_mock_bim_pbip_zip


def test_pbir_pages_and_visuals_extraction(tmp_path):
    zip_path = str(tmp_path / "mock_tmdl.zip")
    create_mock_tmdl_pbip_zip(zip_path)

    with PBIPReader.read_zip(zip_path) as project:
        extractor = ReportExtractor(project)
        pages = extractor.get_pages()
        assert len(pages) == 2
        page_names = [p["Page Name"] for p in pages]
        assert "Executive Overview" in page_names
        assert "Customer Analysis" in page_names

        visuals = extractor.get_visuals()
        assert len(visuals) == 3
        
        # Check visual types
        vis_types = [v["Visual Type"] for v in visuals]
        assert "Card" in vis_types
        assert "Line Chart" in vis_types
        assert "Table" in vis_types

        # Check visual titles
        vis_titles = [v["Visual Title"] for v in visuals]
        assert "Total Revenue KPI" in vis_titles
        assert "Monthly Revenue Trend" in vis_titles
        assert "Customer Breakdown" in vis_titles


def test_legacy_report_json_extraction(tmp_path):
    zip_path = str(tmp_path / "mock_bim.zip")
    create_mock_bim_pbip_zip(zip_path)

    with PBIPReader.read_zip(zip_path) as project:
        extractor = ReportExtractor(project)
        pages = extractor.get_pages()
        assert len(pages) == 1
        assert pages[0]["Page Name"] == "Finance Summary"

        visuals = extractor.get_visuals()
        assert len(visuals) == 1
        assert visuals[0]["Visual Type"] == "Card"
        assert visuals[0]["Visual Title"] == "Total Balance"

