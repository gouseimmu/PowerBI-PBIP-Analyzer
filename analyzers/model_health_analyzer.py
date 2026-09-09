"""Deterministic Model Health Analyzer & Score Generator.

Computes the "PBIP Analyzer Model Health Score" (0-100) and identifies major governance,
performance, and architecture factors impacting model quality.
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class ModelHealthAnalyzer:
    """Calculates deterministic model health score and compiles explainable health factors."""

    @classmethod
    def calculate_health_score(cls, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Compute 0-100 PBIP Analyzer Model Health Score with explainable factors."""
        base_score = 100
        deductions: List[Dict[str, Any]] = []

        tables = metadata.get("tables", [])
        columns = metadata.get("columns", [])
        measures = metadata.get("measures", [])
        calc_cols = metadata.get("calculated_columns", [])
        relationships = metadata.get("relationships", [])
        object_usage = metadata.get("object_usage", [])
        dax_analysis = metadata.get("dax_analysis", [])
        dax_deps = metadata.get("dax_dependencies", [])
        p2_summary = metadata.get("phase2_summary", {})
        visuals = metadata.get("visuals", [])

        # 1. Circular Dependencies (High penalty)
        circ_count = p2_summary.get("Circular Dependencies", 0)
        if circ_count > 0:
            penalty = min(25, circ_count * 10)
            base_score -= penalty
            deductions.append({
                "category": "DAX Lineage",
                "severity": "High",
                "impact": f"-{penalty} pts",
                "title": "Circular Dependencies Detected",
                "description": f"Found {circ_count} circular dependency cycle(s) in DAX formulas. Cycles can cause runtime errors or infinite loops.",
            })

        # 2. Unresolved DAX References (Medium-High penalty)
        unresolved_count = p2_summary.get("Unresolved DAX References", 0)
        if unresolved_count > 0:
            penalty = min(15, unresolved_count * 3)
            base_score -= penalty
            deductions.append({
                "category": "DAX Lineage",
                "severity": "High",
                "impact": f"-{penalty} pts",
                "title": "Unresolved DAX References",
                "description": f"Found {unresolved_count} unresolved reference(s) to missing tables, columns, or measures.",
            })

        # 3. High Unused Objects Ratio (Medium penalty)
        total_model_objects = len(object_usage)
        unused_count = p2_summary.get("Unused Objects", 0)
        if total_model_objects > 0:
            unused_ratio = unused_count / total_model_objects
            if unused_ratio > 0.3:
                penalty = min(15, int(unused_ratio * 20))
                base_score -= penalty
                deductions.append({
                    "category": "Model Bloat",
                    "severity": "Medium",
                    "impact": f"-{penalty} pts",
                    "title": "High Unused Object Ratio",
                    "description": f"{unused_count} out of {total_model_objects} objects ({unused_ratio:.0%}) are not referenced by any report visual or DAX chain.",
                })

        # 4. Excessive Calculated Columns (Performance penalty)
        num_calc_cols = len(calc_cols)
        num_cols = len(columns)
        if num_cols > 0 and num_calc_cols > 5:
            calc_ratio = num_calc_cols / num_cols
            if calc_ratio > 0.15 or num_calc_cols >= 10:
                penalty = min(10, num_calc_cols)
                base_score -= penalty
                deductions.append({
                    "category": "Performance",
                    "severity": "Medium",
                    "impact": f"-{penalty} pts",
                    "title": "Excessive Calculated Columns",
                    "description": f"Model contains {num_calc_cols} calculated columns. Prefer Power Query / M or source system transformations to save VertiPaq RAM.",
                })

        # 5. Many-to-Many & Bidirectional Relationships (Data modeling penalty)
        m_to_m = sum(1 for r in relationships if r.get("Cardinality") in ("M:M", "Many-to-Many", "1:1"))
        bidi = sum(1 for r in relationships if r.get("Filter Direction") in ("Both", "Bidirectional"))
        inactive = sum(1 for r in relationships if r.get("Status") == "Inactive")

        if m_to_m > 0:
            penalty = min(10, m_to_m * 4)
            base_score -= penalty
            deductions.append({
                "category": "Relationships",
                "severity": "Medium",
                "impact": f"-{penalty} pts",
                "title": "Many-to-Many / 1:1 Relationships",
                "description": f"Found {m_to_m} Many-to-Many or 1:1 relationship(s). These can produce unpredictable filter propagation.",
            })

        if bidi > 0:
            penalty = min(10, bidi * 3)
            base_score -= penalty
            deductions.append({
                "category": "Relationships",
                "severity": "Medium",
                "impact": f"-{penalty} pts",
                "title": "Bidirectional Cross-Filtering",
                "description": f"Found {bidi} relationship(s) set to Bidirectional filtering. Can introduce ambiguous filter paths and performance drag.",
            })

        if inactive > 3:
            penalty = min(5, inactive)
            base_score -= penalty
            deductions.append({
                "category": "Relationships",
                "severity": "Low",
                "impact": f"-{penalty} pts",
                "title": "Multiple Inactive Relationships",
                "description": f"Found {inactive} inactive relationships requiring USERELATIONSHIP() pattern management.",
            })

        # 6. High DAX Complexity / High Severity Quality Issues
        high_sev_dax = sum(1 for d in dax_analysis if d.get("Highest Severity") == "High" or d.get("Severity") == "High")
        if high_sev_dax > 0:
            penalty = min(10, high_sev_dax * 3)
            base_score -= penalty
            deductions.append({
                "category": "DAX Quality",
                "severity": "High",
                "impact": f"-{penalty} pts",
                "title": "High-Severity DAX Quality Issues",
                "description": f"{high_sev_dax} DAX object(s) have high-severity issues (e.g. FILTER over full table, unsafe division, or excessive complexity).",
            })

        final_score = max(0, min(100, base_score))

        if final_score >= 90:
            grade = "A (Excellent)"
            status_text = "Model health is excellent with strong compliance to Power BI best practices."
        elif final_score >= 75:
            grade = "B (Good)"
            status_text = "Model health is good, with minor optimization and cleanup opportunities."
        elif final_score >= 60:
            grade = "C (Fair)"
            status_text = "Model health has moderate issues requiring review."
        elif final_score >= 45:
            grade = "D (Poor)"
            status_text = "Model health has notable risks in DAX, usage, or relationships."
        else:
            grade = "F (Critical)"
            status_text = "Model health requires immediate intervention to address structural issues."

        return {
            "score": final_score,
            "grade": grade,
            "status_text": status_text,
            "deductions": deductions,
            "metric_breakdown": {
                "Circular Dependencies": circ_count,
                "Unresolved References": unresolved_count,
                "Unused Objects": unused_count,
                "Calculated Columns": num_calc_cols,
                "Bidirectional Filters": bidi,
                "Many-to-Many Relationships": m_to_m,
                "High Severity DAX Issues": high_sev_dax,
            },
        }

