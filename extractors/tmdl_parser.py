"""TMDL (Tabular Model Definition Language) Parser.

Robust, pure-Python parser for TMDL files in Power BI PBIP projects.
Extracts model properties, tables, columns, calculated columns, measures,
partitions (M code), relationships, and expressions.
"""

import os
import re
import logging
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)


def unquote_name(name: str) -> str:
    """Strip enclosing quotes or brackets from TMDL identifiers."""
    name = name.strip()
    if (name.startswith("'") and name.endswith("'")) or (name.startswith('"') and name.endswith('"')):
        name = name[1:-1].replace("''", "'")
    elif name.startswith("[") and name.endswith("]"):
        name = name[1:-1]
    return name.strip()


def parse_column_reference(ref: str) -> Tuple[str, str]:
    """Parse 'Table'.'Column' or Table.Column or 'Table'[Column] or [Column] into (table, column)."""
    ref = ref.strip()
    # Pattern: 'Table Name'[Column Name] or 'Table Name'.'Column Name' or Table.Column
    # 1. Match 'Table'[Column] or 'Table'.'Column'
    m = re.match(r"^'([^']+)'\.(?:'([^']+)'|\[([^\]]+)\]|([^\s\.]+))$", ref)
    if m:
        table = m.group(1)
        col = m.group(2) or m.group(3) or m.group(4)
        return table, col

    # 2. Match 'Table'[Column] without dot
    m = re.match(r"^'([^']+)'\[([^\]]+)\]$", ref)
    if m:
        return m.group(1), m.group(2)

    # 3. Match Table[Column]
    m = re.match(r"^([^'\[\.\s]+)\[([^\]]+)\]$", ref)
    if m:
        return m.group(1), m.group(2)

    # 4. Match Table.Column (possibly with quotes on column)
    if "." in ref:
        parts = ref.split(".", 1)
        return unquote_name(parts[0]), unquote_name(parts[1])

    return "", unquote_name(ref)


class TMDLParser:
    """Parses TMDL definition directories or individual TMDL files into structured metadata."""

    @classmethod
    def parse_definition_dir(cls, def_dir: str) -> Dict[str, Any]:
        """Parse all TMDL files inside a definition folder."""
        result: Dict[str, Any] = {
            "model": {
                "name": "Model",
                "culture": "Unknown",
                "compatibilityLevel": "Unknown",
                "sourceQueryCulture": "Unknown",
                "defaultPowerBIDataSourceVersion": "Unknown",
                "tables": [],
                "relationships": [],
                "expressions": [],
                "annotations": {},
            }
        }

        if not os.path.exists(def_dir):
            logger.warning(f"TMDL definition directory does not exist: {def_dir}")
            return result

        # 1. Parse model.tmdl if present
        model_file = os.path.join(def_dir, "model.tmdl")
        if os.path.exists(model_file):
            cls._parse_model_file(model_file, result["model"])

        # 2. Parse tables/ directory
        tables_dir = os.path.join(def_dir, "tables")
        if os.path.exists(tables_dir):
            for fname in os.listdir(tables_dir):
                if fname.lower().endswith(".tmdl"):
                    t_path = os.path.join(tables_dir, fname)
                    table_obj = cls.parse_table_file(t_path)
                    if table_obj:
                        result["model"]["tables"].append(table_obj)

        # Also look for any standalone table *.tmdl in def_dir
        for fname in os.listdir(def_dir):
            fpath = os.path.join(def_dir, fname)
            if os.path.isfile(fpath) and fname.lower().endswith(".tmdl"):
                if fname.lower() not in ["model.tmdl", "relationships.tmdl", "expressions.tmdl"]:
                    # Try parsing as table file if it begins with 'table '
                    with open(fpath, "r", encoding="utf-8", errors="replace") as tf:
                        first_line = tf.readline().strip()
                        if first_line.startswith("table "):
                            table_obj = cls.parse_table_file(fpath)
                            if table_obj:
                                result["model"]["tables"].append(table_obj)

        # 3. Parse relationships.tmdl if present
        rel_file = os.path.join(def_dir, "relationships.tmdl")
        if os.path.exists(rel_file):
            rels = cls.parse_relationships_file(rel_file)
            result["model"]["relationships"].extend(rels)

        # 4. Parse expressions.tmdl if present
        expr_file = os.path.join(def_dir, "expressions.tmdl")
        if os.path.exists(expr_file):
            exprs = cls.parse_expressions_file(expr_file)
            result["model"]["expressions"].extend(exprs)

        # Log summary
        m = result["model"]
        logger.info(
            f"Parsed TMDL definition: {len(m['tables'])} tables, {len(m['relationships'])} relationships, "
            f"{len(m['expressions'])} expressions"
        )
        return result

    @classmethod
    def _parse_model_file(cls, filepath: str, model_dict: Dict[str, Any]) -> None:
        """Parse model.tmdl for model-level properties."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            logger.error(f"Failed to read model.tmdl: {e}")
            return

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue

            if stripped.startswith("model "):
                model_dict["name"] = unquote_name(stripped[6:].strip())
            elif stripped.startswith("culture:"):
                model_dict["culture"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("defaultPowerBIDataSourceVersion:"):
                model_dict["defaultPowerBIDataSourceVersion"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("sourceQueryCulture:"):
                model_dict["sourceQueryCulture"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("annotation "):
                ann_match = re.match(r"^annotation\s+([^\s=]+)\s*=\s*(.*)$", stripped)
                if ann_match:
                    model_dict["annotations"][ann_match.group(1)] = ann_match.group(2).strip('"')

    @classmethod
    def parse_table_file(cls, filepath: str) -> Optional[Dict[str, Any]]:
        """Parse a table TMDL file into structured table dictionary."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read table file {filepath}: {e}")
            return None

        lines = content.splitlines()
        if not lines:
            return None

        table_dict: Dict[str, Any] = {
            "name": os.path.splitext(os.path.basename(filepath))[0],
            "isHidden": False,
            "description": "",
            "dataCategory": "",
            "columns": [],
            "measures": [],
            "partitions": [],
            "annotations": [],
        }

        # Parsing state machine
        current_section = "table"  # 'table', 'column', 'measure', 'partition'
        current_item: Dict[str, Any] = {}
        in_backtick_block = False
        multiline_buffer: List[str] = []

        i = 0
        n = len(lines)
        while i < n:
            raw_line = lines[i]
            line = raw_line.strip()
            i += 1

            if not line or line.startswith("//"):
                continue

            # Handle multiline triple backticks
            if in_backtick_block:
                if line.endswith("```") or line == "```":
                    clean_line = line[:-3].strip() if line.endswith("```") else ""
                    if clean_line:
                        multiline_buffer.append(clean_line)
                    in_backtick_block = False
                    cls._assign_buffer_to_item(current_section, current_item, multiline_buffer)
                    multiline_buffer = []
                else:
                    multiline_buffer.append(raw_line)
                continue

            # Check if line is a TMDL property or new section header
            is_prop_or_header = cls._is_tmdl_property_or_header(line, current_section)

            # If we are currently accumulating an unquoted multiline expression and hit a property/header
            if multiline_buffer and not in_backtick_block and is_prop_or_header:
                cls._assign_buffer_to_item(current_section, current_item, multiline_buffer)
                multiline_buffer = []

            # 1. Check for start of top-level table declaration
            if line.startswith("table "):
                cls._flush_item(table_dict, current_section, current_item, multiline_buffer)
                multiline_buffer = []
                table_dict["name"] = unquote_name(line[6:].strip())
                current_section = "table"
                current_item = {}
                continue

            # 2. Check for column declaration:
            col_match = re.match(r"^column\s+('[^']+'|\[[^\]]+\]|[^\s=]+)(?:\s*=\s*(.*))?$", line)
            if col_match:
                cls._flush_item(table_dict, current_section, current_item, multiline_buffer)
                multiline_buffer = []
                current_section = "column"
                col_name = unquote_name(col_match.group(1))
                expr = col_match.group(2)
                is_calc = expr is not None

                current_item = {
                    "name": col_name,
                    "dataType": "Unknown",
                    "isHidden": False,
                    "isKey": False,
                    "type": "calculated" if is_calc else "data",
                    "expression": "",
                    "formatString": "",
                    "description": "",
                    "sourceColumn": "",
                    "dataCategory": "",
                    "summarizeBy": "",
                    "hasDateVariation": False,
                    "defaultHierarchy": "",
                    "annotations": [],
                }

                if is_calc and expr is not None:
                    expr = expr.strip()
                    if expr.startswith("```"):
                        if expr.endswith("```") and len(expr) > 3:
                            current_item["expression"] = expr[3:-3].strip()
                        else:
                            in_backtick_block = True
                            sub_expr = expr[3:].strip()
                            if sub_expr:
                                multiline_buffer.append(sub_expr)
                    elif expr:
                        multiline_buffer.append(expr)
                continue

            # 3. Check for measure declaration:
            meas_match = re.match(r"^measure\s+('[^']+'|\[[^\]]+\]|[^\s=]+)(?:\s*=\s*(.*))?$", line)
            if meas_match:
                cls._flush_item(table_dict, current_section, current_item, multiline_buffer)
                multiline_buffer = []
                current_section = "measure"
                meas_name = unquote_name(meas_match.group(1))
                expr = (meas_match.group(2) or "").strip()

                current_item = {
                    "name": meas_name,
                    "expression": "",
                    "formatString": "",
                    "description": "",
                    "isHidden": False,
                    "lineageTag": "",
                    "annotations": [],
                }

                if expr.startswith("```"):
                    if expr.endswith("```") and len(expr) > 3:
                        current_item["expression"] = expr[3:-3].strip()
                    else:
                        in_backtick_block = True
                        sub_expr = expr[3:].strip()
                        if sub_expr:
                            multiline_buffer.append(sub_expr)
                elif expr:
                    multiline_buffer.append(expr)
                continue

            # 4. Check for partition declaration:
            part_match = re.match(r"^partition\s+('[^']+'|[^\s=]+)\s*=\s*(.*)$", line)
            if part_match:
                cls._flush_item(table_dict, current_section, current_item, multiline_buffer)
                multiline_buffer = []
                current_section = "partition"
                part_name = unquote_name(part_match.group(1))
                part_type = part_match.group(2).strip()
                current_item = {
                    "name": part_name,
                    "mode": "import",
                    "source": {
                        "type": part_type,
                        "expression": "",
                    },
                }
                continue

            # If we are currently accumulating an unquoted multiline expression and line is NOT a property/header
            if current_section in ["measure", "column", "partition"] and not is_prop_or_header and not in_backtick_block:
                multiline_buffer.append(raw_line)
                continue

            # Check for properties within current_section
            if current_section == "table":
                if line == "isHidden" or line.startswith("isHidden:"):
                    table_dict["isHidden"] = True if line == "isHidden" else "true" in line.lower()
                elif line.startswith("description:"):
                    table_dict["description"] = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("dataCategory:"):
                    table_dict["dataCategory"] = line.split(":", 1)[1].strip()
                elif line.startswith("annotation "):
                    m_ann = re.match(r"^annotation\s+([^\s=]+)\s*=\s*(.*)$", line)
                    if m_ann:
                        table_dict["annotations"].append({"name": m_ann.group(1), "value": m_ann.group(2).strip('"')})

            elif current_section == "column":
                if line == "isHidden" or line.startswith("isHidden:"):
                    current_item["isHidden"] = True if line == "isHidden" else "true" in line.lower()
                elif line == "isKey" or line.startswith("isKey:"):
                    current_item["isKey"] = True if line == "isKey" else "true" in line.lower()
                elif line.startswith("dataType:"):
                    current_item["dataType"] = line.split(":", 1)[1].strip()
                elif line.startswith("formatString:"):
                    current_item["formatString"] = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("description:"):
                    current_item["description"] = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("sourceColumn:"):
                    current_item["sourceColumn"] = unquote_name(line.split(":", 1)[1].strip())
                elif line.startswith("dataCategory:"):
                    current_item["dataCategory"] = line.split(":", 1)[1].strip()
                elif line.startswith("summarizeBy:"):
                    current_item["summarizeBy"] = line.split(":", 1)[1].strip()
                elif line.startswith(("variation", "dateTime variation")) or line == "isDefault" or line.startswith(("defaultHierarchy:", "relationship:")):
                    current_item["hasDateVariation"] = True
                    if line.startswith("defaultHierarchy:"):
                        current_item["defaultHierarchy"] = line.split(":", 1)[1].strip()
                elif line.startswith("annotation "):
                    m_ann = re.match(r"^annotation\s+([^\s=]+)\s*=\s*(.*)$", line)
                    if m_ann:
                        current_item["annotations"].append({"name": m_ann.group(1), "value": m_ann.group(2).strip('"')})

            elif current_section == "measure":
                if line == "isHidden" or line.startswith("isHidden:"):
                    current_item["isHidden"] = True if line == "isHidden" else "true" in line.lower()
                elif line.startswith("formatString:"):
                    current_item["formatString"] = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("description:"):
                    current_item["description"] = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("lineageTag:"):
                    current_item["lineageTag"] = line.split(":", 1)[1].strip()
                elif line.startswith("annotation "):
                    m_ann = re.match(r"^annotation\s+([^\s=]+)\s*=\s*(.*)$", line)
                    if m_ann:
                        current_item["annotations"].append({"name": m_ann.group(1), "value": m_ann.group(2).strip('"')})

            elif current_section == "partition":
                if line.startswith("mode:"):
                    current_item["mode"] = line.split(":", 1)[1].strip()
                elif line.startswith("source =") or line.startswith("source:"):
                    source_part = line.split("=", 1)[1].strip() if "=" in line else line.split(":", 1)[1].strip()
                    if source_part.startswith("```"):
                        in_backtick_block = True
                        sub = source_part[3:].strip()
                        if sub:
                            multiline_buffer.append(sub)
                    elif source_part:
                        multiline_buffer.append(source_part)

        # Flush trailing item
        cls._flush_item(table_dict, current_section, current_item, multiline_buffer)
        return table_dict

    @classmethod
    def _is_tmdl_property_or_header(cls, line: str, section: str) -> bool:
        """Check if line is a recognized TMDL property or new section header."""
        s = line.strip()
        if not s:
            return False

        if s.startswith(("column ", "measure ", "partition ", "table ", "relationship ", "expression ")):
            return True

        if section == "table":
            if s == "isHidden" or s.startswith(("isHidden:", "description:", "dataCategory:", "annotation ", "lineageTag:")):
                return True
        elif section == "column":
            if s in ["isHidden", "isKey", "isUnique", "isNullable", "isDefault"] or s.startswith((
                "isHidden:", "isKey:", "isUnique:", "isNullable:", "dataType:", "formatString:",
                "description:", "sourceColumn:", "sourceProviderType:", "dataCategory:",
                "summarizeBy:", "displayFolder:", "sortByColumn:", "annotation ", "lineageTag:",
                "variation", "dateTime variation", "relationship:", "defaultHierarchy:", "hierarchy ", "level "
            )):
                return True
        elif section == "measure":
            if s == "isHidden" or s.startswith((
                "isHidden:", "formatString:", "description:", "lineageTag:", "dataCategory:",
                "displayFolder:", "kpi:", "kpi ", "annotation "
            )):
                return True
        elif section == "partition":
            if s.startswith(("mode:", "source =", "source:", "annotation ", "lineageTag:")):
                return True

        return False

    @classmethod
    def _assign_buffer_to_item(cls, section: str, item: Dict[str, Any], buffer: List[str]) -> None:
        """Clean and assign accumulated multiline buffer to current item."""
        if not buffer or not item:
            return

        # Clean common leading indent
        cleaned_lines = cls._clean_indentation(buffer)
        expr_str = "\n".join(cleaned_lines).strip()

        if section == "measure":
            item["expression"] = expr_str
        elif section == "column":
            item["expression"] = expr_str
        elif section == "partition":
            item.setdefault("source", {})["expression"] = expr_str

    @classmethod
    def _clean_indentation(cls, buffer: List[str]) -> List[str]:
        """Strip common leading tab or whitespace indentation from buffer lines."""
        if not buffer:
            return []

        # Determine minimum indentation on non-empty lines
        min_indent = None
        for line in buffer:
            if not line.strip():
                continue
            indent_len = len(line) - len(line.lstrip())
            if min_indent is None or indent_len < min_indent:
                min_indent = indent_len

        if not min_indent:
            return [line.rstrip() for line in buffer]

        result = []
        for line in buffer:
            if len(line) >= min_indent:
                result.append(line[min_indent:].rstrip())
            else:
                result.append(line.strip())
        return result

    @classmethod
    def _flush_item(cls, table_dict: Dict[str, Any], section: str, item: Dict[str, Any], buffer: List[str] = None) -> None:
        """Store completed column, measure, or partition item in the table dict."""
        if not item or not item.get("name"):
            return

        if buffer:
            cls._assign_buffer_to_item(section, item, buffer)

        if section == "column":
            table_dict["columns"].append(item)
        elif section == "measure":
            table_dict["measures"].append(item)
        elif section == "partition":
            table_dict["partitions"].append(item)

    @classmethod
    def parse_relationships_file(cls, filepath: str) -> List[Dict[str, Any]]:
        """Parse relationships.tmdl file into a list of relationship dictionaries."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read relationships file {filepath}: {e}")
            return []

        relationships: List[Dict[str, Any]] = []
        lines = content.splitlines()

        current_rel: Optional[Dict[str, Any]] = None

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("//"):
                continue

            if line.startswith("relationship "):
                if current_rel:
                    relationships.append(current_rel)
                rel_id = line[13:].strip()
                current_rel = {
                    "id": rel_id,
                    "fromTable": "",
                    "fromColumn": "",
                    "toTable": "",
                    "toColumn": "",
                    "cardinality": "manyToOne",
                    "crossFilteringBehavior": "oneDirection",
                    "isActive": True,
                }
                continue

            if current_rel is None:
                # In case relationship header is missing or simple format
                current_rel = {
                    "fromTable": "",
                    "fromColumn": "",
                    "toTable": "",
                    "toColumn": "",
                    "cardinality": "manyToOne",
                    "crossFilteringBehavior": "oneDirection",
                    "isActive": True,
                }

            if line.startswith("fromColumn:"):
                col_ref = line.split(":", 1)[1].strip()
                t, c = parse_column_reference(col_ref)
                current_rel["fromTable"] = t
                current_rel["fromColumn"] = c
            elif line.startswith("toColumn:"):
                col_ref = line.split(":", 1)[1].strip()
                t, c = parse_column_reference(col_ref)
                current_rel["toTable"] = t
                current_rel["toColumn"] = c
            elif line.startswith("cardinality:"):
                current_rel["cardinality"] = line.split(":", 1)[1].strip()
            elif line.startswith("crossFilteringBehavior:"):
                current_rel["crossFilteringBehavior"] = line.split(":", 1)[1].strip()
            elif line.startswith("isActive:"):
                val = line.split(":", 1)[1].strip().lower()
                current_rel["isActive"] = val == "true"

        if current_rel and (current_rel.get("fromTable") or current_rel.get("toTable")):
            relationships.append(current_rel)

        return relationships

    @classmethod
    def parse_expressions_file(cls, filepath: str) -> List[Dict[str, Any]]:
        """Parse expressions.tmdl for shared M queries and parameters."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read expressions file {filepath}: {e}")
            return []

        expressions: List[Dict[str, Any]] = []
        lines = content.splitlines()

        current_expr: Optional[Dict[str, Any]] = None
        in_backtick = False
        buf: List[str] = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("//"):
                continue

            if in_backtick:
                if line.endswith("```") or line == "```":
                    clean = line[:-3].strip() if line.endswith("```") else ""
                    if clean:
                        buf.append(clean)
                    in_backtick = False
                    if current_expr:
                        current_expr["expression"] = "\n".join(buf)
                    buf = []
                else:
                    buf.append(raw_line)
                continue

            expr_match = re.match(r"^expression\s+('[^']+'|[^\s=]+)(?:\s*=\s*(.*))?$", line)
            if expr_match:
                if current_expr:
                    expressions.append(current_expr)
                name = unquote_name(expr_match.group(1))
                val = expr_match.group(2) or ""
                current_expr = {"name": name, "expression": "", "kind": "m"}
                val = val.strip()
                if val.startswith("```"):
                    in_backtick = True
                    buf = []
                else:
                    current_expr["expression"] = val
                continue

            if current_expr and line.startswith("kind:"):
                current_expr["kind"] = line.split(":", 1)[1].strip()

        if current_expr:
            expressions.append(current_expr)

        return expressions

