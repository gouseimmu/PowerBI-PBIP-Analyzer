"""Date Table Analyzer.

Determines whether a date table is explicitly marked/configured as a date table
in the Power BI semantic model metadata without guessing based on column names.
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


from extractors.model_extractor import is_system_table


class DateTableAnalyzer:
    """Detects explicitly marked Date tables in Power BI semantic models."""

    def __init__(self, raw_tables: List[Dict[str, Any]]):
        self.raw_tables = raw_tables
        self.detected_date_tables: List[Dict[str, Any]] = []
        self._analyze()

    def _analyze(self) -> None:
        """Scan tables for explicit Date Table configuration."""
        for table in self.raw_tables:
            table_name = table.get("name", "")
            if not table_name or is_system_table(table_name, table):
                continue

            is_date_table = False
            reason = []
            date_col_name = "None"

            # 1. Check table dataCategory == 'Time'
            data_cat = str(table.get("dataCategory", "")).strip().lower()
            if data_cat == "time":
                is_date_table = True
                reason.append("dataCategory = 'Time'")

            # 2. Check annotations for explicit user date table markers
            annotations = table.get("annotations", [])
            user_date_ann_keys = ["isTableDate", "isCustomDateTable", "__PBI_IsDateTable", "isDateTable", "markAsDateTable"]
            
            if isinstance(annotations, list):
                for ann in annotations:
                    if isinstance(ann, dict):
                        ann_name = ann.get("name", "")
                        ann_val = str(ann.get("value", "")).lower()
                        if ann_name in user_date_ann_keys:
                            is_date_table = True
                            reason.append(f"Annotation: {ann_name}={ann_val}")
            elif isinstance(annotations, dict):
                for k, v in annotations.items():
                    if k in user_date_ann_keys:
                        is_date_table = True
                        reason.append(f"Annotation: {k}={v}")

            # 3. Check for markAsDateTable property
            if table.get("markAsDateTable") is True:
                is_date_table = True
                reason.append("markAsDateTable = True")

            # 4. Check for key column with dateTime / date type or time dataCategory
            for col in table.get("columns", []):
                col_name = col.get("name", "")
                col_cat = str(col.get("dataCategory", "")).strip().lower()
                dtype = str(col.get("dataType", "")).strip().lower()
                is_key = col.get("isKey") is True

                if is_key and (dtype in ["datetime", "date"] or col_cat == "time" or col_name.lower() in ["date", "calendardate"]):
                    is_date_table = True
                    date_col_name = col_name
                    reason.append(f"Key Column '{col_name}' (dataType={col.get('dataType', 'dateTime')})")
                    break

            if is_date_table:
                # If date_col_name not set yet, pick first date/datetime column
                if date_col_name == "None":
                    for col in table.get("columns", []):
                        dtype = str(col.get("dataType", "")).strip().lower()
                        cname = col.get("name", "")
                        if dtype in ["datetime", "date"] or cname.lower() in ["date", "calendardate"]:
                            date_col_name = cname
                            break

                self.detected_date_tables.append({
                    "Table Name": table_name,
                    "Date Column": date_col_name,
                    "Marked Reason": "; ".join(reason) if reason else "Explicitly marked date table",
                    "Is Hidden": "Yes" if table.get("isHidden", False) else "No",
                    "Total Columns": len(table.get("columns", [])),
                })

        logger.info(f"Identified {len(self.detected_date_tables)} explicitly marked user date tables.")

    def get_date_table_summary(self) -> Dict[str, str]:
        """Return executive summary values for date tables."""
        if not self.raw_tables:
            return {"Date Table Exists": "Unknown", "Date Table Name": "Unknown"}

        if self.detected_date_tables:
            names = ", ".join([dt["Table Name"] for dt in self.detected_date_tables])
            return {"Date Table Exists": "Yes", "Date Table Name": names}

        return {"Date Table Exists": "No", "Date Table Name": "None"}

    def get_date_tables_list(self) -> List[Dict[str, Any]]:
        """Return detailed list of identified date tables."""
        return self.detected_date_tables

