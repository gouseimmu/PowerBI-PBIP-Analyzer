"""PBIP Project Reader and Safe ZIP Extraction.

Validates and extracts ZIP files containing Power BI Projects (.pbip),
detects project structures dynamically, and identifies TMDL/BIM and PBIR formats.
"""

import os
import json
import zipfile
import tempfile
import shutil
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class ModelFormat(str, Enum):
    TMDL = "TMDL"
    BIM_JSON = "BIM_JSON"
    UNKNOWN = "UNKNOWN"


class ReportFormat(str, Enum):
    PBIR_PAGES = "PBIR_PAGES"
    LEGACY_REPORT_JSON = "LEGACY_REPORT_JSON"
    NONE = "NONE"


class PBIPExtractionError(Exception):
    """Raised when PBIP ZIP validation or folder structure detection fails."""
    pass


@dataclass
class PBIPProject:
    """Normalized representation of an extracted PBIP project."""
    project_name: str
    root_dir: str
    temp_dir: Optional[str]
    pbip_file_path: Optional[str]
    model_dir: Optional[str]
    model_definition_dir: Optional[str]
    model_format: ModelFormat
    report_dir: Optional[str]
    report_definition_dir: Optional[str]
    report_format: ReportFormat

    def cleanup(self):
        """Clean up extracted temporary files."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                logger.info(f"Cleaned up temporary extraction directory: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"Error cleaning up temp directory {self.temp_dir}: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


class PBIPReader:
    """Safely extracts and discovers Power BI PBIP project structures."""

    @classmethod
    def read_zip(cls, zip_path: str) -> PBIPProject:
        """Extract a ZIP file safely and discover the PBIP structure."""
        if not os.path.exists(zip_path):
            raise PBIPExtractionError(f"ZIP file not found: {zip_path}")

        if not zipfile.is_zipfile(zip_path):
            raise PBIPExtractionError(f"Uploaded file is not a valid ZIP archive: {zip_path}")

        temp_dir = tempfile.mkdtemp(prefix="pbi_extract_")
        logger.info(f"Extracting ZIP {zip_path} to temporary directory: {temp_dir}")

        try:
            cls._safe_extract(zip_path, temp_dir)
            project = cls._discover_project(temp_dir)
            project.temp_dir = temp_dir
            return project
        except Exception:
            # Clean up on failure
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    @classmethod
    def _safe_extract(cls, zip_path: str, extract_dir: str) -> None:
        """Extract ZIP safely, guarding against Zip Slip path traversal attacks."""
        resolved_extract_dir = os.path.abspath(extract_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                member_path = member.filename
                # Reject absolute paths or paths with parent traversal
                if os.path.isabs(member_path) or ".." in member_path.split("/") or ".." in member_path.split("\\"):
                    raise PBIPExtractionError(f"Zip-slip attack detected: malicious path in archive '{member_path}'")

                target_path = os.path.abspath(os.path.join(resolved_extract_dir, member_path))
                if not (target_path == resolved_extract_dir or target_path.startswith(resolved_extract_dir + os.sep)):
                    raise PBIPExtractionError(f"Zip-slip attack detected: path escapes extraction root '{member_path}'")

            # All members validated, perform extraction
            zf.extractall(resolved_extract_dir)

    @classmethod
    def _discover_project(cls, root_dir: str) -> PBIPProject:
        """Dynamically detect .pbip file, report folder, and semantic model folder."""
        # 1. Locate .pbip file
        pbip_files: List[str] = []
        for root, _, files in os.walk(root_dir):
            for file in files:
                if file.lower().endswith(".pbip"):
                    pbip_files.append(os.path.join(root, file))

        if not pbip_files:
            raise PBIPExtractionError("Invalid PBIP archive: No .pbip file found.")

        pbip_path = pbip_files[0]
        project_base_dir = os.path.dirname(pbip_path)
        project_name = os.path.splitext(os.path.basename(pbip_path))[0]
        logger.info(f"Discovered PBIP file: {pbip_path} (Project name: '{project_name}')")

        # Read pbip manifest if possible to check artifact hints
        pbip_manifest: Dict[str, Any] = {}
        try:
            with open(pbip_path, "r", encoding="utf-8") as f:
                pbip_manifest = json.load(f)
        except Exception as e:
            logger.debug(f"Could not parse .pbip as JSON: {e}")

        # 2. Locate Semantic Model Directory
        model_dir, model_def_dir, model_format = cls._find_semantic_model(root_dir, project_base_dir, pbip_manifest)
        if not model_dir or model_format == ModelFormat.UNKNOWN:
            raise PBIPExtractionError(
                "Semantic model folder could not be found or contains no supported model metadata (TMDL or model.bim)."
            )

        logger.info(f"Discovered Semantic Model at '{model_dir}' (Format: {model_format.value})")

        # 3. Locate Report Directory
        report_dir, report_def_dir, report_format = cls._find_report(root_dir, project_base_dir, pbip_manifest)
        if report_dir:
            logger.info(f"Discovered Report folder at '{report_dir}' (Format: {report_format.value})")
        else:
            logger.warning("Report folder could not be found in the PBIP archive.")
            report_format = ReportFormat.NONE

        return PBIPProject(
            project_name=project_name,
            root_dir=root_dir,
            temp_dir=None,
            pbip_file_path=pbip_path,
            model_dir=model_dir,
            model_definition_dir=model_def_dir,
            model_format=model_format,
            report_dir=report_dir,
            report_definition_dir=report_def_dir,
            report_format=report_format,
        )

    @classmethod
    def _find_semantic_model(
        cls, root_dir: str, project_base_dir: str, manifest: Dict[str, Any]
    ) -> tuple[Optional[str], Optional[str], ModelFormat]:
        """Find the semantic model directory and detect its format (TMDL vs BIM_JSON)."""
        candidate_dirs: List[str] = []

        # Check manifest artifacts if available
        artifacts = manifest.get("artifacts", [])
        for art in artifacts:
            if isinstance(art, dict) and art.get("type", "").lower() in ["semanticmodel", "dataset"]:
                art_path = art.get("path")
                if art_path:
                    cand = os.path.normpath(os.path.join(project_base_dir, art_path))
                    if os.path.exists(cand):
                        candidate_dirs.append(cand)

        # Scan for .SemanticModel or .Dataset folders, or folders with definition.pbism
        for root, dirs, files in os.walk(root_dir):
            for d in dirs:
                full_d = os.path.join(root, d)
                d_lower = d.lower()
                if d_lower.endswith(".semanticmodel") or d_lower.endswith(".dataset"):
                    if full_d not in candidate_dirs:
                        candidate_dirs.append(full_d)

            # Check if current directory has definition.pbism or model.bim or model.tmdl
            if "definition.pbism" in files or "model.bim" in files:
                if root not in candidate_dirs:
                    candidate_dirs.append(root)

        # Also search for any directory containing TMDL files
        for root, _, files in os.walk(root_dir):
            if any(f.lower().endswith(".tmdl") for f in files):
                parent = root
                # Check if this is 'definition' subfolder
                if os.path.basename(parent).lower() == "definition":
                    parent = os.path.dirname(parent)
                if parent not in candidate_dirs:
                    candidate_dirs.append(parent)

        # Inspect candidate directories to determine model definition path and format
        for cand in candidate_dirs:
            # 1. Check TMDL in definition/ or cand root
            def_path = os.path.join(cand, "definition")
            if os.path.isdir(def_path):
                if os.path.exists(os.path.join(def_path, "model.tmdl")) or any(
                    f.endswith(".tmdl") for f in os.listdir(def_path)
                ):
                    return cand, def_path, ModelFormat.TMDL
                if os.path.exists(os.path.join(def_path, "model.bim")):
                    return cand, def_path, ModelFormat.BIM_JSON

            # Check directly in cand
            if os.path.exists(os.path.join(cand, "model.tmdl")) or any(
                f.endswith(".tmdl") for f in os.listdir(cand) if os.path.isfile(os.path.join(cand, f))
            ):
                return cand, cand, ModelFormat.TMDL
            if os.path.exists(os.path.join(cand, "model.bim")):
                return cand, cand, ModelFormat.BIM_JSON

            # Check any .bim / .json tabular model in cand
            for root, _, files in os.walk(cand):
                for f in files:
                    if f.lower().endswith(".bim") or f.lower() == "model.json" or f.lower() == "datamodel.json":
                        return cand, root, ModelFormat.BIM_JSON

        return None, None, ModelFormat.UNKNOWN

    @classmethod
    def _find_report(
        cls, root_dir: str, project_base_dir: str, manifest: Dict[str, Any]
    ) -> tuple[Optional[str], Optional[str], ReportFormat]:
        """Find the report directory and detect its format (PBIR pages vs legacy)."""
        candidate_dirs: List[str] = []

        # Check manifest artifacts
        artifacts = manifest.get("artifacts", [])
        for art in artifacts:
            if isinstance(art, dict) and art.get("type", "").lower() == "report":
                art_path = art.get("path")
                if art_path:
                    cand = os.path.normpath(os.path.join(project_base_dir, art_path))
                    if os.path.exists(cand):
                        candidate_dirs.append(cand)

        # Scan for .Report folders or folders with definition.pbir
        for root, dirs, files in os.walk(root_dir):
            for d in dirs:
                if d.lower().endswith(".report"):
                    full_d = os.path.join(root, d)
                    if full_d not in candidate_dirs:
                        candidate_dirs.append(full_d)

            if "definition.pbir" in files or "report.json" in files:
                if root not in candidate_dirs:
                    candidate_dirs.append(root)

        for cand in candidate_dirs:
            # Check modern PBIR in definition/pages
            def_path = os.path.join(cand, "definition")
            if os.path.isdir(def_path):
                pages_dir = os.path.join(def_path, "pages")
                if os.path.isdir(pages_dir) or os.path.exists(os.path.join(def_path, "report.json")):
                    return cand, def_path, ReportFormat.PBIR_PAGES

            # Check pages in cand directly
            if os.path.isdir(os.path.join(cand, "pages")):
                return cand, cand, ReportFormat.PBIR_PAGES

            # Check report.json
            if os.path.exists(os.path.join(cand, "report.json")):
                return cand, cand, ReportFormat.LEGACY_REPORT_JSON

            # Check if cand has definition.pbir
            if os.path.exists(os.path.join(cand, "definition.pbir")):
                return cand, (def_path if os.path.isdir(def_path) else cand), ReportFormat.PBIR_PAGES

        # If no candidates matched specifically, return any .Report folder found
        if candidate_dirs:
            return candidate_dirs[0], candidate_dirs[0], ReportFormat.UNKNOWN

        return None, None, ReportFormat.NONE

