"""Power BI PBIP Report Analyzer — Flask Web Application.

Phase 1, Phase 2 & Phase 3: Metadata, Lineage, DAX Quality & AI-Assisted Optimization.
"""

import os
import logging
from datetime import datetime
from flask import Flask, request, render_template, send_from_directory
from werkzeug.utils import secure_filename

from extractors.pbip_reader import PBIPReader, PBIPExtractionError
from extractors.model_extractor import ModelExtractor
from extractors.report_extractor import ReportExtractor
from extractors.source_extractor import SourceExtractor
from analyzers.relationship_analyzer import RelationshipAnalyzer
from analyzers.date_table_analyzer import DateTableAnalyzer
from analyzers.dax_dependency_analyzer import DAXDependencyAnalyzer, ModelCatalog
from analyzers.visual_usage_analyzer import VisualUsageAnalyzer
from analyzers.object_usage_analyzer import ObjectUsageAnalyzer
from ai.dax_optimizer import DAXOptimizer
from ai.provider import get_ai_provider
from output.excel_generator import ExcelGenerator

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["OUTPUT_FOLDER"] = OUTPUT_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024  # 250 MB


@app.route("/", methods=["GET"])
def index():
    """Render the upload landing page."""
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    """Handle PBIP ZIP file upload and trigger full Phase 1, 2 & 3 metadata and optimization pipeline."""
    if "file" not in request.files:
        logger.warning("Upload attempt with no file field in request.")
        return render_template("upload.html", error="No file part in request."), 400

    file = request.files["file"]
    if file.filename == "":
        logger.warning("Upload attempt with empty filename.")
        return render_template("upload.html", error="No file selected."), 400

    if not file.filename.lower().endswith(".zip"):
        logger.warning(f"Rejected non-ZIP file upload: {file.filename}")
        return render_template("upload.html", error="Only .zip files containing a PBIP project are supported."), 400

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = secure_filename(file.filename)
    zip_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{timestamp}_{safe_name}")
    file.save(zip_path)
    logger.info(f"Saved uploaded ZIP to: {zip_path}")

    try:
        # Extract and parse PBIP project safely
        with PBIPReader.read_zip(zip_path) as project:
            logger.info(f"Processing project '{project.project_name}' (Model: {project.model_format.value}, Report: {project.report_format.value})")

            # 1. Semantic Model Extraction (Phase 1)
            model_ext = ModelExtractor(project)
            model_info = model_ext.get_model_info()
            tables = model_ext.get_tables()
            columns = model_ext.get_columns()
            calc_columns = model_ext.get_calculated_columns()
            measures = model_ext.get_measures()
            raw_rels = model_ext.get_raw_relationships()
            raw_partitions = model_ext.get_raw_partitions_and_expressions()

            # 2. Report PBIR Extraction (Phase 1)
            report_ext = ReportExtractor(project)
            pages = report_ext.get_pages()
            visuals = report_ext.get_visuals()

            # 3. Source Extraction (Phase 1)
            sources = SourceExtractor.extract_sources(raw_partitions)

            # 4. Phase 1 Analyzers
            rel_analyzer = RelationshipAnalyzer(raw_rels)
            relationships = rel_analyzer.get_relationships()
            key_columns = rel_analyzer.get_key_columns()
            rel_metrics = rel_analyzer.get_summary_metrics()

            date_analyzer = DateTableAnalyzer(model_ext.raw_model.get("model", {}).get("tables", []))
            date_summary = date_analyzer.get_date_table_summary()
            date_tables = date_analyzer.get_date_tables_list()

            # 5. Phase 2: Usage, Lineage & DAX Dependency Analysis
            catalog = ModelCatalog(tables, columns, measures, calc_columns)
            dax_analyzer = DAXDependencyAnalyzer(catalog, measures, calc_columns)
            visual_analyzer = VisualUsageAnalyzer(pages, visuals, catalog)

            object_usage_analyzer = ObjectUsageAnalyzer(
                catalog=catalog,
                direct_usages=visual_analyzer.get_direct_usages(),
                dax_analyzer=dax_analyzer,
                visual_analyzer=visual_analyzer,
                tables=tables,
                columns=columns,
                measures=measures,
                calc_columns=calc_columns,
            )

            object_usage = object_usage_analyzer.get_object_usage()
            visual_usage = object_usage_analyzer.get_visual_usage()
            dax_dependencies = object_usage_analyzer.get_dax_dependencies()
            usage_lineage = object_usage_analyzer.get_usage_lineage()
            unused_objects = object_usage_analyzer.get_unused_objects()
            phase2_summary = object_usage_analyzer.get_summary_metrics()

            # 6. Phase 3: DAX Quality Analysis & Optimization
            ai_provider = get_ai_provider()
            object_usage_map = {item.get("Object Name"): item for item in object_usage}
            for item in object_usage:
                can_id = f"{item.get('Object Type', '').upper()}:{item.get('Table', '')}[{item.get('Object Name', '')}]"
                object_usage_map[can_id] = item

            dax_optimizer = DAXOptimizer(
                catalog=catalog,
                measures=measures,
                calc_columns=calc_columns,
                object_usage_map=object_usage_map,
                ai_provider=ai_provider,
            )

            dax_analysis = dax_optimizer.get_analysis_sheet_data()
            dax_improvements = dax_optimizer.get_improvements_sheet_data()
            dax_complexity = dax_optimizer.get_complexity_sheet_data()
            phase3_summary = dax_optimizer.get_phase3_summary_metrics()

            # 7. Compile Full Normalized Metadata (18 Sheets)
            metadata = {
                "model_info": model_info,
                "tables": tables,
                "columns": columns,
                "calculated_columns": calc_columns,
                "measures": measures,
                "relationships": relationships,
                "key_columns": key_columns,
                "relationship_metrics": rel_metrics,
                "pages": pages,
                "visuals": visuals,
                "data_sources": sources,
                "date_table_summary": date_summary,
                "date_tables": date_tables,
                "object_usage": object_usage,
                "visual_usage": visual_usage,
                "dax_dependencies": dax_dependencies,
                "usage_lineage": usage_lineage,
                "unused_objects": unused_objects,
                "phase2_summary": phase2_summary,
                "dax_analysis": dax_analysis,
                "dax_improvements": dax_improvements,
                "dax_complexity": dax_complexity,
                "phase3_summary": phase3_summary,
            }

            # 8. Generate Excel Workbook (18 Sheets)
            excel_filename = f"PBIP_Analysis_{secure_filename(project.project_name)}_{timestamp}.xlsx"
            excel_path = os.path.join(app.config["OUTPUT_FOLDER"], excel_filename)
            ExcelGenerator.generate_report(metadata, excel_path)

            logger.info(f"Phase 1, 2 & 3 Analysis completed successfully for {project.project_name}")

            return render_template(
                "result.html",
                project_name=project.project_name,
                model_format=project.model_format.value,
                report_format=project.report_format.value,
                # Phase 1 Metrics
                num_tables=len(tables),
                num_columns=len(columns),
                num_measures=len(measures),
                num_calc_columns=len(calc_columns),
                num_relationships=len(relationships),
                active_relationships=rel_metrics.get("Active Relationships", 0),
                num_pages=len(pages),
                num_visuals=len(visuals),
                num_sources=len(sources),
                date_table_exists=date_summary.get("Date Table Exists", "Unknown"),
                date_table_name=date_summary.get("Date Table Name", "None"),
                # Phase 2 Metrics
                total_objects=phase2_summary.get("Total Objects", 0),
                used_objects=phase2_summary.get("Used Objects", 0),
                unused_objects=phase2_summary.get("Unused Objects", 0),
                directly_used=phase2_summary.get("Directly Used Objects", 0),
                indirectly_used=phase2_summary.get("Indirectly Used Objects", 0),
                dax_dependencies_count=phase2_summary.get("Dependency Edges", 0),
                unresolved_refs=phase2_summary.get("Unresolved DAX References", 0),
                circular_deps=phase2_summary.get("Circular Dependencies", 0),
                # Phase 3 Metrics
                ai_provider_name=ai_provider.provider_name,
                ai_available=ai_provider.is_available(),
                dax_objects_analyzed=phase3_summary.get("DAX Objects Analyzed", 0),
                potential_improvements=phase3_summary.get("Objects With Potential Improvements", 0),
                high_severity_count=phase3_summary.get("High Severity Issues", 0),
                medium_severity_count=phase3_summary.get("Medium Severity Issues", 0),
                low_severity_count=phase3_summary.get("Low Severity Issues", 0),
                ai_suggestions_count=phase3_summary.get("AI Suggestions", 0),
                manual_validation_count=phase3_summary.get("Suggestions Requiring Manual Validation", 0),
                excel_filename=excel_filename,
            )

    except PBIPExtractionError as e:
        logger.error(f"PBIP Extraction Error: {e}")
        return render_template("upload.html", error=f"PBIP Structure Error: {str(e)}"), 400
    except Exception as e:
        logger.exception(f"Unexpected error during PBIP analysis: {e}")
        return render_template("upload.html", error=f"Analysis failed: {str(e)}"), 500
    finally:
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except Exception as e:
                logger.debug(f"Could not remove uploaded zip {zip_path}: {e}")


@app.route("/download/<path:filename>", methods=["GET"])
def download_file(filename):
    """Download generated analysis Excel workbook."""
    safe_name = secure_filename(filename)
    return send_from_directory(app.config["OUTPUT_FOLDER"], safe_name, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
