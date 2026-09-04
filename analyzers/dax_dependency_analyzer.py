"""DAX Reference Extraction, Object Resolution & Dependency Graph Analyzer.

Parses DAX expressions from measures and calculated columns deterministically,
resolves references against the semantic model catalog, and builds a dependency graph
with cycle detection.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional, Any

logger = logging.getLogger(__name__)


def clean_dax_comments_and_strings(dax: str) -> Tuple[str, List[str]]:
    """Strip single-line/multi-line comments and mask string literals to prevent false matches."""
    if not dax:
        return "", []

    # 1. Strip multi-line comments /* ... */
    cleaned = re.sub(r"/\*[\s\S]*?\*/", " ", dax)

    # 2. Strip single-line comments // ... or -- ...
    cleaned = re.sub(r"(?://|--)[^\r\n]*", " ", cleaned)

    # 3. Mask string literals "..." (handling escaped "" quotes)
    # We replace string literal content with spaces to preserve line offsets
    string_literals = []

    def mask_string(match):
        s = match.group(0)
        string_literals.append(s)
        return '"' + " " * (len(s) - 2) + '"' if len(s) >= 2 else s

    masked = re.sub(r'"(?:[^"]|"")*"', mask_string, cleaned)

    return masked, string_literals


@dataclass
class DAXReference:
    """Raw reference extracted from DAX code."""
    raw_text: str
    ref_type: str  # 'qualified_column', 'unqualified_bracket', 'table'
    table_name: Optional[str] = None
    object_name: str = ""


@dataclass
class DependencyEdge:
    """Directed edge in the DAX dependency graph."""
    source_type: str  # 'Measure', 'Calculated Column'
    source_table: str
    source_name: str
    target_type: str  # 'Measure', 'Column', 'Calculated Column', 'Table', 'Unknown'
    target_table: str
    target_name: str
    dependency_type: str  # 'Measure -> Measure', 'Measure -> Column', etc.
    dependency_level: int
    dax_expression: str
    resolution_status: str  # 'Resolved', 'Unresolved'
    source_canonical: str = ""
    target_canonical: str = ""


class ModelCatalog:
    """Fast indexing catalog for semantic model tables, columns, and measures."""

    def __init__(self, tables: List[Dict[str, Any]], columns: List[Dict[str, Any]], measures: List[Dict[str, Any]], calc_columns: List[Dict[str, Any]]):
        self.tables: Dict[str, Dict[str, Any]] = {}
        self.columns: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.measures: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.calc_columns: Dict[Tuple[str, str], Dict[str, Any]] = {}

        # Secondary lookup maps (case-insensitive)
        self.tables_ci: Dict[str, str] = {}  # lower -> canonical table name
        self.measures_by_name: Dict[str, List[Tuple[str, str]]] = {}  # meas_name.lower() -> [(table, name)]
        self.columns_by_name: Dict[str, List[Tuple[str, str]]] = {}  # col_name.lower() -> [(table, name)]

        self._build_indexes(tables, columns, measures, calc_columns)

    def _build_indexes(self, tables, columns, measures, calc_columns):
        for t in tables:
            tname = t.get("Table Name", "")
            if tname:
                self.tables[tname] = t
                self.tables_ci[tname.lower()] = tname

        for c in columns:
            tname = c.get("Table Name", "")
            cname = c.get("Column Name", "")
            if tname and cname:
                self.columns[(tname, cname)] = c
                self.columns_by_name.setdefault(cname.lower(), []).append((tname, cname))

        for cc in calc_columns:
            tname = cc.get("Table", "")
            cname = cc.get("Column", "")
            if tname and cname:
                self.calc_columns[(tname, cname)] = cc

        for m in measures:
            tname = m.get("Table", "")
            mname = m.get("Measure Name", "")
            if tname and mname:
                self.measures[(tname, mname)] = m
                self.measures_by_name.setdefault(mname.lower(), []).append((tname, mname))

    def resolve_table(self, table_name: str) -> Optional[str]:
        """Resolve a table name case-insensitively."""
        if not table_name:
            return None
        return self.tables_ci.get(table_name.strip().lower())

    def resolve_qualified_column(self, table_name: str, col_name: str) -> Optional[Tuple[str, str, str]]:
        """Resolve Table[Column] -> (canonical_table, canonical_col, object_type)."""
        can_table = self.resolve_table(table_name)
        if not can_table:
            return None

        # Check in columns
        col_lower = col_name.strip().lower()
        for (t, c), obj in self.columns.items():
            if t == can_table and c.lower() == col_lower:
                obj_type = "Calculated Column" if (t, c) in self.calc_columns else "Column"
                return can_table, c, obj_type

        # Check in measures (sometimes qualified as Table[Measure])
        for (t, m), obj in self.measures.items():
            if t == can_table and m.lower() == col_lower:
                return can_table, m, "Measure"

        return None

    def resolve_unqualified(self, name: str, context_table: str) -> Optional[Tuple[str, str, str]]:
        """Resolve [Name] against measures first, then context table columns, then unique model columns."""
        name_lower = name.strip().lower()

        # 1. Check measures (in Power BI, [Measure] can be called from any table)
        if name_lower in self.measures_by_name:
            candidates = self.measures_by_name[name_lower]
            # If candidate in current table exists, prefer it, otherwise pick first
            for t, m in candidates:
                if t.lower() == context_table.lower():
                    return t, m, "Measure"
            t, m = candidates[0]
            return t, m, "Measure"

        # 2. Check columns in context table
        can_table = self.resolve_table(context_table)
        if can_table:
            for (t, c) in self.columns:
                if t == can_table and c.lower() == name_lower:
                    obj_type = "Calculated Column" if (t, c) in self.calc_columns else "Column"
                    return can_table, c, obj_type

        # 3. Check unique column in entire model
        if name_lower in self.columns_by_name:
            candidates = self.columns_by_name[name_lower]
            if len(candidates) == 1:
                t, c = candidates[0]
                obj_type = "Calculated Column" if (t, c) in self.calc_columns else "Column"
                return t, c, obj_type

        return None


class DAXDependencyAnalyzer:
    """Extracts DAX references, resolves them against model catalog, and builds the dependency graph."""

    def __init__(self, catalog: ModelCatalog, measures: List[Dict[str, Any]], calc_columns: List[Dict[str, Any]]):
        self.catalog = catalog
        self.measures = measures
        self.calc_columns = calc_columns
        self.edges: List[DependencyEdge] = []
        self.adjacency: Dict[str, List[DependencyEdge]] = {}  # canonical_source -> [DependencyEdge]
        self.unresolved_references: List[Dict[str, Any]] = []
        self.circular_dependencies: List[Dict[str, Any]] = []
        self._analyze()

    def _analyze(self) -> None:
        """Parse all measures and calculated columns to build dependency edges."""
        # 1. Parse Measures
        for m in self.measures:
            table = m.get("Table", "")
            name = m.get("Measure Name", "")
            dax = m.get("DAX Expression", "")
            if dax and dax != "Unknown":
                self._process_expression("Measure", table, name, dax)

        # 2. Parse Calculated Columns
        for cc in self.calc_columns:
            table = cc.get("Table", "")
            name = cc.get("Column", "")
            dax = cc.get("DAX Expression", "")
            if dax and dax != "Unknown":
                self._process_expression("Calculated Column", table, name, dax)

        # 3. Detect Circular Dependencies
        self._detect_circular_dependencies()

    def _process_expression(self, source_type: str, source_table: str, source_name: str, dax: str) -> None:
        """Extract and resolve references from a single DAX expression."""
        source_canonical = f"{source_type.upper()}:{source_table}[{source_name}]"
        raw_refs = self.extract_dax_references(dax)

        seen_targets: Set[str] = set()

        for ref in raw_refs:
            resolved_info = None

            if ref.ref_type == "qualified_column":
                resolved_info = self.catalog.resolve_qualified_column(ref.table_name or "", ref.object_name)
            elif ref.ref_type == "unqualified_bracket":
                resolved_info = self.catalog.resolve_unqualified(ref.object_name, source_table)
            elif ref.ref_type == "table":
                can_table = self.catalog.resolve_table(ref.object_name)
                if can_table:
                    resolved_info = (can_table, "", "Table")

            if resolved_info:
                target_table, target_name, target_type = resolved_info
                target_canonical = f"{target_type.upper()}:{target_table}" + (f"[{target_name}]" if target_name else "")
                
                # Prevent self-referencing duplicates or multiple duplicate edges
                if target_canonical == source_canonical or target_canonical in seen_targets:
                    continue
                seen_targets.add(target_canonical)

                dep_type = f"{source_type} -> {target_type}"
                edge = DependencyEdge(
                    source_type=source_type,
                    source_table=source_table,
                    source_name=source_name,
                    target_type=target_type,
                    target_table=target_table,
                    target_name=target_name,
                    dependency_type=dep_type,
                    dependency_level=1,
                    dax_expression=dax,
                    resolution_status="Resolved",
                    source_canonical=source_canonical,
                    target_canonical=target_canonical,
                )
                self.edges.append(edge)
                self.adjacency.setdefault(source_canonical, []).append(edge)

            else:
                # Unresolved reference
                target_table = ref.table_name or "Unknown"
                target_name = ref.object_name
                target_type = "Unknown"
                target_canonical = f"UNKNOWN:{target_table}[{target_name}]"

                if target_canonical in seen_targets:
                    continue
                seen_targets.add(target_canonical)

                edge = DependencyEdge(
                    source_type=source_type,
                    source_table=source_table,
                    source_name=source_name,
                    target_type=target_type,
                    target_table=target_table,
                    target_name=target_name,
                    dependency_type=f"{source_type} -> Unknown",
                    dependency_level=1,
                    dax_expression=dax,
                    resolution_status="Unresolved",
                    source_canonical=source_canonical,
                    target_canonical=target_canonical,
                )
                self.edges.append(edge)
                self.unresolved_references.append({
                    "Source Object": source_canonical,
                    "Referenced Text": ref.raw_text,
                    "DAX Expression": dax,
                })

    @classmethod
    def extract_dax_references(cls, dax: str) -> List[DAXReference]:
        """Deterministic regex-based DAX reference extractor."""
        references: List[DAXReference] = []
        masked_dax, _ = clean_dax_comments_and_strings(dax)
        if not masked_dax.strip():
            return references

        # 1. Match Qualified Column References:
        # 'Table Name'[Column Name] or Table[Column Name]
        # We need to distinguish this from [Measure] preceded by spaces or keywords
        qual_pattern = r"(?:'([^']+)'|([a-zA-Z0-9_#@]+))\s*\[([^\]]+)\]"
        for match in re.finditer(qual_pattern, masked_dax):
            table = match.group(1) or match.group(2)
            col = match.group(3)
            raw = match.group(0)
            references.append(DAXReference(
                raw_text=raw,
                ref_type="qualified_column",
                table_name=table.strip(),
                object_name=col.strip(),
            ))

        # 2. Match Unqualified Bracket References:
        # [Measure Name] where '[' is NOT preceded by ' or identifier
        # Replace qualified matches with spaces first to find remaining unqualified ones
        unqual_masked = re.sub(qual_pattern, lambda m: " " * len(m.group(0)), masked_dax)
        unqual_pattern = r"\[([^\]]+)\]"
        for match in re.finditer(unqual_pattern, unqual_masked):
            obj = match.group(1).strip()
            raw = match.group(0)
            references.append(DAXReference(
                raw_text=raw,
                ref_type="unqualified_bracket",
                table_name=None,
                object_name=obj,
            ))

        # 3. Match Table references in Table Functions:
        # e.g. ALL('Table'), ALL(Table), FILTER('Table', ...), COUNTROWS(Table), RELATEDTABLE(Table), SUMX(Table, ...)
        table_func_pattern = r"\b(?:ALL|ALLEXCEPT|FILTER|COUNTROWS|DISTINCT|VALUES|CALCULATETABLE|RELATEDTABLE|SUMMARIZE|ADDCOLUMNS|SELECTCOLUMNS|CROSSJOIN|UNION|EXCEPT|INTERSECT|TREATAS|SUMX|AVERAGEX|MINX|MAXX|COUNTX|COUNTAX|MEDIANX|CONCATENATEX|RANKX)\s*\(\s*(?:'([^']+)'|([a-zA-Z0-9_#@]+))(?!\s*\[)"
        for match in re.finditer(table_func_pattern, masked_dax, re.IGNORECASE):
            tname = match.group(1) or match.group(2)
            if tname:
                tname = tname.strip()
                # Exclude DAX keywords that might look like names
                if tname.upper() not in ["VAR", "RETURN", "TRUE", "FALSE", "BLANK"]:
                    references.append(DAXReference(
                        raw_text=match.group(0),
                        ref_type="table",
                        table_name=tname,
                        object_name=tname,
                    ))

        return references

    def _detect_circular_dependencies(self) -> None:
        """Cycle detection using DFS traversal."""
        visited: Set[str] = set()
        rec_stack: List[str] = []

        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.append(node)

            for edge in self.adjacency.get(node, []):
                target = edge.target_canonical
                if target not in visited:
                    dfs(target, path + [node])
                elif target in rec_stack:
                    # Circular dependency detected!
                    cycle_start_idx = rec_stack.index(target)
                    cycle_nodes = rec_stack[cycle_start_idx:] + [target]
                    cycle_path_str = " -> ".join(cycle_nodes)

                    # Avoid duplicate recording of the same cycle
                    cycle_set = frozenset(cycle_nodes)
                    if not any(frozenset(c["Nodes"]) == cycle_set for c in self.circular_dependencies):
                        self.circular_dependencies.append({
                            "Cycle ID": f"Cycle-{len(self.circular_dependencies) + 1}",
                            "Nodes": cycle_nodes,
                            "Path": cycle_path_str,
                        })
                        logger.warning(f"Circular dependency detected in DAX: {cycle_path_str}")

            rec_stack.pop()

        for node in list(self.adjacency.keys()):
            if node not in visited:
                dfs(node, [])

    def get_edges(self) -> List[DependencyEdge]:
        """Return list of all dependency edges."""
        return self.edges

    def get_circular_dependencies(self) -> List[Dict[str, Any]]:
        """Return list of detected circular dependencies."""
        return self.circular_dependencies

    def get_unresolved_references(self) -> List[Dict[str, Any]]:
        """Return list of unresolved DAX references."""
        return self.unresolved_references

