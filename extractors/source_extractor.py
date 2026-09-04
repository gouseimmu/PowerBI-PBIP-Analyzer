"""Data Source and M Expression Extractor.

Inspects partition M queries, expressions, and model data sources to identify
source types, servers/paths/URLs, and Power Query expressions safely.
"""

import re
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Regular expressions to detect source types and extract safe target details
SOURCE_PATTERNS = [
    # SQL Server
    (
        r'Sql\.Database\s*\(\s*"([^"]+)"(?:\s*,\s*"([^"]+)")?',
        "SQL Server",
        lambda m: f"Server: {m.group(1)}" + (f", Database: {m.group(2)}" if m.group(2) else ""),
    ),
    (
        r'Sql\.Databases\s*\(\s*"([^"]+)"',
        "SQL Server",
        lambda m: f"Server: {m.group(1)}",
    ),
    # Excel
    (
        r'(?:Excel\.Workbook|Excel\.Sheet)\s*\(\s*File\.Contents\s*\(\s*"([^"]+)"',
        "Excel",
        lambda m: f"File: {m.group(1)}",
    ),
    (
        r'Excel\.Workbook\s*\(',
        "Excel",
        lambda m: "Excel Workbook",
    ),
    # SharePoint
    (
        r'SharePoint\.(?:Files|Tables|Contents)\s*\(\s*"([^"]+)"',
        "SharePoint",
        lambda m: f"URL: {m.group(1)}",
    ),
    # CSV / Text
    (
        r'Csv\.Document\s*\(\s*File\.Contents\s*\(\s*"([^"]+)"',
        "CSV",
        lambda m: f"File: {m.group(1)}",
    ),
    (
        r'Csv\.Document\s*\(',
        "CSV",
        lambda m: "CSV Document",
    ),
    # Web / REST API
    (
        r'Web\.(?:Contents|Page|BrowserContents)\s*\(\s*"([^"]+)"',
        "Web",
        lambda m: f"URL: {m.group(1)}",
    ),
    # Dataflows
    (
        r'(?:PowerBI|PowerPlatform)\.Dataflows\s*\(',
        "Dataflow",
        lambda m: "Power BI Dataflow",
    ),
    # Oracle
    (
        r'Oracle\.Database\s*\(\s*"([^"]+)"',
        "Oracle",
        lambda m: f"Server: {m.group(1)}",
    ),
    # PostgreSQL
    (
        r'PostgreSQL\.Database\s*\(\s*"([^"]+)"(?:\s*,\s*"([^"]+)")?',
        "PostgreSQL",
        lambda m: f"Server: {m.group(1)}" + (f", Database: {m.group(2)}" if m.group(2) else ""),
    ),
    # MySQL
    (
        r'MySQL\.Database\s*\(\s*"([^"]+)"(?:\s*,\s*"([^"]+)")?',
        "MySQL",
        lambda m: f"Server: {m.group(1)}" + (f", Database: {m.group(2)}" if m.group(2) else ""),
    ),
    # Snowflake
    (
        r'Snowflake\.Databases\s*\(\s*"([^"]+)"(?:\s*,\s*"([^"]+)")?',
        "Snowflake",
        lambda m: f"Server: {m.group(1)}" + (f", Warehouse/DB: {m.group(2)}" if m.group(2) else ""),
    ),
    # Azure Storage / Data Lake
    (
        r'AzureStorage\.(?:Blobs|DataLake|Tables)\s*\(\s*"([^"]+)"',
        "Azure Storage",
        lambda m: f"Account/URL: {m.group(1)}",
    ),
    # Local Folder
    (
        r'Folder\.Files\s*\(\s*"([^"]+)"',
        "Folder",
        lambda m: f"Path: {m.group(1)}",
    ),
    # OData Feed
    (
        r'OData\.Feed\s*\(\s*"([^"]+)"',
        "OData",
        lambda m: f"Feed URL: {m.group(1)}",
    ),
    # Salesforce
    (
        r'Salesforce\.(?:Data|Reports)\s*\(',
        "Salesforce",
        lambda m: "Salesforce Connection",
    ),
    # SAP HANA / BW
    (
        r'Sap(?:Hana|BusinessWarehouse)\.(?:Database|Cubes)\s*\(\s*"([^"]+)"',
        "SAP",
        lambda m: f"Server: {m.group(1)}",
    ),
    # Analysis Services
    (
        r'AnalysisServices\.Database\s*\(\s*"([^"]+)"(?:\s*,\s*"([^"]+)")?',
        "Analysis Services",
        lambda m: f"Server: {m.group(1)}" + (f", Database: {m.group(2)}" if m.group(2) else ""),
    ),
    # Enter Data / Static Table
    (
        r'(?:#table|Table\.FromRows|DATATABLE)\s*\(',
        "Enter Data",
        lambda m: "Inline / Entered Data Table",
    ),
]


def sanitize_expression(expr: str) -> str:
    """Remove obvious passwords or secrets from connection strings/expressions."""
    if not expr:
        return ""
    # Mask passwords, tokens, API keys
    sanitized = re.sub(
        r'(?i)(password|pwd|secret|access_token|apikey|api_key|bearer)\s*=\s*"[^"]*"',
        r'\1="[REDACTED]"',
        expr,
    )
    sanitized = re.sub(
        r'(?i)(password|pwd|secret|access_token|apikey|api_key|bearer)\s*=\s*\'[^\']*\'',
        r"\1='[REDACTED]'",
        sanitized,
    )
    return sanitized


class SourceExtractor:
    """Extracts data sources and Power Query expressions from semantic model partitions."""

    @classmethod
    def extract_sources(cls, partition_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analyze a list of partition/expression dictionaries and return normalized data source items."""
        sources: List[Dict[str, Any]] = []

        for item in partition_items:
            table_name = item.get("table", "Unknown")
            part_type = item.get("type", "m")
            raw_expr = item.get("expression", "")

            if not raw_expr:
                continue

            source_type, source_details = cls._identify_source(raw_expr, part_type)
            safe_expr = sanitize_expression(raw_expr)

            sources.append({
                "Table": table_name,
                "Source Type": source_type,
                "Source Details": source_details,
                "Power Query / M Expression": safe_expr if safe_expr else "None",
            })

        logger.info(f"Extracted {len(sources)} data sources.")
        return sources

    @classmethod
    def _identify_source(cls, expression: str, part_type: str) -> tuple[str, str]:
        """Detect source type and safe details from expression text."""
        if not expression:
            return "Unknown", "Unknown"

        # Check DAX calculated tables
        if part_type.lower() in ["calculated", "calculation"]:
            return "DAX Calculated Table", "Model Internal DAX Expression"

        # Check known source patterns
        for pattern, src_type, detail_fn in SOURCE_PATTERNS:
            m = re.search(pattern, expression, re.IGNORECASE)
            if m:
                try:
                    details = detail_fn(m)
                except Exception:
                    details = "Detected"
                return src_type, details

        # Fallback if M code exists but pattern didn't match specific driver
        if "let" in expression and "in" in expression:
            return "Other (Power Query M)", "Custom M Query"

        return "Unknown", "Unknown"

