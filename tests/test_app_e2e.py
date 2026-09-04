"""End-to-end Integration tests for the Flask Web Application."""

import io
import pytest
from app import app
from tests.fixtures import create_mock_tmdl_pbip_zip, create_mock_bim_pbip_zip


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Power BI Report Analyzer" in response.data
    assert b"Upload PBIP Project ZIP" in response.data


def test_upload_no_file(client):
    response = client.post("/upload", data={})
    assert response.status_code == 400
    assert b"No file part in request" in response.data


def test_upload_non_zip(client):
    data = {"file": (io.BytesIO(b"dummy text"), "report.txt")}
    response = client.post("/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert b"Only .zip files" in response.data


def test_upload_tmdl_pbip_flow(client, tmp_path):
    zip_path = str(tmp_path / "mock_tmdl.zip")
    create_mock_tmdl_pbip_zip(zip_path)

    with open(zip_path, "rb") as f:
        data = {"file": (f, "SalesAnalytics.zip")}
        response = client.post("/upload", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    assert b"SalesAnalytics" in response.data
    assert b"Extraction Successful" in response.data
    assert b"Download Excel Report" in response.data
    assert b"TMDL" in response.data


def test_upload_bim_pbip_flow(client, tmp_path):
    zip_path = str(tmp_path / "mock_bim.zip")
    create_mock_bim_pbip_zip(zip_path)

    with open(zip_path, "rb") as f:
        data = {"file": (f, "FinanceReport.zip")}
        response = client.post("/upload", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    assert b"FinanceReport" in response.data
    assert b"BIM_JSON" in response.data

