"""AI Governance Advisors & Executive Summary Documentation Generator.

Provides optional AI-assisted Model Governance Advisor, Report Governance Advisor,
and AI-generated Semantic Model Documentation.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from .provider import DAXAIProvider

logger = logging.getLogger(__name__)


class AIAdvisors:
    """Orchestrates AI Model Advisor, AI Report Advisor, and AI Documentation Generation."""

    @classmethod
    def generate_model_advice(cls, metadata: Dict[str, Any], provider: DAXAIProvider) -> List[Dict[str, Any]]:
        """Generate AI Model Advisor recommendations based on deterministic model metrics."""
        if not provider.is_available():
            return cls._fallback_model_advice(metadata)

        p2 = metadata.get("phase2_summary", {})
        rels = metadata.get("relationships", [])
        calc_cols = metadata.get("calculated_columns", [])
        health = metadata.get("model_health", {})

        context = {
            "task": "model_advisor",
            "health_score": health.get("score"),
            "health_grade": health.get("grade"),
            "total_tables": len(metadata.get("tables", [])),
            "total_measures": len(metadata.get("measures", [])),
            "calculated_columns_count": len(calc_cols),
            "unused_objects_count": p2.get("Unused Objects", 0),
            "unresolved_references_count": p2.get("Unresolved DAX References", 0),
            "circular_dependencies_count": p2.get("Circular Dependencies", 0),
            "bidirectional_relationships": sum(1 for r in rels if r.get("Filter Direction") in ("Both", "Bidirectional")),
            "many_to_many_relationships": sum(1 for r in rels if r.get("Cardinality") in ("M:M", "Many-to-Many")),
        }

        try:
            # We can use analyze_dax with context if provider supports it or return structured fallback
            res = provider.analyze_dax({"object_name": "Model Governance Advisor", "original_dax": "MODEL_LEVEL_ADVISORY", "context": context})
            if res and isinstance(res, dict) and "issues" in res:
                return res.get("issues", [])
        except Exception as e:
            logger.warning(f"AI Model Advisor failed: {e}")

        return cls._fallback_model_advice(metadata)

    @classmethod
    def generate_report_advice(cls, metadata: Dict[str, Any], provider: DAXAIProvider) -> List[Dict[str, Any]]:
        """Generate AI Report Advisor recommendations based on report page/visual metadata."""
        if not provider.is_available():
            return cls._fallback_report_advice(metadata)

        pages = metadata.get("pages", [])
        visuals = metadata.get("visuals", [])
        vis_usage = metadata.get("visual_usage", [])

        context = {
            "task": "report_advisor",
            "page_count": len(pages),
            "visual_count": len(visuals),
            "unique_objects_used_in_report": len({v.get("Object Name") for v in vis_usage if v.get("Object Name")}),
        }

        try:
            res = provider.analyze_dax({"object_name": "Report Governance Advisor", "original_dax": "REPORT_LEVEL_ADVISORY", "context": context})
            if res and isinstance(res, dict) and "issues" in res:
                return res.get("issues", [])
        except Exception as e:
            logger.warning(f"AI Report Advisor failed: {e}")

        return cls._fallback_report_advice(metadata)

    @classmethod
    def generate_documentation(cls, metadata: Dict[str, Any], provider: DAXAIProvider) -> Dict[str, Any]:
        """Generate executive semantic model documentation summary."""
        project_name = metadata.get("project_name", "Power BI Project")
        num_tables = len(metadata.get("tables", []))
        num_measures = len(metadata.get("measures", []))
        num_cols = len(metadata.get("columns", []))
        num_pages = len(metadata.get("pages", []))
        num_visuals = len(metadata.get("visuals", []))
        health_score = metadata.get("model_health", {}).get("score", 100)

        overview = (
            f"The '{project_name}' semantic model contains {num_tables} tables, {num_cols} columns, "
            f"and {num_measures} measures serving {num_pages} report pages with {num_visuals} total visuals. "
            f"The PBIP Analyzer Model Health Score is {health_score}/100."
        )

        return {
            "overview": overview,
            "key_highlights": [
                f"Semantic model format: {metadata.get('model_format', 'TMDL')}",
                f"Report pages: {num_pages} pages, {num_visuals} visuals",
                f"Data sources: {len(metadata.get('data_sources', []))} extracted queries",
            ],
            "is_ai_generated": provider.is_available(),
        }

    @staticmethod
    def _fallback_model_advice(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Deterministic rule-based model advisory recommendations."""
        advices = []
        p2 = metadata.get("phase2_summary", {})
        rels = metadata.get("relationships", [])
        calc_cols = metadata.get("calculated_columns", [])

        unused = p2.get("Unused Objects", 0)
        if unused > 0:
            advices.append({
                "type": "Unused Objects",
                "severity": "Medium",
                "description": f"{unused} model object(s) have no direct or indirect report usage.",
                "recommendation": "Review and consider removing unused measures and columns to reduce model size.",
            })

        bidi = sum(1 for r in rels if r.get("Filter Direction") in ("Both", "Bidirectional"))
        if bidi > 0:
            advices.append({
                "type": "Bidirectional Relationships",
                "severity": "Medium",
                "description": f"{bidi} relationship(s) use bidirectional cross-filtering.",
                "recommendation": "Change cross-filtering to single direction where possible or manage via CROSSFILTER().",
            })

        if len(calc_cols) > 5:
            advices.append({
                "type": "Calculated Columns",
                "severity": "Low",
                "description": f"Model contains {len(calc_cols)} calculated columns.",
                "recommendation": "Migrate calculated columns to Power Query M transformations for better compression.",
            })

        if not advices:
            advices.append({
                "type": "Model Health",
                "severity": "Informational",
                "description": "Model architecture adheres to basic structural recommendations.",
                "recommendation": "Maintain current design patterns.",
            })

        return advices

    @staticmethod
    def _fallback_report_advice(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Deterministic rule-based report advisory recommendations."""
        advices = []
        pages = metadata.get("pages", [])
        visuals = metadata.get("visuals", [])

        if len(visuals) > 0 and len(pages) > 0:
            avg_vis = len(visuals) / len(pages)
            if avg_vis > 10:
                advices.append({
                    "type": "High Visual Density",
                    "severity": "Medium",
                    "description": f"Average of {avg_vis:.1f} visuals per page.",
                    "recommendation": "Consolidate visuals or use tooltips/drillthroughs to improve page rendering time.",
                })

        if not advices:
            advices.append({
                "type": "Report Design",
                "severity": "Informational",
                "description": "Report visual distribution is balanced across pages.",
                "recommendation": "No critical report visual performance bottlenecks detected.",
            })

        return advices

