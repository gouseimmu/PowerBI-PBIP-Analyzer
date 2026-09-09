"""PBIP Analysis Context Builder.

Extracts targeted, relevant metadata from in-memory PBIP analysis results
to keep AI prompts compact, cheap, fast, and strictly grounded.
DOES NOT use vector databases or embeddings.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple


class ContextBuilder:
    """Intelligently filters analyzed PBIP metadata for chatbot context grounding."""

    @classmethod
    def build_context(
        cls,
        question: str,
        metadata: Dict[str, Any],
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Build a compact, focused context dictionary matching the user's question."""
        if not metadata:
            return {}

        clean_q = question.strip()
        lower_q = clean_q.lower()

        # 1. Resolve entity references from recent chat history if pronouns exist
        resolved_entity = cls._resolve_entity_from_history(lower_q, chat_history, metadata)

        # 2. Extract matched entities in the query or resolved history
        matched_measures = cls._find_measures(lower_q, metadata)
        matched_tables = cls._find_tables(lower_q, metadata)
        matched_columns = cls._find_columns(lower_q, metadata)

        if resolved_entity:
            entity_type, entity_table, entity_name = resolved_entity
            if entity_type in ("measure", "calculated_column"):
                for m in metadata.get("measures", []) + metadata.get("calculated_columns", []):
                    name = m.get("Measure Name") or m.get("Column")
                    if name and name.lower() == entity_name.lower():
                        if m not in matched_measures:
                            matched_measures.append(m)
            elif entity_type == "table":
                for t in metadata.get("tables", []):
                    name = t.get("Table Name") or t.get("Table", "")
                    if name and name.lower() == entity_name.lower():
                        if t not in matched_tables:
                            matched_tables.append(t)

        context: Dict[str, Any] = {
            "project_name": metadata.get("project_name", "Unknown"),
            "model_format": metadata.get("model_format", "TMDL"),
            "report_format": metadata.get("report_format", "PBIR"),
            "model_info": metadata.get("model_info", {}),
        }

        # 3. Intent Detection & Context Construction

        # Intent A: Specific Measure / Calculated Column asked
        if matched_measures:
            m_contexts = []
            for m in matched_measures[:3]:  # Top 3 matching measures max
                mname = m.get("Measure Name") or m.get("Column") or ""
                tname = m.get("Table") or ""
                obj_type = "Measure" if "Measure Name" in m else "Calculated Column"

                # Get static analysis / improvements
                imps = [
                    imp for imp in metadata.get("dax_improvements", [])
                    if (imp.get("Object Name") == mname or imp.get("Object") == mname)
                ]
                dax_analysis = [
                    a for a in metadata.get("dax_analysis", [])
                    if (a.get("Object Name") == mname or a.get("Object") == mname)
                ]

                # Get usage records
                obj_usage = [
                    u for u in metadata.get("object_usage", [])
                    if u.get("Object Name") == mname
                ]

                # Get visual references
                vis_refs = [
                    v for v in metadata.get("visual_usage", [])
                    if v.get("Object Name") == mname
                ]

                # Get dependency edges
                dep_edges = [
                    e for e in metadata.get("dax_dependencies", [])
                    if (isinstance(e, dict) and (e.get("Source Object") == mname or e.get("Target Object") == mname))
                    or (hasattr(e, "source_name") and (getattr(e, "source_name") == mname or getattr(e, "target_name") == mname))
                ]

                m_contexts.append({
                    "object_type": obj_type,
                    "table": tname,
                    "object_name": mname,
                    "dax_expression": m.get("DAX Expression", ""),
                    "format_string": m.get("Format String", ""),
                    "description": m.get("Description", ""),
                    "usage_info": obj_usage[0] if obj_usage else {},
                    "static_dax_analysis": dax_analysis[0] if dax_analysis else {},
                    "improvements": imps,
                    "visual_references": vis_refs[:10],
                    "dependency_edges": [
                        e if isinstance(e, dict) else {
                            "source_table": getattr(e, "source_table", ""),
                            "source_name": getattr(e, "source_name", ""),
                            "target_table": getattr(e, "target_table", ""),
                            "target_name": getattr(e, "target_name", ""),
                        } for e in dep_edges[:10]
                    ],
                })
            context["focused_objects"] = m_contexts

        # Intent B: Unused Objects / Model Cleanup
        if any(w in lower_q for w in ["unused", "orphan", "clean up", "redundant", "dead"]):
            context["unused_objects_summary"] = {
                "unused_objects_count": len(metadata.get("unused_objects", [])),
                "unused_objects": metadata.get("unused_objects", [])[:30],
                "phase2_summary": metadata.get("phase2_summary", {}),
            }

        # Intent C: Relationships / Lineage
        if any(w in lower_q for w in ["relationship", "relation", "filter direction", "bidirectional", "cardinality", "parent-child", "inactive", "parent child"]):
            rels = metadata.get("relationships", [])
            if matched_tables:
                t_names = {t.get("Table Name") or t.get("Table", "") for t in matched_tables}
                rels = [r for r in rels if r.get("From Table") in t_names or r.get("To Table") in t_names]
            context["relationships_summary"] = {
                "relationship_metrics": metadata.get("relationship_metrics", {}),
                "relationships": rels[:25],
                "key_columns": metadata.get("key_columns", [])[:25],
            }

        # Intent D: Data Sources / Power Query M
        if any(w in lower_q for w in ["source", "sql", "excel", "power query", "m expression", "sharepoint", "database", "connection"]):
            context["data_sources"] = metadata.get("data_sources", [])

        # Intent E: Model Health / Health Score
        if any(w in lower_q for w in ["health", "score", "deduction", "grade", "why is my score", "factor"]):
            context["model_health"] = metadata.get("model_health", {})

        # Intent F: Report / Visuals / Pages
        if any(w in lower_q for w in ["visual", "page", "report", "display", "card", "chart", "tableex"]):
            context["pages"] = metadata.get("pages", [])
            context["visual_count"] = len(metadata.get("visuals", []))
            context["visual_usage_sample"] = metadata.get("visual_usage", [])[:20]

        # Intent G: Executive Summary / Model Overview / Top Issues
        if any(w in lower_q for w in ["summary", "executive", "overview", "top issue", "fix first", "recommendation"]):
            context["executive_overview"] = {
                "model_info": metadata.get("model_info", {}),
                "model_health": metadata.get("model_health", {}),
                "table_count": len(metadata.get("tables", [])),
                "column_count": len(metadata.get("columns", [])),
                "measure_count": len(metadata.get("measures", [])),
                "page_count": len(metadata.get("pages", [])),
                "visual_count": len(metadata.get("visuals", [])),
                "unused_objects_count": len(metadata.get("unused_objects", [])),
                "top_dax_improvements": metadata.get("dax_improvements", [])[:5],
                "relationship_metrics": metadata.get("relationship_metrics", {}),
                "data_source_types": list({s.get("Source Type") for s in metadata.get("data_sources", []) if s.get("Source Type")}),
            }

        # Intent H: General Table / Column Specific Question
        if matched_tables and not matched_measures:
            tbl_info = []
            for t in matched_tables[:3]:
                tname = t.get("Table Name") or t.get("Table", "")
                tbl_cols = [c for c in metadata.get("columns", []) if c.get("Table Name") == tname or c.get("Table") == tname]
                tbl_meas = [m for m in metadata.get("measures", []) if m.get("Table") == tname]
                tbl_rels = [r for r in metadata.get("relationships", []) if r.get("From Table") == tname or r.get("To Table") == tname]
                tbl_info.append({
                    "table_name": tname,
                    "table_type": t.get("Table Type", "Data"),
                    "is_hidden": t.get("Is Hidden", "No"),
                    "columns_count": len(tbl_cols),
                    "measures_count": len(tbl_meas),
                    "columns_sample": [c.get("Column Name") or c.get("Column") for c in tbl_cols[:10]],
                    "measures_list": [m.get("Measure Name") for m in tbl_meas[:10]],
                    "relationships": tbl_rels,
                })
            context["focused_tables"] = tbl_info

        # Fallback General Model Summary if context remains very sparse
        if len(context) <= 4:
            context["general_model_summary"] = {
                "tables": [t.get("Table Name") or t.get("Table") for t in metadata.get("tables", [])[:15]],
                "measures": [m.get("Measure Name") for m in metadata.get("measures", [])[:20]],
                "model_health": metadata.get("model_health", {}),
                "unused_count": len(metadata.get("unused_objects", [])),
            }

        return context

    @classmethod
    def _find_measures(cls, lower_q: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find measures or calculated columns matched in the query string."""
        matches = []
        all_objects = metadata.get("measures", []) + metadata.get("calculated_columns", [])

        for obj in all_objects:
            name = obj.get("Measure Name") or obj.get("Column")
            if not name:
                continue
            name_lower = name.lower()
            bracket_name = f"[{name_lower}]"
            if bracket_name in lower_q or name_lower in lower_q:
                matches.append(obj)

        return matches

    @classmethod
    def _find_tables(cls, lower_q: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find tables matched in the query string."""
        matches = []
        for t in metadata.get("tables", []):
            name = t.get("Table Name") or t.get("Table")
            if not name:
                continue
            name_lower = name.lower()
            if re.search(r"\b" + re.escape(name_lower) + r"\b", lower_q):
                matches.append(t)

        return matches

    @classmethod
    def _find_columns(cls, lower_q: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find data columns matched in the query string."""
        matches = []
        for c in metadata.get("columns", []):
            cname = c.get("Column Name") or c.get("Column")
            if not cname:
                continue
            c_lower = cname.lower()
            if c_lower in lower_q:
                matches.append(c)

        return matches

    @classmethod
    def _resolve_entity_from_history(
        cls,
        lower_q: str,
        chat_history: Optional[List[Dict[str, str]]],
        metadata: Dict[str, Any],
    ) -> Optional[Tuple[str, str, str]]:
        """Resolve pronouns ('it', 'this measure', 'that table') using recent chat history."""
        if not chat_history:
            return None

        pronouns = [" it ", " it?", " it.", "its ", "this measure", "that measure", "this table", "that table"]
        if not any(p in lower_q or lower_q.startswith("it ") for p in pronouns):
            return None

        # Look backward through recent messages (up to 4 messages)
        recent_messages = list(reversed(chat_history[-4:]))

        all_measures = [m.get("Measure Name") or m.get("Column") for m in metadata.get("measures", []) if m.get("Measure Name") or m.get("Column")]
        all_tables = [t.get("Table Name") or t.get("Table") for t in metadata.get("tables", []) if t.get("Table Name") or t.get("Table")]

        for msg in recent_messages:
            content = msg.get("content", "")
            # Check for bracketed measures like [Total Revenue]
            bracket_match = re.findall(r"\[(.*?)\]", content)
            for b in bracket_match:
                for m in all_measures:
                    if m and m.lower() == b.lower():
                        return ("measure", "", m)

            # Check for measure names in message text
            for m in all_measures:
                if m and m.lower() in content.lower():
                    return ("measure", "", m)

            # Check for table names in message text
            for t in all_tables:
                if t and t.lower() in content.lower():
                    return ("table", t, "")

        return None

