"""Data structures for DAX quality analysis, complexity indicators, and optimization recommendations."""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


@dataclass
class DAXComplexityMetrics:
    """Deterministic complexity indicators for a DAX expression."""
    character_count: int = 0
    line_count: int = 1
    function_count: int = 0
    referenced_measures: int = 0
    referenced_columns: int = 0
    referenced_tables: int = 0
    calculate_count: int = 0
    filter_count: int = 0
    iterator_count: int = 0
    var_count: int = 0
    nesting_depth: int = 0
    repeated_expressions_count: int = 0
    complexity_score: float = 0.0


@dataclass
class DAXQualityIssue:
    """A specific potential issue or observation detected in a DAX expression."""
    category: str  # 'Performance', 'Reliability', 'Maintainability', 'Readability', 'Context Transition'
    severity: str  # 'High', 'Medium', 'Low', 'Informational'
    issue: str
    explanation: str
    recommendation: str
    suggested_dax: Optional[str] = None
    confidence: str = "Medium"  # 'High', 'Medium', 'Low'
    source: str = "Static Rule"  # 'Static Rule', 'AI', 'Static Rule + AI'
    validation_status: str = "Needs Review"  # 'Validated', 'Needs Review', 'Invalid', 'No Suggestion'
    requires_manual_validation: bool = True


@dataclass
class DAXImprovement:
    """A structured improvement recommendation item for Excel Sheet 17."""
    object_type: str
    table: str
    object_name: str
    original_dax: str
    issue_category: str
    severity: str
    issue: str
    explanation: str
    recommendation: str
    suggested_dax: str
    confidence: str
    source: str
    validation_status: str
    requires_manual_validation: str


@dataclass
class DAXAnalysisRecord:
    """Summary analysis record for Excel Sheet 16."""
    object_type: str
    table: str
    object_name: str
    original_dax: str
    used: str
    usage_type: str
    direct_usage_count: int
    indirect_usage_count: int
    dependency_count: int
    complexity_score: float
    character_count: int
    line_count: int
    function_count: int
    calculate_count: int
    filter_count: int
    iterator_count: int
    var_count: int
    issue_count: int
    highest_severity: str
    analysis_status: str

