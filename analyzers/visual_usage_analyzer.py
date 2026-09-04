"""Visual Usage Analyzer for Power BI Reports.

Inspects modern PBIR and legacy report visual definitions (queryState, projections,
prototypeQuery, filters, objects) to identify directly referenced semantic model objects.
"""

import re
import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple, Optional, Any

from .dax_dependency_analyzer import ModelCatalog

logger = logging.getLogger(__name__)


@dataclass
class DirectVisualUsage:
    """Record of a model object directly used by a report visual."""
    page_id: str
    page_name: str
    visual_id: str
    visual_name: str
    visual_type: str
    visual_title: str
    object_type: str  # 'Measure', 'Column', 'Calculated Column', 'Table'
    table: str
    object_name: str
    usage_type: str = "Direct"
    canonical_id: str = ""


class VisualUsageAnalyzer:
    """Extracts field references from PBIR and legacy visual definitions and resolves them."""

    def __init__(self, pages: List[Dict[str, Any]], visuals: List[Dict[str, Any]], catalog: ModelCatalog):
        self.pages = pages
        self.visuals = visuals
        self.catalog = catalog
        self.direct_usages: List[DirectVisualUsage] = []
        self.visuals_with_parsed_refs = 0
        self.visuals_with_unresolved_refs = 0
        self._analyze()

    def _analyze(self) -> None:
        """Scan all visuals and page-level objects to extract direct field references."""
        for vis in self.visuals:
            page_id = vis.get("Page ID", "Unknown")
            page_name = vis.get("Page Name", "Unknown")
            visual_id = str(vis.get("Visual ID", "Unknown"))
            visual_name = vis.get("Visual Name", visual_id)
            visual_type = vis.get("Visual Type", "Unknown")
            raw_title = vis.get("Visual Title", "")

            # If title is unavailable or 'None', normalize to 'Untitled'
            if not raw_title or raw_title in ["None", "Untitled", ""]:
                visual_title = "Untitled"
            else:
                visual_title = str(raw_title).strip()

            raw_data = vis.get("raw_data", {})
            raw_fields = self._extract_fields_from_raw_visual(raw_data)

            # Also check if visual title has an expression / text
            if isinstance(raw_title, str) and "[" in raw_title:
                m = re.search(r"\[([^\]]+)\]", raw_title)
                if m:
                    raw_fields.append((None, m.group(1), None))

            # Resolve fields against catalog
            resolved_for_visual: Set[str] = set()
            has_resolved = False
            has_unresolved = False

            for t_hint, name, kind_hint in raw_fields:
                resolved_item = self._resolve_field(t_hint, name, kind_hint)
                if resolved_item:
                    t_can, obj_name, obj_type = resolved_item
                    can_id = f"{obj_type.upper()}:{t_can}" + (f"[{obj_name}]" if obj_name else "")

                    if can_id not in resolved_for_visual:
                        resolved_for_visual.add(can_id)
                        self.direct_usages.append(DirectVisualUsage(
                            page_id=page_id,
                            page_name=page_name,
                            visual_id=visual_id,
                            visual_name=visual_name,
                            visual_type=visual_type,
                            visual_title=visual_title,
                            object_type=obj_type,
                            table=t_can,
                            object_name=obj_name if obj_name else t_can,
                            usage_type="Direct",
                            canonical_id=can_id,
                        ))
                    has_resolved = True
                else:
                    has_unresolved = True

            if has_resolved:
                self.visuals_with_parsed_refs += 1
            if has_unresolved:
                self.visuals_with_unresolved_refs += 1

        logger.info(
            f"Extracted {len(self.direct_usages)} direct visual usages across {len(self.visuals)} visuals."
        )

    def _resolve_field(self, table_hint: Optional[str], field_name: str, kind_hint: Optional[str]) -> Optional[Tuple[str, str, str]]:
        """Resolve a field reference against ModelCatalog."""
        if not field_name:
            return None

        # 1. If table hint is provided, check qualified lookup
        if table_hint:
            res = self.catalog.resolve_qualified_column(table_hint, field_name)
            if res:
                return res
            # Check if table alone exists
            if not field_name or field_name == table_hint:
                can_t = self.catalog.resolve_table(table_hint)
                if can_t:
                    return can_t, "", "Table"

        # 2. Check unqualified lookup
        res_unq = self.catalog.resolve_unqualified(field_name, table_hint or "")
        if res_unq:
            return res_unq

        # 3. Check if field_name itself is a Table
        can_t = self.catalog.resolve_table(field_name)
        if can_t:
            return can_t, "", "Table"

        return None

    def _extract_fields_from_raw_visual(self, data: Any) -> List[Tuple[Optional[str], str, Optional[str]]]:
        """Recursively inspect visual JSON objects and extract (table_hint, name, kind_hint)."""
        fields: List[Tuple[Optional[str], str, Optional[str]]] = []
        if not data:
            return fields

        # Build alias map if prototypeQuery.From exists
        alias_map: Dict[str, str] = {}
        if isinstance(data, dict):
            # Check prototypeQuery
            proto = data.get("prototypeQuery", {}) or data.get("singleVisual", {}).get("prototypeQuery", {})
            if isinstance(proto, dict):
                for f_item in proto.get("From", []):
                    if isinstance(f_item, dict):
                        alias = f_item.get("Name")
                        entity = f_item.get("Entity")
                        if alias and entity:
                            alias_map[alias] = entity

        def walk(obj: Any):
            if isinstance(obj, dict):
                # 1. Match Column object: {"Column": {"Expression": ..., "Property": "ColName"}}
                if "Column" in obj and isinstance(obj["Column"], dict):
                    col_obj = obj["Column"]
                    prop = col_obj.get("Property")
                    expr = col_obj.get("Expression", {})
                    entity = self._get_entity_from_expr(expr, alias_map)
                    if prop:
                        fields.append((entity, prop, "Column"))

                # 2. Match Measure object: {"Measure": {"Expression": ..., "Property": "MeasureName"}}
                if "Measure" in obj and isinstance(obj["Measure"], dict):
                    meas_obj = obj["Measure"]
                    prop = meas_obj.get("Property")
                    expr = meas_obj.get("Expression", {})
                    entity = self._get_entity_from_expr(expr, alias_map)
                    if prop:
                        fields.append((entity, prop, "Measure"))

                # 3. Match HierarchyLevel: {"HierarchyLevel": {"Expression": ..., "Level": "LevelName"}}
                if "HierarchyLevel" in obj and isinstance(obj["HierarchyLevel"], dict):
                    hl_obj = obj["HierarchyLevel"]
                    level = hl_obj.get("Level")
                    expr = hl_obj.get("Expression", {})
                    entity = self._get_entity_from_expr(expr, alias_map)
                    if level:
                        fields.append((entity, level, "Column"))

                # 4. Match queryRef: e.g. "Customer.Customer Name", "Sales.Total Sales", "Sum(Sales.Amount)"
                if "queryRef" in obj and isinstance(obj["queryRef"], str):
                    qref = obj["queryRef"]
                    parsed = self._parse_query_ref(qref)
                    if parsed:
                        fields.append(parsed)

                # 5. Check visual title / direct visual name if visual config specifies target
                if "field" in obj and isinstance(obj["field"], dict):
                    walk(obj["field"])

                for k, v in obj.items():
                    walk(v)

            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(data)
        return fields

    def _get_entity_from_expr(self, expr: Any, alias_map: Dict[str, str]) -> Optional[str]:
        """Extract table / entity name from SourceRef expression dictionary."""
        if not isinstance(expr, dict):
            return None
        source_ref = expr.get("SourceRef", {})
        if isinstance(source_ref, dict):
            entity = source_ref.get("Entity")
            if entity:
                return entity
            source_alias = source_ref.get("Source")
            if source_alias and source_alias in alias_map:
                return alias_map[source_alias]
        return None

    def _parse_query_ref(self, qref: str) -> Optional[Tuple[Optional[str], str, Optional[str]]]:
        """Parse queryRef strings like 'Sales.Total Sales' or 'Sum(Sales.Amount)'."""
        qref = qref.strip()
        # Strip aggregation wrapper if present: Sum(Table.Col), Min(...), etc.
        m_agg = re.match(r"^[a-zA-Z0-9_]+\((.*)\)$", qref)
        if m_agg:
            qref = m_agg.group(1).strip()

        # Check Table.Column or Table.Measure
        if "." in qref:
            parts = qref.split(".", 1)
            t_part = parts[0].strip().strip("'\"[]")
            c_part = parts[1].strip().strip("'\"[]")
            # If Variation / Date Hierarchy like 'Date.Date.Variation.Year'
            if "." in c_part:
                c_part = c_part.split(".", 1)[0].strip().strip("'\"[]")
            return t_part, c_part, None

        return None, qref.strip().strip("'\"[]"), None

    def get_direct_usages(self) -> List[DirectVisualUsage]:
        """Return all direct visual usage records."""
        return self.direct_usages

    def get_visual_metrics(self) -> Dict[str, int]:
        """Return visual reference extraction metrics."""
        return {
            "Visuals with Parsed References": self.visuals_with_parsed_refs,
            "Visuals with Unresolved References": self.visuals_with_unresolved_refs,
        }

