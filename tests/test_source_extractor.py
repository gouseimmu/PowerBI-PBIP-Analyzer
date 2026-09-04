"""Tests for SourceExtractor (Power Query & M Expression classification)."""

from extractors.source_extractor import SourceExtractor, sanitize_expression


def test_sql_server_source():
    partitions = [{
        "table": "Customer",
        "type": "m",
        "expression": 'let Source = Sql.Database("sqlserver.corp.local", "DataWarehouse") in Source'
    }]
    sources = SourceExtractor.extract_sources(partitions)
    assert len(sources) == 1
    assert sources[0]["Source Type"] == "SQL Server"
    assert "sqlserver.corp.local" in sources[0]["Source Details"]
    assert "DataWarehouse" in sources[0]["Source Details"]


def test_excel_source():
    partitions = [{
        "table": "Sales",
        "type": "m",
        "expression": 'let Source = Excel.Workbook(File.Contents("D:\\Reports\\Sales.xlsx")) in Source'
    }]
    sources = SourceExtractor.extract_sources(partitions)
    assert len(sources) == 1
    assert sources[0]["Source Type"] == "Excel"
    assert "Sales.xlsx" in sources[0]["Source Details"]


def test_sharepoint_source():
    partitions = [{
        "table": "Documents",
        "type": "m",
        "expression": 'let Source = SharePoint.Files("https://myorg.sharepoint.com/teams/finance") in Source'
    }]
    sources = SourceExtractor.extract_sources(partitions)
    assert len(sources) == 1
    assert sources[0]["Source Type"] == "SharePoint"
    assert "https://myorg.sharepoint.com" in sources[0]["Source Details"]


def test_csv_source():
    partitions = [{
        "table": "Logs",
        "type": "m",
        "expression": 'let Source = Csv.Document(File.Contents("C:\\logs.csv")) in Source'
    }]
    sources = SourceExtractor.extract_sources(partitions)
    assert len(sources) == 1
    assert sources[0]["Source Type"] == "CSV"


def test_web_source():
    partitions = [{
        "table": "ExchangeRates",
        "type": "m",
        "expression": 'let Source = Web.Contents("https://api.exchangerates.io/v1/latest") in Source'
    }]
    sources = SourceExtractor.extract_sources(partitions)
    assert len(sources) == 1
    assert sources[0]["Source Type"] == "Web"


def test_password_redaction():
    raw_expr = 'Sql.Database("server", "db", [Password="SuperSecret123", User="admin"])'
    sanitized = sanitize_expression(raw_expr)
    assert "SuperSecret123" not in sanitized
    assert "[REDACTED]" in sanitized

