"""DAX Pattern & Complexity Analyzer.

Calculates deterministic complexity metrics, token occurrences, function usage,
nesting depth, and repeated sub-expressions for DAX expressions.
"""

import re
import logging
from typing import Dict, List, Set, Tuple, Any
from models.dax_analysis import DAXComplexityMetrics
from .dax_dependency_analyzer import clean_dax_comments_and_strings, DAXDependencyAnalyzer

logger = logging.getLogger(__name__)

# Standard DAX Iterator Functions
ITERATOR_FUNCTIONS = {
    "SUMX", "AVERAGEX", "MINX", "MAXX", "COUNTX", "COUNTAX",
    "MEDIANX", "CONCATENATEX", "RANKX", "GEOMEANX", "PRODUCTX",
    "FILTER", "ADDCOLUMNS", "SELECTCOLUMNS", "GENERATE", "GENERATEX",
}


class DAXPatternAnalyzer:
    """Computes deterministic complexity metrics and structural statistics for a DAX expression."""

    @classmethod
    def analyze_complexity(cls, dax: str) -> DAXComplexityMetrics:
        """Compute all complexity metrics for the given DAX code."""
        if not dax or dax == "Unknown":
            return DAXComplexityMetrics()

        trimmed_dax = dax.strip()
        char_count = len(trimmed_dax)
        lines = [line for line in trimmed_dax.splitlines() if line.strip()]
        line_count = max(len(lines), 1)

        masked_dax, _ = clean_dax_comments_and_strings(trimmed_dax)

        # 1. Function counting: words followed by '('
        function_matches = re.findall(r"\b([a-zA-Z0-9_\.]+)\s*\(", masked_dax)
        functions_upper = [f.upper() for f in function_matches]
        function_count = len(functions_upper)

        # 2. Specific keywords
        calculate_count = sum(1 for f in functions_upper if f in ["CALCULATE", "CALCULATETABLE"])
        filter_count = sum(1 for f in functions_upper if f == "FILTER")
        iterator_count = sum(1 for f in functions_upper if f in ITERATOR_FUNCTIONS)
        var_count = len(re.findall(r"\bVAR\b", masked_dax, re.IGNORECASE))

        # 3. Nesting depth (parentheses depth)
        nesting_depth = cls._calculate_max_nesting_depth(masked_dax)

        # 4. References count
        refs = DAXDependencyAnalyzer.extract_dax_references(trimmed_dax)
        ref_measures = sum(1 for r in refs if r.ref_type == "unqualified_bracket")
        ref_columns = sum(1 for r in refs if r.ref_type == "qualified_column")
        ref_tables = sum(1 for r in refs if r.ref_type == "table")

        # 5. Repeated expressions count
        repeated_count = cls._count_repeated_subexpressions(trimmed_dax, refs)

        # 6. Composite Complexity Score
        complexity_score = round(
            (char_count / 100.0)
            + (function_count * 1.5)
            + (calculate_count * 2.0)
            + (iterator_count * 2.5)
            + (nesting_depth * 1.5)
            + (repeated_count * 1.0),
            1,
        )

        return DAXComplexityMetrics(
            character_count=char_count,
            line_count=line_count,
            function_count=function_count,
            referenced_measures=ref_measures,
            referenced_columns=ref_columns,
            referenced_tables=ref_tables,
            calculate_count=calculate_count,
            filter_count=filter_count,
            iterator_count=iterator_count,
            var_count=var_count,
            nesting_depth=nesting_depth,
            repeated_expressions_count=repeated_count,
            complexity_score=complexity_score,
        )

    @classmethod
    def _calculate_max_nesting_depth(cls, masked_dax: str) -> int:
        """Calculate the maximum nesting depth of parentheses in DAX."""
        max_depth = 0
        current_depth = 0
        for char in masked_dax:
            if char == "(":
                current_depth += 1
                if current_depth > max_depth:
                    max_depth = current_depth
            elif char == ")":
                if current_depth > 0:
                    current_depth -= 1
        return max_depth

    @classmethod
    def _count_repeated_subexpressions(cls, dax: str, refs: List[Any]) -> int:
        """Identify sub-expressions or measure references that appear more than once."""
        counts: Dict[str, int] = {}
        for r in refs:
            key = r.raw_text.strip()
            counts[key] = counts.get(key, 0) + 1

        # Count items that appear >= 2 times
        repeated = sum(1 for k, v in counts.items() if v >= 2)
        return repeated

