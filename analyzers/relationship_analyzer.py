"""Relationship Analyzer and Normalizer.

Normalizes relationships, cardinalities (1:1, 1:M, M:1, M:M), cross-filter directions
(Single, Both), active/inactive states, and extracts key relationship columns.
"""

import logging
from typing import Dict, List, Any, Tuple

logger = logging.getLogger(__name__)


def normalize_cardinality(raw_cardinality: Any, from_card: Any = None, to_card: Any = None) -> str:
    """Normalize raw cardinality strings to standard '1:1', '1:M', 'M:1', 'M:M', or 'Unknown'."""
    if not raw_cardinality and (from_card or to_card):
        # Derive from fromCardinality / toCardinality
        fc = str(from_card).lower().strip() if from_card else "many"
        tc = str(to_card).lower().strip() if to_card else "one"
        if fc in ["one", "1"] and tc in ["one", "1"]:
            return "1:1"
        elif fc in ["one", "1"] and tc in ["many", "none", "*"]:
            return "1:M"
        elif fc in ["many", "none", "*"] and tc in ["one", "1"]:
            return "M:1"
        elif fc in ["many", "none", "*"] and tc in ["many", "none", "*"]:
            return "M:M"

    if not raw_cardinality:
        # Default in Power BI Tabular when unspecified is Many-to-One
        return "M:1"

    c_str = str(raw_cardinality).strip().lower()

    if c_str in ["manytoone", "m:1", "*:1", "many_to_one", "many-to-one"]:
        return "M:1"
    elif c_str in ["onetomany", "1:m", "1:*", "one_to_many", "one-to-many"]:
        return "1:M"
    elif c_str in ["onetoone", "1:1", "one_to_one", "one-to-one"]:
        return "1:1"
    elif c_str in ["manytomany", "m:m", "*:*", "many_to_many", "many-to-many"]:
        return "M:M"
    elif c_str in ["one", "1"]:
        return "1:1"
    elif c_str in ["many", "*"]:
        return "M:1"

    return "Unknown"


def normalize_filter_direction(raw_direction: Any) -> str:
    """Normalize cross-filtering behavior into 'Single', 'Both', or 'Unknown'."""
    if not raw_direction:
        return "Single"

    d_str = str(raw_direction).strip().lower()

    if d_str in ["onedirection", "single", "singledirection", "1", "one"]:
        return "Single"
    elif d_str in ["bothdirections", "both", "2", "bidirectional"]:
        return "Both"
    elif d_str in ["automatic", "default"]:
        return "Single"

    return "Unknown"


def normalize_status(is_active: Any) -> str:
    """Normalize active/inactive boolean into 'Active' or 'Inactive'."""
    if is_active is None:
        return "Active"  # Default in Power BI
    if isinstance(is_active, bool):
        return "Active" if is_active else "Inactive"
    s_str = str(is_active).strip().lower()
    if s_str in ["true", "1", "active", "yes"]:
        return "Active"
    elif s_str in ["false", "0", "inactive", "no"]:
        return "Inactive"
    return "Active"


class RelationshipAnalyzer:
    """Processes raw model relationships and generates normalized relationships and key columns."""

    def __init__(self, raw_relationships: List[Dict[str, Any]]):
        self.raw_relationships = raw_relationships
        self.normalized_relationships: List[Dict[str, Any]] = []
        self.key_columns: List[Dict[str, Any]] = []
        self._analyze()

    def _analyze(self) -> None:
        """Process and normalize all relationships."""
        for rel in self.raw_relationships:
            from_table = rel.get("fromTable", "") or ""
            from_col = rel.get("fromColumn", "") or ""
            to_table = rel.get("toTable", "") or ""
            to_col = rel.get("toColumn", "") or ""

            if not from_table and not to_table:
                continue

            cardinality = normalize_cardinality(
                rel.get("cardinality"),
                rel.get("fromCardinality"),
                rel.get("toCardinality"),
            )
            filter_dir = normalize_filter_direction(rel.get("crossFilteringBehavior"))
            status = normalize_status(rel.get("isActive", True))

            self.normalized_relationships.append({
                "From Table": from_table,
                "From Column": from_col,
                "To Table": to_table,
                "To Column": to_col,
                "Cardinality": cardinality,
                "Filter Direction": filter_dir,
                "Status": status,
            })

            # Key columns extraction
            # From Table side
            from_role = (
                "From (Many)" if cardinality in ["M:1", "M:M"] else ("From (One)" if cardinality in ["1:1", "1:M"] else "From")
            )
            self.key_columns.append({
                "Table": from_table,
                "Column": from_col,
                "Relationship Role": from_role,
                "Related Table": to_table,
                "Related Column": to_col,
            })

            # To Table side
            to_role = (
                "To (One)" if cardinality in ["M:1", "1:1"] else ("To (Many)" if cardinality in ["1:M", "M:M"] else "To")
            )
            self.key_columns.append({
                "Table": to_table,
                "Column": to_col,
                "Relationship Role": to_role,
                "Related Table": from_table,
                "Related Column": from_col,
            })

        logger.info(
            f"Normalized {len(self.normalized_relationships)} relationships and {len(self.key_columns)} key column entries."
        )

    def get_relationships(self) -> List[Dict[str, Any]]:
        """Return normalized relationships list."""
        return self.normalized_relationships

    def get_key_columns(self) -> List[Dict[str, Any]]:
        """Return key columns list."""
        return self.key_columns

    def get_summary_metrics(self) -> Dict[str, int]:
        """Compute metrics for Executive Summary sheet."""
        total = len(self.normalized_relationships)
        active = sum(1 for r in self.normalized_relationships if r["Status"] == "Active")
        inactive = total - active

        c_1_1 = sum(1 for r in self.normalized_relationships if r["Cardinality"] == "1:1")
        c_1_m = sum(1 for r in self.normalized_relationships if r["Cardinality"] == "1:M")
        c_m_1 = sum(1 for r in self.normalized_relationships if r["Cardinality"] == "M:1")
        c_m_m = sum(1 for r in self.normalized_relationships if r["Cardinality"] == "M:M")

        f_single = sum(1 for r in self.normalized_relationships if r["Filter Direction"] == "Single")
        f_both = sum(1 for r in self.normalized_relationships if r["Filter Direction"] == "Both")

        return {
            "Total Relationships": total,
            "Active Relationships": active,
            "Inactive Relationships": inactive,
            "1:1 Relationships": c_1_1,
            "1:M Relationships": c_1_m,
            "M:1 Relationships": c_m_1,
            "M:M Relationships": c_m_m,
            "Single-direction Relationships": f_single,
            "Both-direction Relationships": f_both,
        }

