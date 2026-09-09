"""DAX Optimizer Orchestrator.

Combines deterministic static analysis with optional AI-assisted optimization,
caches responses, and compiles Sheet 16 (DAX Analysis), Sheet 17 (DAX Improvements),
and Sheet 18 (DAX Complexity) data.
caches responses per run, enforces request limits, and compiles DAX analysis records.
"""

import hashlib
import json
import logging
from typing import Dict, List, Set, Tuple, Optional, Any

from models.dax_analysis import (
    DAXComplexityMetrics,
    DAXQualityIssue,
    DAXImprovement,
    DAXAnalysisRecord,
)
from analyzers.dax_pattern_analyzer import DAXPatternAnalyzer
from analyzers.dax_quality_analyzer import DAXQualityAnalyzer, SEVERITY_RANKS
from analyzers.dax_dependency_analyzer import ModelCatalog
from analyzers.dax_dependency_analyzer import ModelCatalog, DAXDependencyAnalyzer
from .provider import DAXAIProvider, get_ai_provider
from .response_parser import AIResponseParser

logger = logging.getLogger(__name__)


class DAXOptimizer:
    """Orchestrates static quality checks, complexity metrics, and optional AI enhancement."""

    def __init__(
        self,
        catalog: ModelCatalog,
        measures: List[Dict[str, Any]],
        calc_columns: List[Dict[str, Any]],
        object_usage_map: Dict[str, Dict[str, Any]],
        ai_provider: Optional[DAXAIProvider] = None,
        max_ai_requests: int = 50,
    ):
        self.catalog = catalog
        self.measures = measures
        self.calc_columns = calc_columns
        self.object_usage_map = object_usage_map
        self.ai_provider = ai_provider if ai_provider is not None else get_ai_provider()
        self.max_ai_requests = max_ai_requests

        self._ai_cache: Dict[str, Any] = {}
        self.ai_requests_sent = 0
        self.analysis_records: List[DAXAnalysisRecord] = []
        self.improvements: List[DAXImprovement] = []
        self.complexity_records: List[Dict[str, Any]] = []

        self.ai_suggestions_count = 0
        self.static_suggestions_count = 0
        self.ai_failures_count = 0
        self.manual_validation_count = 0

        self._run_optimization_pipeline()

    def _run_optimization_pipeline(self) -> None:
        """Analyze all measures and calculated columns."""
        total_analyzed = 0
        ai_requests_sent = 0

        # 1. Process Measures
        for m in self.measures:
            tname = m.get("Table", "")
            mname = m.get("Measure Name", "")
            dax = m.get("DAX Expression", "")
            self._analyze_single_object("Measure", tname, mname, dax)
            total_analyzed += 1

        # 2. Process Calculated Columns
        for cc in self.calc_columns:
            tname = cc.get("Table", "")
            cname = cc.get("Column", "")
            dax = cc.get("DAX Expression", "")
            self._analyze_single_object("Calculated Column", tname, cname, dax)
            total_analyzed += 1

        logger.info(
            f"DAX Optimization complete: {total_analyzed} objects analyzed, {self.ai_requests_sent} AI requests sent, {len(self.improvements)} suggestions generated."
        )

    def _analyze_single_object(self, obj_type: str, table: str, name: str, dax: str) -> None:
        """Analyze one DAX formula through static checks and optional AI."""
        if not dax or dax == "Unknown":
            return

        # 1. Complexity Metrics
        complexity = DAXPatternAnalyzer.analyze_complexity(dax)

        # 2. Static Quality Rules
        static_issues, static_highest = DAXQualityAnalyzer.analyze_expression(obj_type, table, name, dax, complexity)

        # 3. Optional AI-Assisted Optimization
        ai_issue: Optional[DAXQualityIssue] = None
        analysis_status = "Static Complete"

        if self.ai_provider.is_available():
            # Build relevant dependency context instead of full model catalog
            relevant_deps = self._get_relevant_dependencies(dax, table)
            context_str = f"{obj_type}:{table}:{name}:{dax}:" + ",".join(sorted(relevant_deps))
            cache_key = hashlib.sha256(context_str.encode()).hexdigest()

            raw_ai_res = None

            if cache_key in self._ai_cache:
                raw_ai_res = self._ai_cache[cache_key]
                logger.debug(f"Using cached AI response for {name}")
            elif self.ai_requests_sent < self.max_ai_requests:
                context = {
                    "object_name": f"[{name}]" if obj_type == "Measure" else f"{table}[{name}]",
                    "object_type": obj_type,
                    "table": table,
                    "original_dax": dax,
                    "dependencies": relevant_deps,
                    "static_issues": [{"issue": i.issue, "severity": i.severity, "explanation": i.explanation} for i in static_issues],
                    "usage_summary": self._get_usage_summary(obj_type, table, name),
                }
                try:
                    self.ai_requests_sent += 1
                    raw_ai_res = self.ai_provider.analyze_dax(context)
                    if raw_ai_res:
                        self._ai_cache[cache_key] = raw_ai_res
                except Exception as e:
                    logger.warning(f"AI provider failed for {name}: {e}")
                    self.ai_failures_count += 1
            else:
                logger.info(f"Max AI requests ({self.max_ai_requests}) reached. Skipping AI call for {name}.")

            if raw_ai_res:
                ai_issue = AIResponseParser.parse_and_validate(raw_ai_res, self.catalog, table)
                if ai_issue:
                    analysis_status = "AI Enhanced"
                    self.ai_suggestions_count += 1

        # 4. Merge Issues
        all_issues = list(static_issues)
        if ai_issue:
            all_issues.append(ai_issue)

        highest_severity = "None"
        for issue in all_issues:
            if SEVERITY_RANKS.get(issue.severity, 0) > SEVERITY_RANKS.get(highest_severity, 0):
                highest_severity = issue.severity

        # 5. Usage context lookup
        can_key = f"{obj_type.upper()}:{table}[{name}]"
        usage_info = self.object_usage_map.get(name, self.object_usage_map.get(can_key, {}))
        used_val = usage_info.get("Used", "No")
        usage_type_val = usage_info.get("Usage Type", "Unused")
        direct_count_val = usage_info.get("Direct Usage Count", 0)
        indirect_count_val = usage_info.get("Indirect Usage Count", 0)

        # 6. Build Sheet 16 Analysis Record
        # 6. Build Analysis Record
        self.analysis_records.append(DAXAnalysisRecord(
            object_type=obj_type,
            table=table,
            object_name=name,
            original_dax=dax,
            used=used_val,
            usage_type=usage_type_val,
            direct_usage_count=direct_count_val,
            indirect_usage_count=indirect_count_val,
            dependency_count=complexity.referenced_measures + complexity.referenced_columns,
            complexity_score=complexity.complexity_score,
            character_count=complexity.character_count,
            line_count=complexity.line_count,
            function_count=complexity.function_count,
            calculate_count=complexity.calculate_count,
            filter_count=complexity.filter_count,
            iterator_count=complexity.iterator_count,
            var_count=complexity.var_count,
            issue_count=len(all_issues),
            highest_severity=highest_severity,
            analysis_status=analysis_status,
        ))

        # 7. Build Sheet 17 Improvements Records
        # 7. Build Improvements Records
        for issue in all_issues:
            if issue.source == "Static Rule":
                self.static_suggestions_count += 1
            if issue.requires_manual_validation:
                self.manual_validation_count += 1

            self.improvements.append(DAXImprovement(
                object_type=obj_type,
                table=table,
                object_name=name,
                original_dax=dax,
                issue_category=issue.category,
                severity=issue.severity,
                issue=issue.issue,
                explanation=issue.explanation,
                recommendation=issue.recommendation,
                suggested_dax=issue.suggested_dax if issue.suggested_dax else "No safe automatic rewrite",
                confidence=issue.confidence,
                source=issue.source,
                validation_status=issue.validation_status,
                requires_manual_validation="Yes" if issue.requires_manual_validation else "No",
            ))

        # 8. Build Sheet 18 Complexity Record
        # 8. Build Complexity Record
        self.complexity_records.append({
            "Object Type": obj_type,
            "Table": table,
            "Object Name": name,
            "Character Count": complexity.character_count,
            "Line Count": complexity.line_count,
            "Function Count": complexity.function_count,
            "Referenced Measures": complexity.referenced_measures,
            "Referenced Columns": complexity.referenced_columns,
            "Referenced Tables": complexity.referenced_tables,
            "CALCULATE Count": complexity.calculate_count,
            "FILTER Count": complexity.filter_count,
            "Iterator Count": complexity.iterator_count,
            "VAR Count": complexity.var_count,
            "Nesting Depth": complexity.nesting_depth,
            "Complexity Score": complexity.complexity_score,
        })

    def _get_relevant_dependencies(self, dax: str, context_table: str) -> List[str]:
        """Extract only direct model references from DAX to keep prompt context minimal."""
        deps = set()
        refs = DAXDependencyAnalyzer.extract_dax_references(dax)
        for ref in refs:
            if ref.ref_type == "qualified_column":
                res = self.catalog.resolve_qualified_column(ref.table_name or "", ref.object_name)
                if res:
                    deps.add(f"'{res[0]}'[{res[1]}]")
            elif ref.ref_type == "unqualified_bracket":
                res = self.catalog.resolve_unqualified(ref.object_name, context_table)
                if res:
                    deps.add(f"[{res[1]}]" if res[2] == "Measure" else f"'{res[0]}'[{res[1]}]")
        return list(deps)

    def _get_usage_summary(self, obj_type: str, table: str, name: str) -> str:
        """Format usage context string for prompts."""
        usage_info = self.object_usage_map.get(name, {})
        u_type = usage_info.get("Usage Type", "Unused")
        loc_count = usage_info.get("Usage Location Count", 0)
        return f"{u_type} (used across {loc_count} visual locations)"

    def get_analysis_sheet_data(self) -> List[Dict[str, Any]]:
        """Return data for Sheet 16: DAX Analysis."""
        """Return data for DAX Analysis sheet."""
        return [
            {
                "Object Type": r.object_type,
                "Table": r.table,
                "Object Name": r.object_name,
                "Original DAX": r.original_dax,
                "Used": r.used,
                "Usage Type": r.usage_type,
                "Direct Usage Count": r.direct_usage_count,
                "Indirect Usage Count": r.indirect_usage_count,
                "Dependency Count": r.dependency_count,
                "Complexity Score": r.complexity_score,
                "Character Count": r.character_count,
                "Line Count": r.line_count,
                "Function Count": r.function_count,
                "CALCULATE Count": r.calculate_count,
                "FILTER Count": r.filter_count,
                "Iterator Count": r.iterator_count,
                "VAR Count": r.var_count,
                "Issue Count": r.issue_count,
                "Highest Severity": r.highest_severity,
                "Analysis Status": r.analysis_status,
            }
            for r in self.analysis_records
        ]

    def get_improvements_sheet_data(self) -> List[Dict[str, Any]]:
        """Return data for Sheet 17: DAX Improvements."""
        """Return data for DAX Improvements."""
        return [
            {
                "Object Type": imp.object_type,
                "Table": imp.table,
                "Object Name": imp.object_name,
                "Original DAX": imp.original_dax,
                "Issue Category": imp.issue_category,
                "Severity": imp.severity,
                "Issue": imp.issue,
                "Explanation": imp.explanation,
                "Recommendation": imp.recommendation,
                "Suggested DAX": imp.suggested_dax,
                "Confidence": imp.confidence,
                "Source": imp.source,
                "Validation Status": imp.validation_status,
                "Requires Manual Validation": imp.requires_manual_validation,
            }
            for imp in self.improvements
        ]

    def get_complexity_sheet_data(self) -> List[Dict[str, Any]]:
        """Return data for Sheet 18: DAX Complexity."""
        """Return data for DAX Complexity."""
        return self.complexity_records

    def get_phase3_summary_metrics(self) -> Dict[str, Any]:
        """Compute Phase 3 metrics for the Executive Summary sheet."""
        """Compute summary metrics."""
        total_analyzed = len(self.analysis_records)
        measures_analyzed = sum(1 for r in self.analysis_records if r.object_type == "Measure")
        calc_cols_analyzed = sum(1 for r in self.analysis_records if r.object_type == "Calculated Column")
        objects_with_improvements = sum(1 for r in self.analysis_records if r.issue_count > 0)

        high_sev = sum(1 for imp in self.improvements if imp.severity == "High")
        med_sev = sum(1 for imp in self.improvements if imp.severity == "Medium")
        low_sev = sum(1 for imp in self.improvements if imp.severity == "Low")
        info_sev = sum(1 for imp in self.improvements if imp.severity == "Informational")

        return {
            "DAX Objects Analyzed": total_analyzed,
            "Measures Analyzed": measures_analyzed,
            "Calculated Columns Analyzed": calc_cols_analyzed,
            "Objects With Potential Improvements": objects_with_improvements,
            "High Severity Issues": high_sev,
            "Medium Severity Issues": med_sev,
            "Low Severity Issues": low_sev,
            "Informational Findings": info_sev,
            "AI Suggestions": self.ai_suggestions_count,
            "Static Suggestions": self.static_suggestions_count,
            "AI Failures": self.ai_failures_count,
            "AI Requests Sent": self.ai_requests_sent,
            "Suggestions Requiring Manual Validation": self.manual_validation_count,
        }

