"""AI Response Parser, Schema Validator & Model Catalog Reference Cross-Checker."""

import re
import json
import logging
from typing import Dict, List, Tuple, Optional, Any

from models.dax_analysis import DAXQualityIssue
from analyzers.dax_dependency_analyzer import DAXDependencyAnalyzer, ModelCatalog

logger = logging.getLogger(__name__)


class AIResponseParser:
    """Parses, validates, and cross-checks AI-generated DAX recommendations against the model catalog."""

    @classmethod
    def parse_and_validate(
        cls,
        raw_response: Any,
        catalog: ModelCatalog,
        context_table: str,
    ) -> Optional[DAXQualityIssue]:
        """Parse raw AI JSON response and validate all referenced entities against ModelCatalog."""
        if not raw_response:
            return None

        data = raw_response
        if isinstance(raw_response, str):
            try:
                # Strip markdown code fences if present
                clean_str = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_response.strip(), flags=re.MULTILINE)
                data = json.loads(clean_str)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to decode AI response string as JSON: {e}")
                return None

        if not isinstance(data, dict):
            return None

        has_improvement = data.get("has_improvement", True)
        if not has_improvement:
            return None

        category = str(data.get("category", "Performance")).strip()
        severity = str(data.get("severity", "Medium")).strip()
        if severity not in ["High", "Medium", "Low", "Informational"]:
            severity = "Medium"

        issue = str(data.get("issue", "AI Optimization Opportunity")).strip()
        explanation = str(data.get("explanation", "")).strip()
        recommendation = str(data.get("recommendation", "")).strip()
        suggested_dax = str(data.get("suggested_dax", "Manual review required")).strip()
        confidence = str(data.get("confidence", "Medium")).strip()
        req_val = bool(data.get("requires_manual_validation", True))

        # Perform Model Catalog reference validation on suggested DAX
        val_status, val_note = cls._validate_references(suggested_dax, catalog, context_table)

        if val_status == "Invalid":
            explanation += f" [Warning: {val_note}]"

        return DAXQualityIssue(
            category=category,
            severity=severity,
            issue=issue,
            explanation=explanation,
            recommendation=recommendation,
            suggested_dax=suggested_dax,
            confidence=confidence,
            source="AI",
            validation_status=val_status,
            requires_manual_validation=req_val,
        )

    @classmethod
    def _validate_references(cls, suggested_dax: str, catalog: ModelCatalog, context_table: str) -> Tuple[str, str]:
        """Verify that all referenced tables, columns, and measures in suggested DAX exist in ModelCatalog."""
        if not suggested_dax or suggested_dax in ["Manual review required", "No change required", "No safe automatic rewrite"]:
            return "No Suggestion", ""

        refs = DAXDependencyAnalyzer.extract_dax_references(suggested_dax)
        if not refs:
            return "Validated", ""

        unrecognized = []

        for ref in refs:
            if ref.ref_type == "qualified_column":
                res = catalog.resolve_qualified_column(ref.table_name or "", ref.object_name)
                if not res:
                    unrecognized.append(f"{ref.table_name}[{ref.object_name}]")
            elif ref.ref_type == "unqualified_bracket":
                # Exclude common DAX temporary variable references or measure resolution
                res = catalog.resolve_unqualified(ref.object_name, context_table)
                if not res:
                    # Could be variable or unknown measure
                    unrecognized.append(f"[{ref.object_name}]")
            elif ref.ref_type == "table":
                res = catalog.resolve_table(ref.object_name)
                if not res:
                    unrecognized.append(f"Table '{ref.object_name}'")

        if unrecognized:
            msg = f"Suggested DAX references unknown model object(s): {', '.join(unrecognized[:3])}"
            logger.warning(msg)
            return "Invalid", msg

        return "Validated", ""

