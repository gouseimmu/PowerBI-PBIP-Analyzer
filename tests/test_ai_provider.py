"""Tests for AI Provider Abstraction, Prompt Sanitizer, and Response Parser."""

import os
import pytest
from ai.provider import NullAIProvider, get_ai_provider
from ai.prompts import build_user_prompt
from ai.response_parser import AIResponseParser
from analyzers.dax_dependency_analyzer import ModelCatalog


def test_null_ai_provider():
    provider = NullAIProvider()
    assert not provider.is_available()
    assert provider.analyze_dax({}) is None
    assert "Static Analysis Only" in provider.provider_name


def test_get_ai_provider_disabled(monkeypatch):
    monkeypatch.setenv("DISABLE_AI", "true")
    provider = get_ai_provider()
    assert isinstance(provider, NullAIProvider)


def test_prompt_builder_sanitization():
    context = {
        "object_name": "[Sales Growth]",
        "object_type": "Measure",
        "table": "Sales",
        "original_dax": "DIVIDE([Sales YTD], [Sales LY], 0)",
        "known_columns": ["Amount", "Cost"],
        "dependencies": ["[Sales YTD]", "[Sales LY]"],
        "static_issues": [{"severity": "Medium", "issue": "Repeated expr", "explanation": "test"}],
        "usage_summary": "Direct on Overview page",
    }
    prompt = build_user_prompt(context)
    assert "[Sales Growth]" in prompt
    assert "DIVIDE([Sales YTD], [Sales LY], 0)" in prompt
    assert "Amount, Cost" in prompt
    assert "Password" not in prompt


def test_ai_response_parser_valid_references():
    tables = [{"Table Name": "Sales"}]
    columns = [{"Table Name": "Sales", "Column Name": "Amount"}, {"Table Name": "Sales", "Column Name": "Cost"}]
    measures = [{"Table": "Sales", "Measure Name": "Total Sales"}]
    catalog = ModelCatalog(tables, columns, measures, [])

    raw_ai_json = {
        "has_improvement": True,
        "category": "Performance",
        "severity": "Medium",
        "issue": "Use native DIVIDE",
        "explanation": "Safer zero handling",
        "recommendation": "Use DIVIDE()",
        "suggested_dax": "DIVIDE(Sales[Amount], Sales[Cost], 0)",
        "confidence": "High",
        "requires_manual_validation": True,
    }

    issue = AIResponseParser.parse_and_validate(raw_ai_json, catalog, "Sales")
    assert issue is not None
    assert issue.category == "Performance"
    assert issue.severity == "Medium"
    assert issue.validation_status == "Validated"
    assert issue.suggested_dax == "DIVIDE(Sales[Amount], Sales[Cost], 0)"


def test_ai_response_parser_unknown_references():
    tables = [{"Table Name": "Sales"}]
    columns = [{"Table Name": "Sales", "Column Name": "Amount"}]
    catalog = ModelCatalog(tables, columns, [], [])

    raw_ai_json = {
        "has_improvement": True,
        "category": "Performance",
        "severity": "Medium",
        "issue": "Hallucinated Column",
        "explanation": "Test explanation",
        "recommendation": "Test recommendation",
        "suggested_dax": "DIVIDE(Sales[NonExistentColumn], 10, 0)",
        "confidence": "Low",
        "requires_manual_validation": True,
    }

    issue = AIResponseParser.parse_and_validate(raw_ai_json, catalog, "Sales")
    assert issue is not None
    assert issue.validation_status == "Invalid"
    assert "unknown model object" in issue.explanation

