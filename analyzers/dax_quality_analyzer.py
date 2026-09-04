"""Static DAX Quality Analyzer & Safe Suggestion Generator.

Deterministic rule-based quality analyzer implementing conservative best practice checks:
1. Repeated expressions / VAR caching
2. FILTER() over entire tables in CALCULATE
3. Iterator review
4. Variable usage & maintainability
5. Division safety (DIVIDE vs /)
6. Complex filter context (nested CALCULATE, USERELATIONSHIP, TREATAS, ALL)
7. Redundant CALCULATE constructs
8. Formatting and nesting depth
"""

import re
import logging
from typing import Dict, List, Set, Tuple, Optional, Any

from models.dax_analysis import (
    DAXComplexityMetrics,
    DAXQualityIssue,
    DAXImprovement,
    DAXAnalysisRecord,
)
from .dax_pattern_analyzer import DAXPatternAnalyzer, ITERATOR_FUNCTIONS
from .dax_dependency_analyzer import clean_dax_comments_and_strings, DAXDependencyAnalyzer

logger = logging.getLogger(__name__)

SEVERITY_RANKS = {
    "None": 0,
    "Informational": 1,
    "Low": 2,
    "Medium": 3,
    "High": 4,
}


class DAXQualityAnalyzer:
    """Performs deterministic static analysis on DAX formulas and generates conservative suggestions."""

    @classmethod
    def analyze_expression(
        cls,
        object_type: str,
        table: str,
        object_name: str,
        dax: str,
        complexity: Optional[DAXComplexityMetrics] = None,
    ) -> Tuple[List[DAXQualityIssue], str]:
        """Analyze a DAX expression and return a list of detected quality issues and highest severity."""
        if not dax or dax == "Unknown":
            return [], "None"

        if complexity is None:
            complexity = DAXPatternAnalyzer.analyze_complexity(dax)

        trimmed_dax = dax.strip()
        masked_dax, _ = clean_dax_comments_and_strings(trimmed_dax)

        issues: List[DAXQualityIssue] = []

        # 1. Check Division Safety (Rule Category 5)
        cls._check_division_safety(trimmed_dax, masked_dax, issues)

        # 2. Check Redundant CALCULATE (Rule Category 7)
        cls._check_redundant_calculate(trimmed_dax, masked_dax, issues)

        # 3. Check FILTER over full table in CALCULATE (Rule Category 2)
        cls._check_filter_table_pattern(trimmed_dax, masked_dax, issues)

        # 4. Check Repeated Expressions without VAR (Rule Category 1)
        cls._check_repeated_expressions(trimmed_dax, masked_dax, complexity, issues)

        # 5. Check Iterators (Rule Category 3)
        cls._check_iterators(masked_dax, issues)

        # 6. Check Variable Usage on Complex DAX (Rule Category 4)
        cls._check_variable_usage(trimmed_dax, masked_dax, complexity, issues)

        # 7. Check Context Modifiers & Nested CALCULATE (Rule Category 6)
        cls._check_filter_context_modifiers(masked_dax, complexity, issues)

        # 8. Check Maintainability / Nesting (Rule Category 8)
        cls._check_maintainability(trimmed_dax, complexity, issues)

        # Compute highest severity
        highest_severity = "None"
        for issue in issues:
            if SEVERITY_RANKS.get(issue.severity, 0) > SEVERITY_RANKS.get(highest_severity, 0):
                highest_severity = issue.severity

        return issues, highest_severity

    @classmethod
    def _check_division_safety(cls, original_dax: str, masked_dax: str, issues: List[DAXQualityIssue]) -> None:
        """Rule 5: Check if '/' operator is used for division instead of DIVIDE()."""
        # Look for '/' not preceded or followed by other operators
        div_pattern = r"(?<![\/\*])\s*\/\s*(?![\/\*])"
        if re.search(div_pattern, masked_dax):
            # Check if DIVIDE() can be safely suggested for simple 'A / B' or 'SUM(...) / SUM(...)'
            simple_div_match = re.match(r"^\s*([A-Za-z0-9_\[\]\.'\(\)\s\n]+?)\s*\/\s*([A-Za-z0-9_\[\]\.'\(\)\s\n]+?)\s*$", original_dax, re.DOTALL)
            suggested_dax = None
            val_status = "No Suggestion"

            if simple_div_match and ";" not in original_dax and "VAR" not in original_dax.upper():
                num = simple_div_match.group(1).strip()
                den = simple_div_match.group(2).strip()
                suggested_dax = f"DIVIDE({num}, {den}, 0)"
                val_status = "Validated"
            else:
                suggested_dax = "Manual review required: replace '/' with DIVIDE(Numerator, Denominator)"
                val_status = "Needs Review"

            issues.append(DAXQualityIssue(
                category="Reliability",
                severity="Medium" if "DIVIDE" not in original_dax.upper() else "Low",
                issue="Division operator '/' used instead of DIVIDE()",
                explanation="The standard division operator '/' returns an error or infinity on divide-by-zero or empty values.",
                recommendation="Consider using the native DIVIDE(Numerator, Denominator) function for safer zero/blank denominator handling.",
                suggested_dax=suggested_dax,
                confidence="High" if val_status == "Validated" else "Medium",
                source="Static Rule",
                validation_status=val_status,
                requires_manual_validation=True,
            ))

    @classmethod
    def _check_redundant_calculate(cls, original_dax: str, masked_dax: str, issues: List[DAXQualityIssue]) -> None:
        """Rule 7: Check for CALCULATE wrapper without filter arguments."""
        match = re.match(r"^\s*CALCULATE\s*\(\s*([A-Za-z0-9_\[\]\.'\(\)\s,\"]+?)\s*\)\s*$", original_dax, re.IGNORECASE)
        if match:
            inner_expr = match.group(1).strip()
            # If no commas separating filter arguments outside inner parentheses
            # Check if inner has top-level commas
            depth = 0
            has_top_comma = False
            for char in inner_expr:
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                elif char == "," and depth == 0:
                    has_top_comma = True
                    break

            if not has_top_comma:
                issues.append(DAXQualityIssue(
                    category="Performance",
                    severity="Low",
                    issue="Redundant CALCULATE wrapper without filter arguments",
                    explanation="CALCULATE is used without any filter arguments, which adds unnecessary context transition overhead when not evaluating row context.",
                    recommendation="Remove the outer CALCULATE() wrapper and evaluate the base expression directly.",
                    suggested_dax=inner_expr,
                    confidence="High",
                    source="Static Rule",
                    validation_status="Validated",
                    requires_manual_validation=True,
                ))

    @classmethod
    def _check_filter_table_pattern(cls, original_dax: str, masked_dax: str, issues: List[DAXQualityIssue]) -> None:
        """Rule 2: Check for FILTER(Table, Table[Col] = ...) inside CALCULATE."""
        # Pattern: CALCULATE( ..., FILTER( Table, Table[Col] == ... ) )
        filter_over_table_match = re.search(
            r"FILTER\s*\(\s*(?:'([^']+)'|([a-zA-Z0-9_]+))\s*,\s*(?:'([^']+)'|([a-zA-Z0-9_]+))?\[([^\]]+)\]\s*(=|==|<>|<|>|<=|>=)\s*([^,\)]+)\)",
            masked_dax,
            re.IGNORECASE,
        )
        if filter_over_table_match:
            table_name = filter_over_table_match.group(1) or filter_over_table_match.group(2)
            col_name = filter_over_table_match.group(5)
            op = filter_over_table_match.group(6)
            val = filter_over_table_match.group(7).strip()

            # Generate suggested predicate if simple
            suggested_predicate = f"{table_name}[{col_name}] {op} {val}"
            suggested_dax = f"Review filter argument: use '{suggested_predicate}' directly inside CALCULATE without wrapping the full table in FILTER()."

            issues.append(DAXQualityIssue(
                category="Performance",
                severity="Medium",
                issue=f"FILTER() used over entire table '{table_name}' inside filter context",
                explanation=f"Filtering the entire table '{table_name}' creates a materialization of all table columns rather than applying a simple column-level predicate filter.",
                recommendation=f"Review whether a direct boolean filter predicate ({table_name}[{col_name}] {op} {val}) or KEEPFILTERS() can be used inside CALCULATE.",
                suggested_dax=suggested_dax,
                confidence="Medium",
                source="Static Rule",
                validation_status="Needs Review",
                requires_manual_validation=True,
            ))

    @classmethod
    def _check_repeated_expressions(cls, original_dax: str, masked_dax: str, complexity: DAXComplexityMetrics, issues: List[DAXQualityIssue]) -> None:
        """Rule 1: Check for repeated measure calls or complex expressions without VAR."""
        refs = DAXDependencyAnalyzer.extract_dax_references(original_dax)
        ref_counts: Dict[str, int] = {}
        for r in refs:
            ref_counts[r.raw_text] = ref_counts.get(r.raw_text, 0) + 1

        repeated_refs = [k for k, v in ref_counts.items() if v >= 2]

        if repeated_refs and complexity.var_count == 0:
            repeated_list_str = ", ".join(repeated_refs[:3])
            issues.append(DAXQualityIssue(
                category="Performance",
                severity="Medium" if len(repeated_refs) > 1 or complexity.function_count > 2 else "Low",
                issue=f"Repeated reference(s) ({repeated_list_str}) evaluated multiple times without VAR",
                explanation="The expression calculates or evaluates the same measure/column multiple times in the same execution context without variable caching.",
                recommendation="Store repeated sub-calculations in a VAR declaration to calculate the value once and reuse it.",
                suggested_dax="Manual review required: declare VAR for repeated expression",
                confidence="Medium",
                source="Static Rule",
                validation_status="Needs Review",
                requires_manual_validation=True,
            ))

    @classmethod
    def _check_iterators(cls, masked_dax: str, issues: List[DAXQualityIssue]) -> None:
        """Rule 3: Check for iterator function usage (SUMX, AVERAGEX, etc.)."""
        for it in ["SUMX", "AVERAGEX", "MINX", "MAXX", "COUNTX", "RANKX"]:
            if re.search(rf"\b{it}\s*\(", masked_dax, re.IGNORECASE):
                issues.append(DAXQualityIssue(
                    category="Performance",
                    severity="Informational",
                    issue=f"Iterator function {it}() detected",
                    explanation=f"{it} iterates row-by-row over a table to evaluate the expression. This is normal for row-context calculations but can impact performance on large fact tables.",
                    recommendation="Review whether a native aggregation function (e.g. SUM, AVERAGE) or a pre-calculated column can achieve the same result more efficiently.",
                    suggested_dax="Manual review required: verify if native aggregation can be used",
                    confidence="Low",
                    source="Static Rule",
                    validation_status="Needs Review",
                    requires_manual_validation=True,
                ))

    @classmethod
    def _check_variable_usage(cls, original_dax: str, masked_dax: str, complexity: DAXComplexityMetrics, issues: List[DAXQualityIssue]) -> None:
        """Rule 4: Check if complex DAX expression lacks VAR declarations."""
        # Do not recommend VAR for simple CALCULATE + USERELATIONSHIP or basic single/double step formulas
        is_userelationship = "USERELATIONSHIP" in masked_dax.upper()
        is_simple_userelation = is_userelationship and complexity.function_count <= 3 and complexity.nesting_depth <= 2

        if not is_simple_userelation and complexity.var_count == 0 and (complexity.function_count >= 5 or complexity.nesting_depth >= 3) and complexity.line_count >= 10:
            issues.append(DAXQualityIssue(
                category="Maintainability",
                severity="Low",
                issue="Complex multi-step expression without VAR declarations",
                explanation="The DAX formula contains multiple nested functions or logic steps but does not use variables to structure intermediate results.",
                recommendation="Break down complex formulas into named VAR declarations to enhance readability, ease debugging, and allow step-by-step verification.",
                suggested_dax="Manual review required: structure intermediate steps into VARs",
                confidence="Medium",
                source="Static Rule",
                validation_status="Needs Review",
                requires_manual_validation=True,
            ))

    @classmethod
    def _check_filter_context_modifiers(cls, masked_dax: str, complexity: DAXComplexityMetrics, issues: List[DAXQualityIssue]) -> None:
        """Rule 6: Check for nested CALCULATE or complex context modifiers (USERELATIONSHIP, TREATAS, ALL)."""
        if complexity.calculate_count >= 2:
            issues.append(DAXQualityIssue(
                category="Maintainability",
                severity="Low",
                issue="Nested CALCULATE() expressions detected",
                explanation="Multiple CALCULATE functions are nested within the same formula, which can create complex context transitions and make filter behavior harder to trace.",
                recommendation="Review whether nested CALCULATE calls can be simplified or separated into intermediate variables.",
                suggested_dax="Manual review required",
                confidence="Low",
                source="Static Rule",
                validation_status="Needs Review",
                requires_manual_validation=True,
            ))

        for mod in ["USERELATIONSHIP", "TREATAS", "ALLEXCEPT", "REMOVEFILTERS"]:
            if re.search(rf"\b{mod}\s*\(", masked_dax, re.IGNORECASE):
                expl = (
                    "Uses an inactive relationship for role-playing/date analysis."
                    if mod == "USERELATIONSHIP"
                    else f"{mod}() modifies standard relationship or filter context behavior."
                )
                issues.append(DAXQualityIssue(
                    category="Context Transition",
                    severity="Informational",
                    issue=f"Filter context modifier {mod}() detected",
                    explanation=expl,
                    recommendation=f"Ensure that {mod}() interactions with visual filters and active model relationships have been tested for expected boundary conditions.",
                    suggested_dax="No change required; informational review only",
                    confidence="High",
                    source="Static Rule",
                    validation_status="No Suggestion",
                    requires_manual_validation=False,
                ))

    @classmethod
    def _check_maintainability(cls, original_dax: str, complexity: DAXComplexityMetrics, issues: List[DAXQualityIssue]) -> None:
        """Rule 8: Check for deep nesting and formatting."""
        if complexity.nesting_depth >= 4:
            issues.append(DAXQualityIssue(
                category="Maintainability",
                severity="Low",
                issue=f"Deep nesting depth ({complexity.nesting_depth} levels)",
                explanation="Deeply nested parentheses and function calls make the calculation difficult to read and maintain.",
                recommendation="Refactor nested calculations into sequential VAR declarations or evaluate if SWITCH(TRUE(), ...) is suitable for conditional branches.",
                suggested_dax="Manual review required: simplify nesting with VAR or SWITCH",
                confidence="Medium",
                source="Static Rule",
                validation_status="Needs Review",
                requires_manual_validation=True,
            ))
