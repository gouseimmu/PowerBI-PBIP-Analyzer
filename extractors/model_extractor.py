"""Semantic Model Metadata Extractor.

Normalizes metadata extracted from TMDL or model.bim / JSON into unified structures
for tables, columns, calculated columns, measures, and relationships.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional

from .pbip_reader import PBIPProject, ModelFormat
from .tmdl_parser import TMDLParser

logger = logging.getLogger(__name__)


def bool_to_yes_no(val: Optional[bool]) -> str:
    """Convert boolean or None to Yes / No / Unknown."""
    if val is True:
        return "Yes"
    elif val is False:
        return "No"
    return "Unknown"


def is_system_table(table_name: str, raw_table: Optional[Dict[str, Any]] = None) -> bool:
    """Identify Power BI auto date/time or internal system tables (LocalDateTable_*, DateTableTemplate_*)."""
    if not table_name:
        return False
    name_lower = table_name.lower().strip()
    if name_lower.startswith("localdatetable_") or name_lower.startswith("datetabletemplate_"):
        return True

    if raw_table:
        annotations = raw_table.get("annotations", [])
        if isinstance(annotations, list):
            for ann in annotations:
                if isinstance(ann, dict):
                    aname = ann.get("name", "")
                    if aname in ["__PBI_LocalDateTable", "__PBI_TemplateDateTable"]:
                        return True
        elif isinstance(annotations, dict):
            for k in annotations:
                if k in ["__PBI_LocalDateTable", "__PBI_TemplateDateTable"]:
                    return True
    return False


class ModelExtractor:
    """Extracts and normalizes semantic model metadata from a PBIP project."""

    def __init__(self, project: PBIPProject):
        self.project = project
        self.raw_model: Dict[str, Any] = {}
        self._extract_raw_model()

    def _extract_raw_model(self) -> None:
        """Load raw model dictionary based on detected format (TMDL vs BIM_JSON)."""
        if self.project.model_format == ModelFormat.TMDL:
            def_dir = self.project.model_definition_dir or self.project.model_dir
            if def_dir:
                self.raw_model = TMDLParser.parse_definition_dir(def_dir)
        elif self.project.model_format == ModelFormat.BIM_JSON:
            self._load_bim_json()
        else:
            logger.warning("No supported model format detected.")

    def _load_bim_json(self) -> None:
        """Search and load model.bim or JSON tabular model file."""
        model_dir = self.project.model_definition_dir or self.project.model_dir
        if not model_dir or not os.path.exists(model_dir):
            return

        json_file: Optional[str] = None
        # Check standard names first
        for name in ["model.bim", "model.json", "datamodel.json", "DataModel.json"]:
            cand = os.path.join(model_dir, name)
            if os.path.exists(cand):
                json_file = cand
                break

        # Fallback search
        if not json_file:
            for root, _, files in os.walk(model_dir):
                for f in files:
                    if f.lower().endswith(".bim") or f.lower() == "datamodel.json":
                        json_file = os.path.join(root, f)
                        break
                if json_file:
                    break

        if json_file and os.path.exists(json_file):
            try:
                with open(json_file, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                    # Normalize if wrapped
                    if "model" in data:
                        self.raw_model = data
                    else:
                        self.raw_model = {"name": data.get("name", "Model"), "model": data}
                    logger.info(f"Successfully loaded model JSON from: {json_file}")
            except Exception as e:
                logger.error(f"Failed to read model JSON file {json_file}: {e}")

    def get_model_info(self) -> Dict[str, Any]:
        """Extract high-level model information."""
        model_data = self.raw_model.get("model", {})
        model_name = (
            self.raw_model.get("name")
            or model_data.get("name")
            or (os.path.basename(self.project.model_dir) if self.project.model_dir else "Model")
        )

        return {
            "Report / Project Name": self.project.project_name,
            "Semantic Model Name": model_name,
            "Model Format": self.project.model_format.value,
            "Culture": model_data.get("culture", "Unknown"),
            "Compatibility Level": str(self.raw_model.get("compatibilityLevel", model_data.get("compatibilityLevel", "Unknown"))),
            "Source Query Culture": model_data.get("sourceQueryCulture", "Unknown"),
            "Default Data Source Version": model_data.get("defaultPowerBIDataSourceVersion", "Unknown"),
        }

def is_date_variation_expression(expr: Any) -> bool:
    """Check if expression content is Power BI date variation / hierarchy metadata rather than DAX."""
    if not expr:
        return False
    if isinstance(expr, list):
        expr_str = "\n".join(expr)
    else:
        expr_str = str(expr)
    expr_lower = expr_str.lower().strip()
    return expr_lower.startswith(("variation", "datetime variation", "isdefault", "relationship:", "defaulthierarchy:")) or "defaulthierarchy:" in expr_lower


class ModelExtractor:
    """Extracts and normalizes semantic model metadata from a PBIP project."""

    def __init__(self, project: PBIPProject):
        self.project = project
        self.raw_model: Dict[str, Any] = {}
        self._extract_raw_model()

    def _extract_raw_model(self) -> None:
        """Load raw model dictionary based on detected format (TMDL vs BIM_JSON)."""
        if self.project.model_format == ModelFormat.TMDL:
            def_dir = self.project.model_definition_dir or self.project.model_dir
            if def_dir:
                self.raw_model = TMDLParser.parse_definition_dir(def_dir)
        elif self.project.model_format == ModelFormat.BIM_JSON:
            self._load_bim_json()
        else:
            logger.warning("No supported model format detected.")

    def _load_bim_json(self) -> None:
        """Search and load model.bim or JSON tabular model file."""
        model_dir = self.project.model_definition_dir or self.project.model_dir
        if not model_dir or not os.path.exists(model_dir):
            return

        json_file: Optional[str] = None
        # Check standard names first
        for name in ["model.bim", "model.json", "datamodel.json", "DataModel.json"]:
            cand = os.path.join(model_dir, name)
            if os.path.exists(cand):
                json_file = cand
                break

        # Fallback search
        if not json_file:
            for root, _, files in os.walk(model_dir):
                for f in files:
                    if f.lower().endswith(".bim") or f.lower() == "datamodel.json":
                        json_file = os.path.join(root, f)
                        break
                if json_file:
                    break

        if json_file and os.path.exists(json_file):
            try:
                with open(json_file, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                    # Normalize if wrapped
                    if "model" in data:
                        self.raw_model = data
                    else:
                        self.raw_model = {"name": data.get("name", "Model"), "model": data}
                    logger.info(f"Successfully loaded model JSON from: {json_file}")
            except Exception as e:
                logger.error(f"Failed to read model JSON file {json_file}: {e}")

    def get_model_info(self) -> Dict[str, Any]:
        """Extract high-level model information."""
        model_data = self.raw_model.get("model", {})
        model_name = (
            self.raw_model.get("name")
            or model_data.get("name")
            or (os.path.basename(self.project.model_dir) if self.project.model_dir else "Model")
        )

        return {
            "Report / Project Name": self.project.project_name,
            "Semantic Model Name": model_name,
            "Model Format": self.project.model_format.value,
            "Culture": model_data.get("culture", "Unknown"),
            "Compatibility Level": str(self.raw_model.get("compatibilityLevel", model_data.get("compatibilityLevel", "Unknown"))),
            "Source Query Culture": model_data.get("sourceQueryCulture", "Unknown"),
            "Default Data Source Version": model_data.get("defaultPowerBIDataSourceVersion", "Unknown"),
        }

    def get_tables(self, include_system: bool = False) -> List[Dict[str, Any]]:
        """Extract table metadata."""
        tables: List[Dict[str, Any]] = []
        raw_tables = self.raw_model.get("model", {}).get("tables", [])

        for table in raw_tables:
            table_name = table.get("name", "")
            if not table_name:
                continue

            if not include_system and is_system_table(table_name, table):
                continue

            is_hidden = table.get("isHidden", False)
            description = table.get("description", "") or ""
            data_category = table.get("dataCategory", "") or ""

            table_type = "Data"
            if table_name.startswith("_") or table_name.lower() in ["_measures", "measures", "keymeasures", "_keymeasures"]:
                table_type = "Helper"

            tables.append({
                "Table Name": table_name,
                "Table Type": table_type,
                "Is Hidden": bool_to_yes_no(is_hidden),
                "Data Category": data_category if data_category else "None",
                "Description": description if description else "None",
            })

        logger.info(f"Extracted {len(tables)} tables (include_system={include_system}).")
        return tables

    def get_columns(self, include_system: bool = False) -> List[Dict[str, Any]]:
        """Extract all column metadata (standard, calculated, etc.)."""
        columns: List[Dict[str, Any]] = []
        raw_tables = self.raw_model.get("model", {}).get("tables", [])

        for table in raw_tables:
            table_name = table.get("name", "")
            if not include_system and is_system_table(table_name, table):
                continue

            for col in table.get("columns", []):
                col_name = col.get("name", "")
                if not col_name:
                    continue

                col_type_raw = col.get("type", "data")
                expr = col.get("expression", "")
                has_variation = bool(col.get("hasDateVariation")) or bool(col.get("variations")) or is_date_variation_expression(expr)

                if (col_type_raw in ["calculated", "calculatedTableColumn"] or (expr and not has_variation)):
                    col_type = "Calculated"
                else:
                    col_type = "Data"

                data_type = col.get("dataType", "Unknown")
                is_hidden = col.get("isHidden", False)
                description = col.get("description", "") or ""
                format_string = col.get("formatString", "") or ""
                source_col = col.get("sourceColumn", "") or ""

                columns.append({
                    "Table Name": table_name,
                    "Column Name": col_name,
                    "Data Type": data_type,
                    "Is Hidden": bool_to_yes_no(is_hidden),
                    "Column Type": col_type,
                    "Date Variation": bool_to_yes_no(has_variation),
                    "Format String": format_string if format_string else "None",
                    "Source Column": source_col if source_col else "None",
                    "Description": description if description else "None",
                })

        logger.info(f"Extracted {len(columns)} columns.")
        return columns

    def get_calculated_columns(self, include_system: bool = False) -> List[Dict[str, Any]]:
        """Extract calculated columns with DAX expressions."""
        calc_cols: List[Dict[str, Any]] = []
        raw_tables = self.raw_model.get("model", {}).get("tables", [])

        for table in raw_tables:
            table_name = table.get("name", "")
            if not include_system and is_system_table(table_name, table):
                continue

            for col in table.get("columns", []):
                col_type_raw = col.get("type", "")
                expr = col.get("expression", "")
                has_variation = bool(col.get("hasDateVariation")) or bool(col.get("variations")) or is_date_variation_expression(expr)

                if (col_type_raw in ["calculated", "calculatedTableColumn"] or (expr and not has_variation)):
                    if isinstance(expr, list):
                        expr = "\n".join(expr)

                    calc_cols.append({
                        "Table": table_name,
                        "Column": col.get("name", ""),
                        "Data Type": col.get("dataType", "Unknown"),
                        "DAX Expression": expr.strip() if expr else "Unknown",
                        "Is Hidden": bool_to_yes_no(col.get("isHidden", False)),
                    })

        logger.info(f"Extracted {len(calc_cols)} calculated columns.")
        return calc_cols

    def get_measures(self, include_system: bool = False) -> List[Dict[str, Any]]:
        """Extract measures with DAX expressions and metadata."""
        measures: List[Dict[str, Any]] = []
        raw_tables = self.raw_model.get("model", {}).get("tables", [])

        for table in raw_tables:
            table_name = table.get("name", "")
            if not include_system and is_system_table(table_name, table):
                continue

            for meas in table.get("measures", []):
                meas_name = meas.get("name", "")
                if not meas_name:
                    continue

                expr = meas.get("expression", "")
                if isinstance(expr, list):
                    expr = "\n".join(expr)

                measures.append({
                    "Table": table_name,
                    "Measure Name": meas_name,
                    "DAX Expression": expr.strip() if expr else "Unknown",
                    "Format String": meas.get("formatString", "") or "None",
                    "Is Hidden": bool_to_yes_no(meas.get("isHidden", False)),
                    "Description": meas.get("description", "") or "None",
                })

        logger.info(f"Extracted {len(measures)} measures.")
        return measures

    def get_raw_relationships(self, include_system: bool = False) -> List[Dict[str, Any]]:
        """Extract raw relationships from the model."""
        raw_rels = self.raw_model.get("model", {}).get("relationships", [])
        if include_system:
            return raw_rels

        filtered = []
        for rel in raw_rels:
            ftable = rel.get("fromTable", "")
            ttable = rel.get("toTable", "")
            if is_system_table(ftable) or is_system_table(ttable):
                continue
            filtered.append(rel)
        return filtered

    def get_raw_partitions_and_expressions(self, include_system: bool = False) -> List[Dict[str, Any]]:
        """Collect all partition queries and shared expressions for data source extraction."""
        items: List[Dict[str, Any]] = []
        raw_tables = self.raw_model.get("model", {}).get("tables", [])

        for table in raw_tables:
            table_name = table.get("name", "")
            if not include_system and is_system_table(table_name, table):
                continue

            for part in table.get("partitions", []):
                source = part.get("source", {})
                expr = source.get("expression", "") if isinstance(source, dict) else ""
                if isinstance(expr, list):
                    expr = "\n".join(expr)
                items.append({
                    "table": table_name,
                    "partition": part.get("name", ""),
                    "type": source.get("type", "m") if isinstance(source, dict) else "m",
                    "expression": expr.strip() if expr else "",
                })

        for expr_obj in self.raw_model.get("model", {}).get("expressions", []):
            expr = expr_obj.get("expression", "")
            if isinstance(expr, list):
                expr = "\n".join(expr)
            items.append({
                "table": f"[Shared Expression] {expr_obj.get('name', '')}",
                "partition": "shared",
                "type": expr_obj.get("kind", "m"),
                "expression": expr.strip() if expr else "",
            })

        return items

