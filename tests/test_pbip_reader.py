"""Tests for PBIPReader and ZIP safe extraction."""

import os
import zipfile
import pytest
from extractors.pbip_reader import PBIPReader, PBIPExtractionError, ModelFormat, ReportFormat
from tests.fixtures import create_mock_tmdl_pbip_zip, create_mock_bim_pbip_zip


def test_read_tmdl_pbip(tmp_path):
    zip_path = str(tmp_path / "mock_tmdl.zip")
    create_mock_tmdl_pbip_zip(zip_path)

    with PBIPReader.read_zip(zip_path) as project:
        assert project.project_name == "SalesAnalytics"
        assert project.model_format == ModelFormat.TMDL
        assert project.report_format == ReportFormat.PBIR_PAGES
        assert project.model_dir is not None
        assert project.report_dir is not None
        temp_dir = project.temp_dir
        assert os.path.exists(temp_dir)

    # Temporary directory should be cleaned up after exit
    assert not os.path.exists(temp_dir)


def test_read_bim_pbip(tmp_path):
    zip_path = str(tmp_path / "mock_bim.zip")
    create_mock_bim_pbip_zip(zip_path)

    with PBIPReader.read_zip(zip_path) as project:
        assert project.project_name == "FinanceReport"
        assert project.model_format == ModelFormat.BIM_JSON
        assert project.report_format in [ReportFormat.LEGACY_REPORT_JSON, ReportFormat.PBIR_PAGES]


def test_invalid_zip_path():
    with pytest.raises(PBIPExtractionError, match="ZIP file not found"):
        PBIPReader.read_zip("non_existent_file.zip")


def test_corrupted_zip_file(tmp_path):
    bad_zip = tmp_path / "corrupt.zip"
    bad_zip.write_text("This is not a zip file.")
    with pytest.raises(PBIPExtractionError, match="not a valid ZIP archive"):
        PBIPReader.read_zip(str(bad_zip))


def test_missing_pbip_file(tmp_path):
    empty_zip = tmp_path / "no_pbip.zip"
    with zipfile.ZipFile(empty_zip, "w") as zf:
        zf.writestr("random_file.txt", "hello")
    with pytest.raises(PBIPExtractionError, match="No .pbip file found"):
        PBIPReader.read_zip(str(empty_zip))


def test_zip_slip_rejection(tmp_path):
    malicious_zip = tmp_path / "malicious.zip"
    with zipfile.ZipFile(malicious_zip, "w") as zf:
        # Attempt path traversal
        zf.writestr("../evil.txt", "malicious payload")

    with pytest.raises(PBIPExtractionError, match="Zip-slip attack detected"):
        PBIPReader.read_zip(str(malicious_zip))

