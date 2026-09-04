import os
import json
import logging
import re
from typing import Dict, List, Any, Optional

from .pbip_reader import PBIPProject, ReportFormat

logger = logging.getLogger(__name__)


VISUAL_TYPE_NAME_MAP = {
    "card": "Card",
    "cardvisual": "Card",
    "columnchart": "Column Chart",
    "clusteredcolumnchart": "Clustered Column Chart",
    "barchart": "Bar Chart",
    "clusteredbarchart": "Clustered Bar Chart",
    "linechart": "Line Chart",
    "linestackedcolumncombochart": "Line and Stacked Column Chart",
    "lineclusteredcolumncombochart": "Line and Clustered Column Chart",
    "areachart": "Area Chart",
    "stackedareachart": "Stacked Area Chart",
    "piechart": "Pie Chart",
    "donutchart": "Donut Chart",
    "tableex": "Table",
    "table": "Table",
    "pivottable": "Matrix",
    "matrix": "Matrix",
    "slicer": "Slicer",
    "textbox": "Text Box",
    "image": "Image",
    "shape": "Shape",
    "basicshape": "Shape",
    "actionbutton": "Button",
    "button": "Button",
    "map": "Map",
    "filledmap": "Filled Map",
    "scatterchart": "Scatter Chart",
    "treemap": "Treemap",
    "funnel": "Funnel",
    "gauge": "Gauge",
    "waterfallchart": "Waterfall Chart",
    "decompositiontree": "Decomposition Tree",
    "pythonvisual": "Python Visual",
    "rvisual": "R Visual",
    "keyinfluencers": "Key Influencers",
}


def normalize_visual_type(raw_type: str) -> str:
    """Map internal camelCase Power BI visualType string to human-readable display name."""
    if not raw_type or raw_type == "Unknown":
        return "Unknown"
    cleaned = raw_type.strip()
    key = cleaned.lower()
    if key in VISUAL_TYPE_NAME_MAP:
        return VISUAL_TYPE_NAME_MAP[key]

    # Convert camelCase/PascalCase to Title Case (e.g. someNewType -> Some New Type)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", cleaned)
    return s.title()


def clean_title_value(val: Any) -> str:
    """Clean extracted title string, removing surrounding literal quotes if present."""
    if val is None:
        return ""
    s = str(val).strip()
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        s = s[1:-1].strip()
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        s = s[1:-1].strip()
    return s if s and s.lower() != "none" else ""


def extract_title_from_config(config_obj: Dict[str, Any]) -> str:
    """Helper to extract visual title from various PBIR / PBIX config JSON schemas."""
    # 1. Direct visual title property
    if "title" in config_obj and isinstance(config_obj["title"], str):
        return clean_title_value(config_obj["title"])

    # 2. singleVisual.vcObjects.title
    sv = config_obj.get("singleVisual", {})
    vc_objects = sv.get("vcObjects", {}) or config_obj.get("vcObjects", {}) or config_obj.get("visualContainerObjects", {}) or sv.get("visualContainerObjects", {})

    # Check title object in vc_objects
    title_obj = vc_objects.get("title", {})
    if isinstance(title_obj, list) and title_obj:
        title_obj = title_obj[0]

    if isinstance(title_obj, dict):
        props = title_obj.get("properties", {})
        text_prop = props.get("text", {})
        if isinstance(text_prop, dict):
            expr = text_prop.get("expr", {})
            if isinstance(expr, dict):
                literal = expr.get("Literal", {})
                if isinstance(literal, dict) and "Value" in literal:
                    return clean_title_value(literal["Value"])
            if "value" in text_prop:
                return clean_title_value(text_prop["value"])
        elif isinstance(text_prop, str):
            return clean_title_value(text_prop)

    # 3. Check objects.title
    objects = sv.get("objects", {}) or config_obj.get("objects", {})
    title_obj2 = objects.get("title", {})
    if isinstance(title_obj2, list) and title_obj2:
        title_obj2 = title_obj2[0]
    if isinstance(title_obj2, dict):
        props = title_obj2.get("properties", {})
        text_prop = props.get("text", {})
        if isinstance(text_prop, dict):
            expr = text_prop.get("expr", {})
            if isinstance(expr, dict):
                literal = expr.get("Literal", {})
                if isinstance(literal, dict) and "Value" in literal:
                    return clean_title_value(literal["Value"])

    # 4. Check text box content / paragraph text
    paragraphs = config_obj.get("paragraphs", [])
    if paragraphs and isinstance(paragraphs, list):
        text_runs = []
        for p in paragraphs:
            for run in p.get("textRuns", []):
                val = run.get("value", "")
                if val:
                    text_runs.append(val.strip())
        if text_runs:
            return clean_title_value(" ".join(text_runs))

    return ""


class ReportExtractor:
    """Extracts pages and visual elements from PBIR report definitions."""

    def __init__(self, project: PBIPProject):
        self.project = project
        self.pages: List[Dict[str, Any]] = []
        self.visuals: List[Dict[str, Any]] = []
        self._extract()

    def _extract(self) -> None:
        """Extract pages and visuals according to detected report format."""
        if self.project.report_format == ReportFormat.NONE or not self.project.report_dir:
            logger.info("No report directory found or format is NONE.")
            return

        report_dir = self.project.report_definition_dir or self.project.report_dir

        # Try PBIR pages directory first
        pages_dir = os.path.join(report_dir, "pages")
        if not os.path.isdir(pages_dir):
            def_pages = os.path.join(report_dir, "definition", "pages")
            if os.path.isdir(def_pages):
                pages_dir = def_pages

        if os.path.isdir(pages_dir):
            self._extract_pbir_pages(pages_dir)
            self._post_process_visuals()
            return

        # Fallback to report.json
        report_json_path = os.path.join(report_dir, "report.json")
        if not os.path.exists(report_json_path):
            report_json_path = os.path.join(report_dir, "definition", "report.json")

        if os.path.exists(report_json_path):
            self._extract_legacy_report_json(report_json_path)
            self._post_process_visuals()

    def _extract_pbir_pages(self, pages_dir: str) -> None:
        """Extract pages and visuals from modern PBIR folder structure."""
        logger.info(f"Extracting PBIR pages from: {pages_dir}")

        for page_folder in sorted(os.listdir(pages_dir)):
            page_path = os.path.join(pages_dir, page_folder)
            if not os.path.isdir(page_path):
                continue

            page_id = page_folder
            page_name = page_folder
            page_json_file = os.path.join(page_path, "page.json")

            if os.path.exists(page_json_file):
                try:
                    with open(page_json_file, "r", encoding="utf-8", errors="replace") as pf:
                        pdata = json.load(pf)
                        page_id = pdata.get("name", page_folder)
                        page_name = pdata.get("displayName", page_id)
                except Exception as e:
                    logger.warning(f"Error parsing page JSON {page_json_file}: {e}")

            self.pages.append({
                "Page ID": page_id,
                "Page Name": page_name,
                "raw_page": pdata if os.path.exists(page_json_file) else {},
            })

            # Check visuals subfolder
            visuals_dir = os.path.join(page_path, "visuals")
            if os.path.isdir(visuals_dir):
                for visual_folder in sorted(os.listdir(visuals_dir)):
                    v_path = os.path.join(visuals_dir, visual_folder)
                    if os.path.isdir(v_path):
                        v_json_file = os.path.join(v_path, "visual.json")
                        if os.path.exists(v_json_file):
                            self._parse_pbir_visual_file(v_json_file, page_id, page_name, visual_folder)
                    elif visual_folder.lower().endswith(".json"):
                        self._parse_pbir_visual_file(v_path, page_id, page_name, os.path.splitext(visual_folder)[0])

        logger.info(f"Extracted {len(self.pages)} pages and {len(self.visuals)} visuals.")

    def _parse_pbir_visual_file(self, visual_file: str, page_id: str, page_name: str, default_id: str) -> None:
        """Parse an individual visual.json file."""
        try:
            with open(visual_file, "r", encoding="utf-8", errors="replace") as vf:
                vdata = json.load(vf)

            visual_id = vdata.get("name", default_id)
            vis_inner = vdata.get("visual", {})

            visual_type = "Unknown"
            if isinstance(vis_inner, dict):
                visual_type = vis_inner.get("visualType", vdata.get("visualType", "Unknown"))
            elif "visualType" in vdata:
                visual_type = vdata["visualType"]

            title = extract_title_from_config(vis_inner if isinstance(vis_inner, dict) else vdata)
            if not title and isinstance(vdata, dict):
                title = extract_title_from_config(vdata)

            self.visuals.append({
                "Page ID": page_id,
                "Page Name": page_name,
                "Visual ID": visual_id,
                "Visual Name": visual_id,
                "Visual Type": visual_type,
                "Visual Title": title,
                "raw_data": vdata,
            })
        except Exception as e:
            logger.warning(f"Error parsing visual file {visual_file}: {e}")
            self.visuals.append({
                "Page ID": page_id,
                "Page Name": page_name,
                "Visual ID": default_id,
                "Visual Name": default_id,
                "Visual Type": "Unknown",
                "Visual Title": "",
                "raw_data": {},
            })

    def _extract_legacy_report_json(self, report_json_path: str) -> None:
        """Extract pages and visuals from legacy report.json file."""
        logger.info(f"Extracting legacy report definition from: {report_json_path}")
        try:
            with open(report_json_path, "r", encoding="utf-8", errors="replace") as f:
                rdata = json.load(f)

            sections = rdata.get("sections", [])
            for sec in sections:
                page_id = sec.get("name", "")
                page_name = sec.get("displayName", page_id)

                self.pages.append({
                    "Page ID": page_id,
                    "Page Name": page_name,
                    "raw_page": sec,
                })

                for vc in sec.get("visualContainers", []):
                    vc_id = str(vc.get("id", vc.get("name", "Unknown")))
                    config_raw = vc.get("config", {})
                    config_obj = {}
                    if isinstance(config_raw, str):
                        try:
                            config_obj = json.loads(config_raw)
                        except Exception:
                            config_obj = {}
                    elif isinstance(config_raw, dict):
                        config_obj = config_raw

                    sv = config_obj.get("singleVisual", {})
                    v_type = sv.get("visualType", config_obj.get("visualType", "Unknown"))
                    v_title = extract_title_from_config(config_obj)

                    raw_combined = dict(config_obj)
                    if "filters" in vc:
                        raw_combined["filters"] = vc["filters"]

                    self.visuals.append({
                        "Page ID": page_id,
                        "Page Name": page_name,
                        "Visual ID": vc_id,
                        "Visual Name": config_obj.get("name", vc_id),
                        "Visual Type": v_type,
                        "Visual Title": v_title,
                        "raw_data": raw_combined,
                    })

            logger.info(f"Extracted {len(self.pages)} pages and {len(self.visuals)} visuals from report.json.")
        except Exception as e:
            logger.error(f"Error reading report.json: {e}")

    def _post_process_visuals(self) -> None:
        """Normalize visual types, clean titles, and assign deterministic human-readable display names per page."""
        # Group visuals by Page ID to scope visual sequence numbers per page
        page_groups: Dict[str, List[Dict[str, Any]]] = {}
        for v in self.visuals:
            page_groups.setdefault(v["Page ID"], []).append(v)

        for pid, vlist in page_groups.items():
            type_counts: Dict[str, int] = {}
            for v in vlist:
                norm_type = normalize_visual_type(v.get("Visual Type", "Unknown"))
                v["Visual Type"] = norm_type

                title = v.get("Visual Title", "").strip()
                if title.lower() == "none":
                    title = ""
                v["Visual Title"] = title

                rdata = v.get("raw_data", {})
                v_id = v.get("Visual ID", "")

                # Check Priority 1: Explicit User / Report Display Name
                explicit_name = ""
                if isinstance(rdata, dict):
                    explicit_name = rdata.get("displayName") or rdata.get("customName") or ""
                    if not explicit_name and isinstance(rdata.get("visual"), dict):
                        explicit_name = rdata["visual"].get("displayName") or rdata["visual"].get("customName") or ""

                # If explicit_name is valid and not GUID-like
                if explicit_name and explicit_name != v_id and not re.match(r"^[0-9a-f]{8,}$", explicit_name, re.IGNORECASE):
                    v["Visual Name"] = explicit_name.strip()
                # Priority 2: Visual Title if present
                elif title:
                    v["Visual Name"] = title
                # Priority 3: Human-Readable Type + Sequence
                else:
                    type_counts[norm_type] = type_counts.get(norm_type, 0) + 1
                    seq = type_counts[norm_type]
                    v["Visual Name"] = f"{norm_type} {seq}"

    def get_pages(self) -> List[Dict[str, Any]]:
        """Return list of normalized pages."""
        return self.pages

    def get_visuals(self) -> List[Dict[str, Any]]:
        """Return list of normalized visuals."""
        return self.visuals
