"""Streamlit UI for the Power BI PBIP Analyzer."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st

from core.pipeline import analyze_pbip_zip, write_excel

st.set_page_config(
    page_title="Power BI PBIP Analyzer",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
.block-container {max-width: 1400px; padding-top: 2rem;}
[data-testid="stMetric"] {border: 1px solid #e6e9ef; border-radius: 10px; padding: 12px;}
</style>
""", unsafe_allow_html=True)

st.title("📊 Power BI PBIP Analyzer")
st.caption("Analyze a PBIP project for semantic model inventory, report usage, DAX lineage and optimization opportunities.")

with st.sidebar:
    st.header("Analysis")
    st.info("Upload a ZIP containing a Power BI PBIP project. The analyzer reads TMDL and PBIR definitions; it does not require a PBIX file.")
    st.divider()
    ai_enabled = bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY")) and os.getenv("DISABLE_AI", "").lower() not in {"1", "true", "yes"}
    st.write("**AI provider:**", os.getenv("AI_PROVIDER", "auto"))
    st.write("**AI configured:**", "Yes" if ai_enabled else "No — static DAX analysis")

uploaded = st.file_uploader("Upload PBIP project ZIP", type=["zip"], help="Zip the entire PBIP project folder before uploading.")

if uploaded:
    st.success(f"Ready: {uploaded.name} ({uploaded.size / 1024 / 1024:.2f} MB)")

    if st.button("Analyze PBIP", type="primary", use_container_width=True):
        progress = st.progress(0, text="Saving uploaded PBIP ZIP…")
        with tempfile.TemporaryDirectory(prefix="pbip_analyzer_") as workdir:
            zip_path = Path(workdir) / uploaded.name
            zip_path.write_bytes(uploaded.getbuffer())
            progress.progress(10, text="Reading PBIP project…")
            try:
                metadata, provider_name = analyze_pbip_zip(str(zip_path))
                progress.progress(85, text="Generating compact 6-sheet Excel report…")
                excel_path = Path(workdir) / f"PBIP_Analysis_{metadata.get('project_name','Project')}.xlsx"
                write_excel(metadata, str(excel_path))
                excel_bytes = excel_path.read_bytes()
                progress.progress(100, text="Analysis complete")
                st.session_state["metadata"] = metadata
                st.session_state["excel_bytes"] = excel_bytes
                st.session_state["excel_name"] = excel_path.name
            except Exception as exc:
                progress.empty()
                st.error("Analysis failed")
                st.exception(exc)

metadata = st.session_state.get("metadata")
if metadata:
    st.divider()
    st.subheader(f"{metadata.get('project_name', 'PBIP Project')} — Analysis Results")

    p2 = metadata.get("phase2_summary", {})
    metrics = [
        ("Tables", len(metadata.get("tables", []))),
        ("Columns", len(metadata.get("columns", []))),
        ("Measures", len(metadata.get("measures", []))),
        ("Pages", len(metadata.get("pages", []))),
        ("Visuals", len(metadata.get("visuals", []))),
        ("Used Objects", p2.get("Used Objects", 0)),
        ("Unused Objects", p2.get("Unused Objects", 0)),
        ("DAX Dependencies", p2.get("Dependency Edges", 0)),
    ]
    cols = st.columns(4)
    for idx, (label, value) in enumerate(metrics):
        cols[idx % 4].metric(label, value)

    st.write(f"**AI provider:** {metadata.get('ai_provider', 'Unknown')}  ·  **AI available:** {'Yes' if metadata.get('ai_available') else 'No'}")

    left, right = st.columns(2)
    with left:
        st.markdown("### Usage overview")
        st.write({
            "Direct usage": p2.get("Directly Used Objects", 0),
            "Indirect usage": p2.get("Indirectly Used Objects", 0),
            "Unused objects": p2.get("Unused Objects", 0),
            "Unresolved DAX references": p2.get("Unresolved DAX References", 0),
            "Circular dependencies": p2.get("Circular Dependencies", 0),
        })
    with right:
        st.markdown("### Main deliverable")
        st.write("The generated workbook contains exactly 6 sheets:")
        st.write("1. Summary\n2. Model Inventory\n3. Report Usage\n4. Relationships & Lineage\n5. Data Sources\n6. DAX Analysis")

    st.download_button(
        "⬇️ Download Excel Report (6 Sheets)",
        data=st.session_state["excel_bytes"],
        file_name=st.session_state["excel_name"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )

    st.divider()
    st.subheader("Quick usage preview")
    usage = metadata.get("visual_usage", [])
    if usage:
        # Avoid adding a pandas dependency to the UI; Streamlit can render lists of dicts.
        st.dataframe(usage, use_container_width=True, hide_index=True)
    else:
        st.info("No visual usage records were extracted.")
