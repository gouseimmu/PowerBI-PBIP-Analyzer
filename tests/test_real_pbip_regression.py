"""Regression test suite for real-world PBIP / TMDL extraction, multiline DAX, system table filtering, date variations, helper tables, and human-readable visual naming."""

import openpyxl
import pytest
from app import app
from extractors.pbip_reader import PBIPReader
from extractors.model_extractor import ModelExtractor
from extractors.report_extractor import ReportExtractor, normalize_visual_type
from extractors.source_extractor import SourceExtractor
from analyzers.date_table_analyzer import DateTableAnalyzer
from analyzers.relationship_analyzer import RelationshipAnalyzer
from analyzers.dax_dependency_analyzer import DAXDependencyAnalyzer, ModelCatalog
from analyzers.visual_usage_analyzer import VisualUsageAnalyzer
from analyzers.object_usage_analyzer import ObjectUsageAnalyzer
from ai.dax_optimizer import DAXOptimizer
from ai.provider import NullAIProvider
from output.excel_generator import ExcelGenerator
from tests.fixtures import create_mock_workforce_pbip_zip


@pytest.fixture
def workforce_pbip(tmp_path):
    zip_path = str(tmp_path / "workforce_report.zip")
    create_mock_workforce_pbip_zip(zip_path)
    return zip_path


def test_calculated_column_count_and_date_variations(workforce_pbip):
    """Assert calculated column count is exactly 4 and date variations are NOT misclassified as calc columns."""
    with PBIPReader.read_zip(workforce_pbip) as project:
        model_ext = ModelExtractor(project)
        calc_cols = model_ext.get_calculated_columns()
        calc_names = [c["Column"] for c in calc_cols]

        # 1. Exactly 4 intended calculated columns
        assert len(calc_cols) == 4
        assert "Employee Tenure" in calc_names
        assert "Employee Level" in calc_names
        assert "Repeated Calculation" in calc_names
        assert "Unsafe Margin" in calc_names

        # 2. Date columns with date variation metadata are NOT in calculated columns
        assert "CalendarDate" not in calc_names

        # 3. Columns list tags Date Variation = Yes
        all_cols = model_ext.get_columns()
        cal_date_col = next(c for c in all_cols if c["Table Name"] == "Calendar" and c["Column Name"] == "CalendarDate")
        assert cal_date_col["Column Type"] == "Data"
        assert cal_date_col["Date Variation"] == "Yes"


def test_helper_table_classification(workforce_pbip):
    """Assert _Measures is classified as a Helper table while business tables are Data tables."""
    with PBIPReader.read_zip(workforce_pbip) as project:
        model_ext = ModelExtractor(project)
        tables = model_ext.get_tables(include_system=False)
        tbl_map = {t["Table Name"]: t["Table Type"] for t in tables}

        assert tbl_map["_Measures"] == "Helper"
        assert tbl_map["Employee"] == "Data"
        assert tbl_map["Calendar"] == "Data"


def test_human_readable_visual_naming_and_types(workforce_pbip):
    """Assert visual names are human-readable, visual types are normalized, titles are blank when absent, and IDs are preserved."""
    with PBIPReader.read_zip(workforce_pbip) as project:
        report_ext = ReportExtractor(project)
        visuals = report_ext.get_visuals()

        assert len(visuals) > 0

        for v in visuals:
            # 1. Visual Title is blank when absent, never literal 'None'
            assert v["Visual Title"] != "None"

            # 2. Visual Type is normalized (e.g. Card, Line Chart, Table)
            assert v["Visual Type"] in ["Card", "Line Chart", "Table", "Matrix", "Slicer", "Text Box", "Unknown"]

            # 3. Visual Name is human-readable (not a hex GUID)
            assert not v["Visual Name"].startswith("0x")

            # 4. Visual ID is preserved
            assert v["Visual ID"] != ""

        # Test sequence numbering per page
        p1_visuals = [v for v in visuals if v["Page Name"] == "Workforce Overview"]
        p1_card_names = [v["Visual Name"] for v in p1_visuals if v["Visual Type"] == "Card"]
        assert "Billable Efficiency" in p1_card_names  # Priority 2: Visual Title used
        assert "Total Hours Card" in p1_card_names      # Priority 2: Visual Title used


def test_multiline_dax_extraction(workforce_pbip):
    with PBIPReader.read_zip(workforce_pbip) as project:
        model_ext = ModelExtractor(project)
        measures = {m["Measure Name"]: m["DAX Expression"] for m in model_ext.get_measures()}
        calc_cols = {c["Column"]: c["DAX Expression"] for c in model_ext.get_calculated_columns()}

        # 1. Billable %
        billable_pct = measures.get("Billable %", "")
        assert "DIVIDE(" in billable_pct
        assert "[Billable Hours]" in billable_pct
        assert "[Total Hours]" in billable_pct
        assert "\n" in billable_pct

        # 2. Project Start Count
        proj_start = measures.get("Project Start Count", "")
        assert "CALCULATE(" in proj_start
        assert "USERELATIONSHIP(" in proj_start
        assert "Calendar[CalendarDate]" in proj_start
        assert "Project[StartDate]" in proj_start

        # 3. Profitability Indicator
        profit_ind = measures.get("Profitability Indicator", "")
        assert "VAR Total =" in profit_ind
        assert "VAR Billable =" in profit_ind
        assert "RETURN" in profit_ind

        # 4. Unsafe Margin
        unsafe_margin = calc_cols.get("Unsafe Margin", "")
        assert "/" in unsafe_margin
        assert "[Total Employee Cost]" in unsafe_margin
        assert "[Total Hours]" in unsafe_margin


def test_system_table_exclusion(workforce_pbip):
    with PBIPReader.read_zip(workforce_pbip) as project:
        model_ext = ModelExtractor(project)

        # Default user-only tables (exclude system date tables)
        user_tables = [t["Table Name"] for t in model_ext.get_tables(include_system=False)]
        assert "Calendar" in user_tables
        assert "Employee" in user_tables
        assert "_Measures" in user_tables
        assert "LocalDateTable_a1b2c3d4-5678-90ef-1234-567890abcdef" not in user_tables
        assert "DateTableTemplate_b2c3d4e5-6789-01fa-2345-678901abcdef" not in user_tables


def test_date_table_detection(workforce_pbip):
    with PBIPReader.read_zip(workforce_pbip) as project:
        model_ext = ModelExtractor(project)
        date_analyzer = DateTableAnalyzer(model_ext.raw_model.get("model", {}).get("tables", []))
        dt_summary = date_analyzer.get_date_table_summary()
        dt_list = date_analyzer.get_date_tables_list()

        assert dt_summary["Date Table Exists"] == "Yes"
        assert dt_summary["Date Table Name"] == "Calendar"
        assert len(dt_list) == 1
        assert dt_list[0]["Table Name"] == "Calendar"
        assert dt_list[0]["Date Column"] == "CalendarDate"


def test_dax_dependency_parsing(workforce_pbip):
    with PBIPReader.read_zip(workforce_pbip) as project:
        model_ext = ModelExtractor(project)
        catalog = ModelCatalog(
            model_ext.get_tables(),
            model_ext.get_columns(),
            model_ext.get_measures(),
            model_ext.get_calculated_columns(),
        )
        dax_analyzer = DAXDependencyAnalyzer(
            catalog,
            model_ext.get_measures(),
            model_ext.get_calculated_columns(),
        )
        edges = dax_analyzer.get_edges()

        # Billable % -> Billable Hours & Total Hours
        b_pct_edges = [e for e in edges if e.source_name == "Billable %"]
        targets = [e.target_name for e in b_pct_edges]
        assert "Billable Hours" in targets
        assert "Total Hours" in targets

        # Project Start Count -> Calendar[CalendarDate] & Project[StartDate]
        proj_edges = [e for e in edges if e.source_name == "Project Start Count"]
        proj_targets = [(e.target_table, e.target_name) for e in proj_edges]
        assert ("Calendar", "CalendarDate") in proj_targets
        assert ("Project", "StartDate") in proj_targets


def test_transitive_usage_classification(workforce_pbip):
    with PBIPReader.read_zip(workforce_pbip) as project:
        model_ext = ModelExtractor(project)
        report_ext = ReportExtractor(project)

        catalog = ModelCatalog(
            model_ext.get_tables(),
            model_ext.get_columns(),
            model_ext.get_measures(),
            model_ext.get_calculated_columns(),
        )
        dax_analyzer = DAXDependencyAnalyzer(catalog, model_ext.get_measures(), model_ext.get_calculated_columns())
        visual_analyzer = VisualUsageAnalyzer(report_ext.get_pages(), report_ext.get_visuals(), catalog)

        obj_analyzer = ObjectUsageAnalyzer(
            catalog=catalog,
            direct_usages=visual_analyzer.get_direct_usages(),
            dax_analyzer=dax_analyzer,
            visual_analyzer=visual_analyzer,
            tables=model_ext.get_tables(),
            columns=model_ext.get_columns(),
            measures=model_ext.get_measures(),
            calc_columns=model_ext.get_calculated_columns(),
        )

        usage_map = {item["Object Name"]: item for item in obj_analyzer.get_object_usage()}

        # 1. Billable % is DIRECT (Visual 1)
        assert usage_map["Billable %"]["Used"] == "Yes"
        assert usage_map["Billable %"]["Usage Type"] == "Direct"

        # 2. Billable Hours is INDIRECT (via Billable %)
        assert usage_map["Billable Hours"]["Used"] == "Yes"
        assert usage_map["Billable Hours"]["Usage Type"] == "Indirect"

        # 3. Total Hours is DIRECT (Visual 3 & Visual 5) and used in multiple locations
        assert usage_map["Total Hours"]["Used"] == "Yes"
        assert usage_map["Total Hours"]["Usage Type"] == "Direct"
        assert usage_map["Total Hours"]["Usage Location Count"] >= 2

        # 4. Unused Training Count is UNUSED
        assert usage_map["Unused Training Count"]["Used"] == "No"
        assert usage_map["Unused Training Count"]["Usage Type"] == "Unused"


def test_self_and_inactive_relationships(workforce_pbip):
    with PBIPReader.read_zip(workforce_pbip) as project:
        model_ext = ModelExtractor(project)
        rel_analyzer = RelationshipAnalyzer(model_ext.get_raw_relationships())
        rels = rel_analyzer.get_relationships()

        # 1. Self-referencing relationship: Employee.ManagerID -> Employee.EmployeeID
        self_rel = next((r for r in rels if r["From Table"] == "Employee" and r["To Table"] == "Employee"), None)
        assert self_rel is not None
        assert self_rel["From Column"] == "ManagerID"
        assert self_rel["To Column"] == "EmployeeID"
        assert self_rel["Status"] == "Active"

        # 2. Inactive relationships: Calendar.CalendarDate -> Project.StartDate
        start_rel = next((r for r in rels if r["From Table"] == "Calendar" and r["To Column"] == "StartDate"), None)
        assert start_rel is not None
        assert start_rel["Status"] == "Inactive"


def test_userelationship_no_false_var_recommendation(workforce_pbip):
    """Assert USERELATIONSHIP is flagged as Informational and does NOT emit false VAR recommendation."""
    with PBIPReader.read_zip(workforce_pbip) as project:
        model_ext = ModelExtractor(project)
        report_ext = ReportExtractor(project)
        catalog = ModelCatalog(
            model_ext.get_tables(),
            model_ext.get_columns(),
            model_ext.get_measures(),
            model_ext.get_calculated_columns(),
        )
        dax_analyzer = DAXDependencyAnalyzer(catalog, model_ext.get_measures(), model_ext.get_calculated_columns())
        visual_analyzer = VisualUsageAnalyzer(report_ext.get_pages(), report_ext.get_visuals(), catalog)

        obj_analyzer = ObjectUsageAnalyzer(
            catalog=catalog,
            direct_usages=visual_analyzer.get_direct_usages(),
            dax_analyzer=dax_analyzer,
            visual_analyzer=visual_analyzer,
            tables=model_ext.get_tables(),
            columns=model_ext.get_columns(),
            measures=model_ext.get_measures(),
            calc_columns=model_ext.get_calculated_columns(),
        )

        object_usage_map = {item.get("Object Name"): item for item in obj_analyzer.get_object_usage()}

        optimizer = DAXOptimizer(
            catalog=catalog,
            measures=model_ext.get_measures(),
            calc_columns=model_ext.get_calculated_columns(),
            object_usage_map=object_usage_map,
            ai_provider=NullAIProvider(),
        )

        analysis = optimizer.get_analysis_sheet_data()
        proj_start_analysis = next((a for a in analysis if a["Object Name"] == "Project Start Count"), None)
        assert proj_start_analysis is not None
        # Does NOT have false VAR recommendation
        assert "VAR declarations" not in proj_start_analysis.get("Primary Issue", "")


def test_excel_preserves_multiline_dax(workforce_pbip, tmp_path):
    output_file = str(tmp_path / "workforce_analysis.xlsx")

    with PBIPReader.read_zip(workforce_pbip) as project:
        model_ext = ModelExtractor(project)
        report_ext = ReportExtractor(project)
        catalog = ModelCatalog(
            model_ext.get_tables(),
            model_ext.get_columns(),
            model_ext.get_measures(),
            model_ext.get_calculated_columns(),
        )
        dax_analyzer = DAXDependencyAnalyzer(catalog, model_ext.get_measures(), model_ext.get_calculated_columns())
        visual_analyzer = VisualUsageAnalyzer(report_ext.get_pages(), report_ext.get_visuals(), catalog)
        obj_analyzer = ObjectUsageAnalyzer(
            catalog=catalog,
            direct_usages=visual_analyzer.get_direct_usages(),
            dax_analyzer=dax_analyzer,
            visual_analyzer=visual_analyzer,
            tables=model_ext.get_tables(),
            columns=model_ext.get_columns(),
            measures=model_ext.get_measures(),
            calc_columns=model_ext.get_calculated_columns(),
        )
        object_usage_map = {item.get("Object Name"): item for item in obj_analyzer.get_object_usage()}
        optimizer = DAXOptimizer(
            catalog=catalog,
            measures=model_ext.get_measures(),
            calc_columns=model_ext.get_calculated_columns(),
            object_usage_map=object_usage_map,
            ai_provider=NullAIProvider(),
        )

        metadata = {
            "model_info": model_ext.get_model_info(),
            "tables": model_ext.get_tables(),
            "columns": model_ext.get_columns(),
            "calculated_columns": model_ext.get_calculated_columns(),
            "measures": model_ext.get_measures(),
            "relationships": RelationshipAnalyzer(model_ext.get_raw_relationships()).get_relationships(),
            "key_columns": RelationshipAnalyzer(model_ext.get_raw_relationships()).get_key_columns(),
            "relationship_metrics": RelationshipAnalyzer(model_ext.get_raw_relationships()).get_summary_metrics(),
            "pages": report_ext.get_pages(),
            "visuals": report_ext.get_visuals(),
            "data_sources": SourceExtractor.extract_sources(model_ext.get_raw_partitions_and_expressions()),
            "date_table_summary": DateTableAnalyzer(model_ext.raw_model.get("model", {}).get("tables", [])).get_date_table_summary(),
            "date_tables": DateTableAnalyzer(model_ext.raw_model.get("model", {}).get("tables", [])).get_date_tables_list(),
            "object_usage": obj_analyzer.get_object_usage(),
            "visual_usage": obj_analyzer.get_visual_usage(),
            "dax_dependencies": obj_analyzer.get_dax_dependencies(),
            "usage_lineage": obj_analyzer.get_usage_lineage(),
            "unused_objects": obj_analyzer.get_unused_objects(),
            "phase2_summary": obj_analyzer.get_summary_metrics(),
            "dax_analysis": optimizer.get_analysis_sheet_data(),
            "dax_improvements": optimizer.get_improvements_sheet_data(),
            "dax_complexity": optimizer.get_complexity_sheet_data(),
            "phase3_summary": optimizer.get_phase3_summary_metrics(),
        }

        ExcelGenerator.generate_report(metadata, output_file)

        wb = openpyxl.load_workbook(output_file)
        assert len(wb.sheetnames) == 9

        # Check Measures & Calculated Columns sheet for multiline DAX
        meas_ws = wb["Measures & Calculated Columns"]
        b_pct_dax = None
        for row in meas_ws.iter_rows(min_row=5, values_only=True):
            if row[1] == "Billable %":
                b_pct_dax = row[3]  # DAX Expression column (index 3, 0-indexed)
                break

        assert b_pct_dax is not None
        assert "DIVIDE(" in b_pct_dax
        assert "[Billable Hours]" in b_pct_dax
        assert "\n" in b_pct_dax

        # Check Pages & Visuals column headers order
        vis_ws = wb["Pages & Visuals"]
        headers = [cell.value for cell in vis_ws[4]]
        assert headers[0] == "Page Name"
        assert headers[1] == "Visual Name"
        assert headers[2] == "Visual Type"
        assert headers[3] == "Visual Title"
        assert headers[4] == "Visual ID"
        assert headers[5] == "Page ID"
