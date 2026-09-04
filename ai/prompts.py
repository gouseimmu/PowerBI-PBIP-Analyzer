"""Prompts and Context Sanitizer for AI-Assisted DAX Optimization."""

import json
from typing import Dict, Any


def build_system_prompt() -> str:
    """Return the system instruction for DAX analysis."""
    return """You are a senior Power BI and DAX Performance Engineer.
Your task is to analyze Power BI DAX formulas and provide conservative, high-quality optimization and maintainability recommendations.

RULES & CONSTRAINTS:
1. PRESERVE BUSINESS LOGIC & SEMANTICS EXACTLY.
2. NEVER invent tables, columns, or measures that do not exist in the provided model context.
3. NEVER make speculative changes without justification.
4. If the formula is already optimal, set "has_improvement": false.
5. Provide a "suggested_dax" ONLY if you are confident in its semantic equivalence. If uncertain, state "Manual review required" in suggested_dax.
6. Return your output STRICTLY as a valid JSON object matching the requested schema.

JSON RESPONSE SCHEMA:
{
  "has_improvement": true,
  "category": "Performance" | "Reliability" | "Maintainability" | "Context Transition",
  "severity": "High" | "Medium" | "Low" | "Informational",
  "issue": "<Short description of issue>",
  "explanation": "<Why this pattern is a concern>",
  "recommendation": "<Actionable guidance>",
  "suggested_dax": "<Optimized DAX expression or 'Manual review required'>",
  "confidence": "High" | "Medium" | "Low",
  "requires_manual_validation": true
}"""


def build_user_prompt(context: Dict[str, Any]) -> str:
    """Build the sanitized user prompt with model context and static analysis findings."""
    obj_name = context.get("object_name", "Unknown")
    obj_type = context.get("object_type", "Measure")
    table_name = context.get("table", "Unknown")
    original_dax = context.get("original_dax", "")

    known_columns = context.get("known_columns", [])
    known_measures = context.get("known_measures", [])
    dependencies = context.get("dependencies", [])
    static_issues = context.get("static_issues", [])
    usage_summary = context.get("usage_summary", "Unknown")

    prompt_lines = [
        f"OBJECT TO ANALYZE:",
        f"- Object Name: {obj_name}",
        f"- Object Type: {obj_type}",
        f"- Table: {table_name}",
        f"- Usage Context: {usage_summary}",
        f"\nORIGINAL DAX EXPRESSION:\n```dax\n{original_dax}\n```",
    ]

    if dependencies:
        prompt_lines.append(f"\nKNOWN MODEL DEPENDENCIES:\n- " + "\n- ".join(dependencies[:10]))

    if known_columns:
        prompt_lines.append(f"\nAVAILABLE COLUMNS IN '{table_name}':\n" + ", ".join(known_columns[:15]))

    if static_issues:
        prompt_lines.append("\nSTATIC ANALYZER PRELIMINARY OBSERVATIONS:")
        for idx, issue in enumerate(static_issues, 1):
            prompt_lines.append(f"{idx}. [{issue.get('severity')}] {issue.get('issue')}: {issue.get('explanation')}")

    prompt_lines.append(
        "\nProvide your analysis strictly in the required JSON format. Do not include markdown ticks outside the JSON."
    )

    return "\n".join(prompt_lines)

