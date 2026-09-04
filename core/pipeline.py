"""Shared PBIP analysis pipeline used by the Streamlit application."""
from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, Tuple

from extractors.pbip_reader import PBIPReader
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


def analyze_pbip_zip(zip_path: str) -> Tuple[Dict[str, Any], str]:
    """Analyze a PBIP ZIP and return normalized metadata plus provider name."""
    with PBIPReader.read_zip(zip_path) as project:
        model_ext = ModelExtractor(project)
        model_info = model_ext.get_model_info()
        tables = model_ext.get_tables()
        columns = model_ext.get_columns()
        calc_columns = model_ext.get_calculated_columns()
        measures = model_ext.get_measures()
        raw_rels = model_ext.get_raw_relationships()
        raw_partitions = model_ext.get_raw_partitions_and_expressions()

        report_ext = ReportExtractor(project)
        pages = report_ext.get_pages()
        visuals = report_ext.get_visuals()

        sources = SourceExtractor.extract_sources(raw_partitions)

        rel_analyzer = RelationshipAnalyzer(raw_rels)
        relationships = rel_analyzer.get_relationships()
        key_columns = rel_analyzer.get_key_columns()
        rel_metrics = rel_analyzer.get_summary_metrics()

        date_analyzer = DateTableAnalyzer(model_ext.raw_model.get("model", {}).get("tables", []))
        date_summary = date_analyzer.get_date_table_summary()
        date_tables = date_analyzer.get_date_tables_list()

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
            "dax_analysis": dax_optimizer.get_analysis_sheet_data(),
            "dax_improvements": dax_optimizer.get_improvements_sheet_data(),
            "dax_complexity": dax_optimizer.get_complexity_sheet_data(),
            "phase3_summary": dax_optimizer.get_phase3_summary_metrics(),
        }

        metadata["project_name"] = project.project_name
        metadata["model_format"] = project.model_format.value
        metadata["report_format"] = project.report_format.value
        metadata["ai_provider"] = ai_provider.provider_name
        metadata["ai_available"] = ai_provider.is_available()

        return metadata, ai_provider.provider_name


def write_excel(metadata: Dict[str, Any], output_path: str) -> str:
    return ExcelGenerator.generate_report(metadata, output_path)
