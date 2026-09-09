"""Tests for Power BI AI Assistant Chatbot and ContextBuilder."""

import pytest
from typing import Dict, Any, List, Optional
from ai.provider import DAXAIProvider, NullAIProvider
from ai.context_builder import ContextBuilder
from ai.powerbi_assistant import PowerBIChatbot, SYSTEM_PROMPT


class MockChatAIProvider(DAXAIProvider):
    """Mock AI provider for testing chatbot behavior without external API calls."""

    def __init__(self, response_text: str = "Mock answer"):
        self._response_text = response_text
        self.last_messages: List[Dict[str, str]] = []
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "MockChatAIProvider"

    def is_available(self) -> bool:
        return True

    def analyze_dax(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> Optional[str]:
        self.call_count += 1
        self.last_messages = messages
        return self._response_text


@pytest.fixture
def mock_metadata() -> Dict[str, Any]:
    return {
        "project_name": "WorkforceAnalytics",
        "model_format": "TMDL",
        "report_format": "PBIR",
        "model_info": {
            "Report / Project Name": "WorkforceAnalytics",
            "Semantic Model Name": "WorkforceModel",
            "Model Format": "TMDL",
        },
        "tables": [
            {"Table Name": "Employee", "Table Type": "Data", "Is Hidden": "No"},
            {"Table Name": "Timesheet", "Table Type": "Data", "Is Hidden": "No"},
            {"Table Name": "Calendar", "Table Type": "Data", "Is Hidden": "No"},
            {"Table Name": "Training", "Table Type": "Data", "Is Hidden": "No"},
        ],
        "columns": [
            {"Table Name": "Employee", "Column Name": "EmployeeID", "Data Type": "int64"},
            {"Table Name": "Employee", "Column Name": "EmployeeName", "Data Type": "string"},
            {"Table Name": "Timesheet", "Column Name": "HoursWorked", "Data Type": "decimal"},
        ],
        "calculated_columns": [
            {"Table": "Employee", "Column": "Employee Tenure", "DAX Expression": "DATEDIFF(Employee[HireDate], TODAY(), YEAR)"}
        ],
        "measures": [
            {"Table": "Timesheet", "Measure Name": "Total Hours", "DAX Expression": "SUM(Timesheet[HoursWorked])"},
            {"Table": "Timesheet", "Measure Name": "Billable %", "DAX Expression": "DIVIDE([Billable Hours], [Total Hours])"},
            {"Table": "Training", "Measure Name": "Unused Training Count", "DAX Expression": "COUNTROWS(Training)"},
        ],
        "relationships": [
            {"From Table": "Timesheet", "From Column": "EmployeeID", "To Table": "Employee", "To Column": "EmployeeID", "Cardinality": "M:1", "Filter Direction": "Single", "Status": "Active"},
            {"From Table": "Timesheet", "From Column": "Date", "To Table": "Calendar", "To Column": "CalendarDate", "Cardinality": "M:1", "Filter Direction": "Single", "Status": "Active"},
        ],
        "key_columns": [
            {"Table": "Timesheet", "Column": "EmployeeID", "Relationship Role": "From (Many)", "Related Table": "Employee", "Related Column": "EmployeeID"}
        ],
        "relationship_metrics": {
            "Total Relationships": 2,
            "Active Relationships": 2,
            "Inactive Relationships": 0,
            "Single-direction Relationships": 2,
            "Both-direction Relationships": 0,
        },
        "pages": [{"Page ID": "p1", "Page Name": "Workforce Overview"}],
        "visuals": [{"Page ID": "p1", "Page Name": "Workforce Overview", "Visual ID": "v1", "Visual Name": "Card 1", "Visual Type": "Card", "Visual Title": "Total Hours Card"}],
        "data_sources": [{"Table": "Timesheet", "Source Type": "SQL Server", "Source Details": "Server: sql-workforce"}],
        "object_usage": [
            {"Object Name": "Total Hours", "Table": "Timesheet", "Object Type": "Measure", "Used": "Yes", "Usage Type": "Direct + Indirect"},
            {"Object Name": "Billable %", "Table": "Timesheet", "Object Type": "Measure", "Used": "Yes", "Usage Type": "Direct"},
            {"Object Name": "Unused Training Count", "Table": "Training", "Object Type": "Measure", "Used": "No", "Usage Type": "Unused"},
        ],
        "visual_usage": [
            {"Page Name": "Workforce Overview", "Visual Title": "Total Hours Card", "Table": "Timesheet", "Object Name": "Total Hours", "Object Type": "Measure"}
        ],
        "dax_dependencies": [
            {"Source Table": "Timesheet", "Source Object": "Billable %", "Target Table": "Timesheet", "Target Object": "Total Hours"}
        ],
        "unused_objects": [
            {"Object Name": "Unused Training Count", "Table": "Training", "Object Type": "Measure"}
        ],
        "dax_analysis": [
            {"Table": "Timesheet", "Object Name": "Total Hours", "Object Type": "Measure", "Original DAX": "SUM(Timesheet[HoursWorked])", "Complexity Score": 1.0}
        ],
        "dax_improvements": [],
        "model_health": {
            "score": 92,
            "grade": "A",
            "status_text": "Good",
            "deductions": [{"title": "1 Unused Measure", "impact": "-5 pts", "category": "Unused Objects", "description": "Unused Training Count"}],
        },
        "phase2_summary": {"Directly Used Objects": 2, "Indirectly Used Objects": 1, "Unused Objects": 1},
    }


def test_chatbot_requires_analyzed_pbip():
    bot = PowerBIChatbot(ai_provider=MockChatAIProvider())
    res = bot.ask("What is the health score?", metadata=None)
    assert res["status"] == "no_metadata"
    assert "upload and analyze" in res["answer"].lower()


def test_chatbot_ai_disabled_guard():
    bot = PowerBIChatbot(ai_provider=NullAIProvider())
    meta = {"project_name": "Test"}
    res = bot.ask("What tables exist?", metadata=meta)
    assert res["status"] == "ai_disabled"
    assert "disabled" in res["answer"].lower()


def test_chatbot_request_limit():
    provider = MockChatAIProvider()
    bot = PowerBIChatbot(ai_provider=provider, max_ai_requests=2)
    meta = {"project_name": "Test", "tables": []}

    r1 = bot.ask("Q1", metadata=meta)
    assert r1["status"] == "success"
    r2 = bot.ask("Q2", metadata=meta)
    assert r2["status"] == "success"

    r3 = bot.ask("Q3", metadata=meta)
    assert r3["status"] == "limit_reached"
    assert "limit reached" in r3["answer"].lower()
    assert provider.call_count == 2


def test_chatbot_response_caching(mock_metadata):
    provider = MockChatAIProvider("Model has 4 tables.")
    bot = PowerBIChatbot(ai_provider=provider)

    r1 = bot.ask("What tables exist?", metadata=mock_metadata)
    assert r1["status"] == "success"
    assert r1["cached"] is False
    assert provider.call_count == 1

    r2 = bot.ask("What tables exist?", metadata=mock_metadata)
    assert r2["status"] == "success"
    assert r2["cached"] is True
    assert provider.call_count == 1  # No extra API call


def test_context_builder_dax_intent(mock_metadata):
    ctx = ContextBuilder.build_context("Explain [Total Hours]", metadata=mock_metadata)
    assert "focused_objects" in ctx
    focused = ctx["focused_objects"]
    assert len(focused) >= 1
    assert focused[0]["object_name"] == "Total Hours"
    assert "SUM(Timesheet[HoursWorked])" in focused[0]["dax_expression"]


def test_context_builder_unused_objects_intent(mock_metadata):
    ctx = ContextBuilder.build_context("Which tables or measures are unused?", metadata=mock_metadata)
    assert "unused_objects_summary" in ctx
    assert ctx["unused_objects_summary"]["unused_objects_count"] == 1


def test_context_builder_relationships_intent(mock_metadata):
    ctx = ContextBuilder.build_context("Which relationships are active or bidirectional?", metadata=mock_metadata)
    assert "relationships_summary" in ctx
    assert len(ctx["relationships_summary"]["relationships"]) == 2


def test_context_builder_sources_intent(mock_metadata):
    ctx = ContextBuilder.build_context("What data sources are used?", metadata=mock_metadata)
    assert "data_sources" in ctx
    assert ctx["data_sources"][0]["Source Type"] == "SQL Server"


def test_context_builder_health_intent(mock_metadata):
    ctx = ContextBuilder.build_context("Why is my health score 92?", metadata=mock_metadata)
    assert "model_health" in ctx
    assert ctx["model_health"]["score"] == 92


def test_context_builder_followup_resolution(mock_metadata):
    history = [
        {"role": "user", "content": "Explain [Total Hours]"},
        {"role": "assistant", "content": "[Total Hours] calculates total hours worked."},
    ]
    ctx = ContextBuilder.build_context("Is it used in any visuals?", metadata=mock_metadata, chat_history=history)
    assert "focused_objects" in ctx
    assert ctx["focused_objects"][0]["object_name"] == "Total Hours"


def test_chatbot_grounding_system_prompt_inclusion(mock_metadata):
    provider = MockChatAIProvider()
    bot = PowerBIChatbot(ai_provider=provider)

    res = bot.ask("Explain [Billable %]", metadata=mock_metadata)
    assert res["status"] == "success"

    # Verify system prompt grounding instructions
    sys_msg = provider.last_messages[0]["content"]
    assert "You are a Power BI technical assistant" in sys_msg
    assert "Do NOT invent tables, columns, measures" in sys_msg
    assert "CRITICAL GROUNDING RULES" in sys_msg


def test_chatbot_azure_error_handling(mock_metadata):
    class ErrorAIProvider(DAXAIProvider):
        @property
        def provider_name(self) -> str: return "ErrorProvider"
        def is_available(self) -> bool: return True
        def analyze_dax(self, context): return None
        def chat_completion(self, messages, temperature=0.2, max_tokens=1000):
            raise RuntimeError("Azure OpenAI timeout / connection reset")

    bot = PowerBIChatbot(ai_provider=ErrorAIProvider())
    res = bot.ask("Summarize the model", metadata=mock_metadata)

    assert res["status"] == "error"
    assert "temporarily unavailable" in res["answer"].lower()

