"""Object Usage, Lineage & Unused Objects Analyzer.

Performs recursive dependency traversal from direct visual references to classify
every model object into Direct, Indirect, or Unused, and builds complete usage lineage paths.
every model object into Direct, Indirect, Direct + Indirect, or Unused, and builds complete usage lineage paths.
"""

import logging
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple, Optional, Any

from .dax_dependency_analyzer import DAXDependencyAnalyzer, ModelCatalog, DependencyEdge
from .visual_usage_analyzer import DirectVisualUsage, VisualUsageAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class UsageLineageRecord:
    """Record representing an end-to-end dependency path from a visual to an indirect object."""
    page_name: str
    visual_name: str
    visual_title: str
    direct_object: str
    indirect_object: str
    dependency_path: str
    dependency_level: int
    dax_expression: str


class ObjectUsageAnalyzer:
    """Combines direct visual usage and DAX dependency graph to compute complete usage and lineage."""

    def __init__(
        self,
        catalog: ModelCatalog,
        direct_usages: List[DirectVisualUsage],
        dax_analyzer: DAXDependencyAnalyzer,
        visual_analyzer: VisualUsageAnalyzer,
        tables: List[Dict[str, Any]],
        columns: List[Dict[str, Any]],
        measures: List[Dict[str, Any]],
        calc_columns: List[Dict[str, Any]],
    ):
        self.catalog = catalog
        self.direct_usages = direct_usages
        self.dax_analyzer = dax_analyzer
        self.visual_analyzer = visual_analyzer

        self.tables = tables
        self.columns = columns
        self.measures = measures
        self.calc_columns = calc_columns

        self.object_usage_list: List[Dict[str, Any]] = []
        self.visual_usage_list: List[Dict[str, Any]] = []
        self.dax_dependencies_list: List[Dict[str, Any]] = []
        self.lineage_list: List[UsageLineageRecord] = []
        self.unused_objects_list: List[Dict[str, Any]] = []
        self.summary_metrics: Dict[str, Any] = {}

        self._analyze()

    def _analyze(self) -> None:
        """Run the complete usage and lineage analysis pipeline."""
        # 1. Format Visual Usage sheet records
        for u in self.direct_usages:
            self.visual_usage_list.append({
                "Page ID": u.page_id,
                "Page Name": u.page_name,
                "Visual ID": u.visual_id,
                "Visual Name": u.visual_name,
                "Visual Type": u.visual_type,
                "Visual Title": u.visual_title,
                "Object Type": u.object_type,
                "Table": u.table,
                "Object Name": u.object_name,
                "Usage Type": "Direct",
            })

        # 2. Format DAX Dependencies sheet records
        for edge in self.dax_analyzer.get_edges():
            self.dax_dependencies_list.append({
                "Source Object Type": edge.source_type,
                "Source Table": edge.source_table,
                "Source Object": edge.source_name,
                "Referenced Object Type": edge.target_type,
                "Referenced Table": edge.target_table,
                "Referenced Object": edge.target_name if edge.target_name else edge.target_table,
                "Dependency Type": edge.dependency_type,
                "Dependency Level": edge.dependency_level,
                "DAX Expression": edge.dax_expression,
                "Resolution Status": edge.resolution_status,
            })

        # 3. Track direct usage occurrences by canonical object
        # canonical_id -> list of visual info dicts
        direct_map: Dict[str, List[DirectVisualUsage]] = {}
        for u in self.direct_usages:
            direct_map.setdefault(u.canonical_id, []).append(u)

        # 4. Transitive Traversal to find Indirect Usages and Lineage
        # canonical_id -> list of (visual_usage, path, level, dax)
        indirect_map: Dict[str, List[Tuple[DirectVisualUsage, List[str], int, str]]] = {}
        seen_lineage: Set[Tuple[str, str, str, str, str]] = set()

        for direct_u in self.direct_usages:
            root_canonical = direct_u.canonical_id
            direct_label = direct_u.object_name

            # Queue contains: (current_canonical_node, path_labels, level)
            queue = deque([(root_canonical, [direct_label], 1)])
            visited_in_branch: Set[str] = {root_canonical}

            while queue:
                current_node, path_labels, level = queue.popleft()

                for edge in self.dax_analyzer.adjacency.get(current_node, []):
                    target_canonical = edge.target_canonical
                    target_label = edge.target_name if edge.target_name else edge.target_table

                    if target_canonical not in visited_in_branch:
                        visited_in_branch.add(target_canonical)
                        new_path = path_labels + [target_label]

                        indirect_map.setdefault(target_canonical, []).append(
                            (direct_u, new_path, level, edge.dax_expression)
                        )

                        # Create Lineage Record
                        lineage_key = (
                            direct_u.page_name,
                            direct_u.visual_name,
                            direct_label,
                            target_label,
                            " -> ".join(new_path),
                        )
                        if lineage_key not in seen_lineage:
                            seen_lineage.add(lineage_key)
                            self.lineage_list.append(UsageLineageRecord(
                                page_name=direct_u.page_name,
                                visual_name=direct_u.visual_name,
                                visual_title=direct_u.visual_title,
                                direct_object=direct_label,
                                indirect_object=target_label,
                                dependency_path=" -> ".join(new_path),
                                dependency_level=level,
                                dax_expression=edge.dax_expression,
                            ))

                        # Traverse deeper
                        queue.append((target_canonical, new_path, level + 1))

        # 5. Build Object Usage & Unused Objects
        total_objects = 0
        used_objects = 0
        unused_objects = 0
        directly_used_objects = 0
        indirectly_used_objects = 0
        direct_and_indirect_used_objects = 0

        # Helper to process an object
        def process_entity(obj_type: str, table_name: str, obj_name: str):
            nonlocal total_objects, used_objects, unused_objects, directly_used_objects, indirectly_used_objects
            nonlocal total_objects, used_objects, unused_objects, directly_used_objects, indirectly_used_objects, direct_and_indirect_used_objects

            total_objects += 1
            can_id = f"{obj_type.upper()}:{table_name}" + (f"[{obj_name}]" if obj_name else "")

            direct_records = direct_map.get(can_id, [])
            indirect_records = indirect_map.get(can_id, [])

            direct_count = len(direct_records)
            indirect_count = len(indirect_records)

            # Unique visual locations
            direct_vis_locs = {(u.page_name, u.visual_id) for u in direct_records}
            indirect_vis_locs = {(u.page_name, u.visual_id) for (u, _, _, _) in indirect_records}
            total_loc_count = len(direct_vis_locs.union(indirect_vis_locs))

            if direct_count > 0 and indirect_count > 0:
                used = "Yes"
                usage_type = "Direct + Indirect"
                used_objects += 1
                directly_used_objects += 1
                indirectly_used_objects += 1
                direct_and_indirect_used_objects += 1
            elif direct_count > 0:
                used = "Yes"
                usage_type = "Direct"
                used_objects += 1
                directly_used_objects += 1
            elif indirect_count > 0:
                used = "Yes"
                usage_type = "Indirect"
                used_objects += 1
                indirectly_used_objects += 1
            else:
                used = "No"
                usage_type = "Unused"
                unused_objects += 1

                self.unused_objects_list.append({
                    "Object Type": obj_type,
                    "Table": table_name,
                    "Object Name": obj_name if obj_name else table_name,
                    "Reason": "No direct or indirect report usage detected",
                    "Direct Usage": "No",
                    "Indirect Usage": "No",
                })

            self.object_usage_list.append({
                "Object Type": obj_type,
                "Table": table_name,
                "Object Name": obj_name if obj_name else table_name,
                "Used": used,
                "Usage Type": usage_type,
                "Direct Usage Count": direct_count,
                "Indirect Usage Count": indirect_count,
                "Usage Location Count": total_loc_count,
            })

        # A. Process Measures
        for m in self.measures:
            process_entity("Measure", m.get("Table", ""), m.get("Measure Name", ""))

        # B. Process Calculated Columns
        for cc in self.calc_columns:
            process_entity("Calculated Column", cc.get("Table", ""), cc.get("Column", ""))

        # C. Process Regular Columns
        calc_keys = {(cc.get("Table", ""), cc.get("Column", "")) for cc in self.calc_columns}
        for c in self.columns:
            t = c.get("Table Name", "")
            col = c.get("Column Name", "")
            if (t, col) not in calc_keys:
                process_entity("Column", t, col)

        # 6. Compute Executive Summary Phase 2 metrics
        vis_metrics = self.visual_analyzer.get_visual_metrics()
        self.summary_metrics = {
            "Total Objects": total_objects,
            "Used Objects": used_objects,
            "Unused Objects": unused_objects,
            "Directly Used Objects": directly_used_objects,
            "Indirectly Used Objects": indirectly_used_objects,
            "Direct + Indirect Objects": direct_and_indirect_used_objects,
            "Direct Usage Records": len(self.visual_usage_list),
            "Indirect Usage Records": len(self.lineage_list),
            "Dependency Edges": len(self.dax_dependencies_list),
            "Unresolved DAX References": len(self.dax_analyzer.get_unresolved_references()),
            "Circular Dependencies": len(self.dax_analyzer.get_circular_dependencies()),
            "Visuals with Parsed References": vis_metrics.get("Visuals with Parsed References", 0),
            "Visuals with Unresolved References": vis_metrics.get("Visuals with Unresolved References", 0),
        }

        logger.info(
            f"Phase 2 Analysis complete: {total_objects} total objects, {used_objects} used ({directly_used_objects} direct, {indirectly_used_objects} indirect), "
            f"Phase 2 Analysis complete: {total_objects} total objects, {used_objects} used "
            f"({directly_used_objects} direct, {indirectly_used_objects} indirect, {direct_and_indirect_used_objects} direct+indirect), "
            f"{unused_objects} unused, {len(self.lineage_list)} lineage records."
        )

    def get_object_usage(self) -> List[Dict[str, Any]]:
        """Return data for Sheet 11: Object Usage."""
        """Return data for Object Usage."""
        return self.object_usage_list

    def get_visual_usage(self) -> List[Dict[str, Any]]:
        """Return data for Sheet 12: Visual Usage."""
        """Return data for Visual Usage."""
        return self.visual_usage_list

    def get_dax_dependencies(self) -> List[Dict[str, Any]]:
        """Return data for Sheet 13: DAX Dependencies."""
        """Return data for DAX Dependencies."""
        return self.dax_dependencies_list

    def get_usage_lineage(self) -> List[Dict[str, Any]]:
        """Return data for Sheet 14: Usage Lineage."""
        """Return data for Usage Lineage."""
        return [
            {
                "Page Name": rec.page_name,
                "Visual Name": rec.visual_name,
                "Visual Title": rec.visual_title,
                "Direct Object": rec.direct_object,
                "Indirect Object": rec.indirect_object,
                "Dependency Path": rec.dependency_path,
                "Dependency Level": rec.dependency_level,
                "DAX Expression": rec.dax_expression,
            }
            for rec in self.lineage_list
        ]

    def get_unused_objects(self) -> List[Dict[str, Any]]:
        """Return data for Sheet 15: Unused Objects."""
        """Return data for Unused Objects."""
        return self.unused_objects_list

    def get_summary_metrics(self) -> Dict[str, Any]:
        """Return Phase 2 summary metrics."""
        return self.summary_metrics

