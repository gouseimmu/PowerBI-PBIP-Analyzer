"""Streamlit UI for the Power BI AI Governance & Optimization Platform."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from core.pipeline import analyze_pbip_zip, write_excel
from ai.provider import get_ai_provider
from ai.powerbi_assistant import PowerBIChatbot

st.set_page_config(
    page_title="Power BI AI Governance Platform",
    page_icon="🛡️",
    layout="wide",
)

st.session_state.setdefault("chat_history", [])

st.markdown("""
<style>
.block-container {max-width: 1400px; padding-top: 2rem;}
[data-testid="stMetric"] {border: 1px solid #e6e9ef; border-radius: 10px; padding: 12px; background-color: #ffffff;}
.health-score-card {border: 2px solid #1F497D; border-radius: 12px; padding: 20px; background-color: #F8FAFC;}
</style>
""", unsafe_allow_html=True)

st.title("🛡️ Power BI AI Governance & Optimization Platform")
st.caption("Deterministic PBIP Project Analysis with Optional Azure OpenAI Governance & DAX Optimization")

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Analysis Settings")
    st.info("Upload a ZIP containing a Power BI PBIP project folder (reading TMDL and PBIR definitions).")
    st.divider()

    ai_key = os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    ai_disabled_env = os.getenv("DISABLE_AI", "").lower() in {"1", "true", "yes"}
    ai_configured = bool(ai_key) and not ai_disabled_env

    enable_ai = st.checkbox("Enable AI DAX Optimization & Insights", value=ai_configured)

    st.divider()
    st.write("**AI Provider Status:**")
    if ai_configured and enable_ai:
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
        st.success(f"Azure OpenAI: Configured\n(Deployment: {deployment})")
    elif enable_ai and not ai_key:
        st.warning("Azure OpenAI: Not configured\n(Deterministic static analysis active)")
    else:
        st.info("AI Analysis: Disabled\n(Static DAX analysis active)")

    st.caption("API keys are never logged or stored.")

uploaded = st.file_uploader("Upload PBIP project ZIP file", type=["zip"], help="Zip your entire PBIP project folder before uploading.")

if uploaded:
    st.success(f"File uploaded: {uploaded.name} ({uploaded.size / 1024 / 1024:.2f} MB)")

    if st.button("🚀 Analyze PBIP Project", type="primary", use_container_width=True):
        progress = st.progress(0, text="Saving uploaded PBIP ZIP…")
        with tempfile.TemporaryDirectory(prefix="pbip_analyzer_") as workdir:
            zip_path = Path(workdir) / uploaded.name
            zip_path.write_bytes(uploaded.getbuffer())
            progress.progress(15, text="Parsing TMDL & PBIR definitions…")
            try:
                metadata, provider_name = analyze_pbip_zip(str(zip_path), enable_ai=enable_ai)
                progress.progress(80, text="Generating 6-sheet Excel report…")
                excel_path = Path(workdir) / f"PBIP_Analysis_{metadata.get('project_name','Project')}.xlsx"
                write_excel(metadata, str(excel_path))
                excel_bytes = excel_path.read_bytes()
                progress.progress(100, text="Analysis complete!")

                st.session_state["metadata"] = metadata
                st.session_state["excel_bytes"] = excel_bytes
                st.session_state["excel_name"] = excel_path.name
                # Reset chat history on new project analysis
                st.session_state["chat_history"] = []
            except Exception as exc:
                progress.empty()
                st.error("Analysis failed. Details are kept in application logs.")
                st.exception(exc)

metadata = st.session_state.get("metadata")
if metadata:
    st.divider()
    st.subheader(f"📊 {metadata.get('project_name', 'PBIP Project')} — Analysis Dashboard")

    p2 = metadata.get("phase2_summary", {})
    health = metadata.get("model_health", {})

    # Top KPI Metrics
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Model Health Score", f"{health.get('score', 100)}/100", health.get("grade", "A"))
    c2.metric("Tables", len(metadata.get("tables", [])))
    c3.metric("Columns", len(metadata.get("columns", [])))
    c4.metric("Measures", len(metadata.get("measures", [])))
    c5.metric("Pages / Visuals", f"{len(metadata.get('pages', []))} / {len(metadata.get('visuals', []))}")
    c6.metric("DAX Dependencies", p2.get("Dependency Edges", 0))

    st.markdown("---")

    # Main deliverable export notification
    col_left, col_right = st.columns([3, 1])
    with col_left:
        st.write("📄 **Generated Excel Workbook Deliverable**: **6 Excel sheets** (`Summary`, `Model Inventory`, `Report Usage`, `Relationships & Lineage`, `Data Sources`, `DAX Analysis`)")
    with col_right:
        st.download_button(
            "⬇️ Download Excel Report (6 Sheets)",
            data=st.session_state["excel_bytes"],
            file_name=st.session_state["excel_name"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )

    st.markdown("---")

    # Interactive Dashboard Tabs
    # Interactive Dashboard Tabs
t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([
    "🏥 Model Health",
    "📦 Model Inventory",
    "🖥️ Report Usage",
    "🔗 Lineage & Relationships",
    "🔌 Data Sources",
    "⚡ DAX Analysis",
    "🛡️ AI Governance Advisory",
    "🤖 AI Assistant",
])

    with t1:
        st.markdown("### PBIP Analyzer Model Health Score Breakdown")
        st.info(health.get("status_text", "Model health score calculated deterministically."))

        deductions = health.get("deductions", [])
        if deductions:
            st.markdown("#### Health Score Deductions & Factors")
            for d in deductions:
                st.warning(f"**[{d.get('impact')}] {d.get('title')}** ({d.get('category')})\n\n{d.get('description')}")
        else:
            st.success("🎉 No major model health risk factors detected!")

        st.markdown("#### Usage Classification Metrics")
        st.write({
            "Directly Used Objects": p2.get("Directly Used Objects", 0),
            "Indirectly Used Objects": p2.get("Indirectly Used Objects", 0),
            "Direct + Indirect Objects": p2.get("Direct + Indirect Objects", 0),
            "Unused Objects": p2.get("Unused Objects", 0),
            "Unresolved DAX References": p2.get("Unresolved DAX References", 0),
            "Circular Dependencies": p2.get("Circular Dependencies", 0),
        })

    with t2:
        st.markdown("### Semantic Model Inventory & Object Usage")
        inv = metadata.get("object_usage", [])
        if inv:
            st.dataframe(inv, use_container_width=True, hide_index=True)
        else:
            st.info("No model inventory items parsed.")

    with t3:
        st.markdown("### Report Visual → Semantic Object Usage")
        usage = metadata.get("visual_usage", [])
        if usage:
            st.dataframe(usage, use_container_width=True, hide_index=True)
        else:
            st.info("No visual usage items extracted.")

    with t4:
        st.markdown("### Relationships & DAX Dependency Lineage")
        rels = metadata.get("relationships", [])
        if rels:
            st.dataframe(rels, use_container_width=True, hide_index=True)

        st.markdown("#### DAX Dependency Edges")
        deps = metadata.get("dax_dependencies", [])
        if deps:
            st.dataframe(deps, use_container_width=True, hide_index=True)

    with t5:
        st.markdown("### Data Sources & Power Query M Expressions")
        srcs = metadata.get("data_sources", [])
        if srcs:
            st.dataframe(srcs, use_container_width=True, hide_index=True)

    with t6:
        st.markdown("### DAX Quality, Complexity & Recommendations")
        dax_data = metadata.get("dax_analysis", [])
        if dax_data:
            st.dataframe(dax_data, use_container_width=True, hide_index=True)

        st.markdown("#### Potential DAX Improvements")
        imps = metadata.get("dax_improvements", [])
        if imps:
            st.dataframe(imps, use_container_width=True, hide_index=True)

    with t7:
        st.markdown("### AI Model & Report Governance Advisory")
        doc = metadata.get("executive_documentation", {})
        if doc.get("overview"):
            st.markdown("#### Executive Summary")
            st.write(doc["overview"])

        col_m, col_r = st.columns(2)
        with col_m:
            st.markdown("#### Model Governance Advisory")
            m_adv = metadata.get("model_advisories", [])
            for item in m_adv:
                st.info(f"**{item.get('type')}** ({item.get('severity')})\n\n{item.get('description')}\n\n*Recommendation:* {item.get('recommendation')}")

        with col_r:
            st.markdown("#### Report Governance Advisory")
            r_adv = metadata.get("report_advisories", [])
            for item in r_adv:
                st.info(f"**{item.get('type')}** ({item.get('severity')})\n\n{item.get('description')}\n\n*Recommendation:* {item.get('recommendation')}")

    with t8:
        st.markdown("### 🤖 Power BI AI Assistant")
        st.caption("Ask questions about your Power BI model, report, DAX, dependencies, relationships, or data sources.")

        # Top control bar: Clear Chat
        ctrl_c1, ctrl_c2 = st.columns([4, 1])
        with ctrl_c2:
            if st.button("🗑️ Clear Chat", use_container_width=True):
                st.session_state["chat_history"] = []
                st.rerun()

        if not enable_ai or not ai_configured:
            st.info("AI Assistant is disabled. Enable AI analysis in the sidebar settings to use the chatbot.")
        else:
            chatbot = PowerBIChatbot(ai_provider=get_ai_provider())

            # Suggested Quick Action Questions
            st.markdown("#### Suggested Questions")
            q_cols = st.columns(3)
            with q_cols[0]:
                if st.button("📊 Model Summary", use_container_width=True):
                    st.session_state["pending_chat_prompt"] = "Give me an executive summary of this Power BI model."
                if st.button("🔌 Source Summary", use_container_width=True):
                    st.session_state["pending_chat_prompt"] = "What data sources and Power Query expressions are used?"
            with q_cols[1]:
                if st.button("🧹 Unused Objects", use_container_width=True):
                    st.session_state["pending_chat_prompt"] = "Which tables, measures, or columns are unused?"
                if st.button("🔗 Relationship Issues", use_container_width=True):
                    st.session_state["pending_chat_prompt"] = "Which relationships use bidirectional filtering or are inactive?"
            with q_cols[2]:
                if st.button("⚡ Top DAX Issues", use_container_width=True):
                    st.session_state["pending_chat_prompt"] = "Which measures have the highest complexity or DAX quality issues?"
                if st.button("🏥 Health Score", use_container_width=True):
                    st.session_state["pending_chat_prompt"] = "Explain the factors affecting my Model Health Score."

            st.markdown("---")

            # Chat History Container
            chat_container = st.container()
            with chat_container:
                if not st.session_state["chat_history"]:
                    st.info(
                        "👋 **I'm your Power BI AI Assistant.**\n\n"
                        "I can answer technical questions about your analyzed PBIP project, including:\n"
                        "• Which tables or measures are unused?\n"
                        "• Explain my most complex measure.\n"
                        "• Which visuals use `[Total Revenue]`?\n"
                        "• What relationships use bidirectional filtering?\n"
                        "• What should I optimize first?"
                    )
                else:
                    for msg in st.session_state["chat_history"]:
                        with st.chat_message(msg["role"]):
                            st.markdown(msg["content"])

            # Prompt input
            user_prompt = st.chat_input("Ask a question about your Power BI model, DAX, dependencies, or report...")
            pending_prompt = st.session_state.pop("pending_chat_prompt", None)
            active_prompt = user_prompt or pending_prompt

            if active_prompt:
                st.session_state["chat_history"].append({"role": "user", "content": active_prompt})

                with st.spinner("Analyzing PBIP metadata & generating answer..."):
                    res = chatbot.ask(active_prompt, metadata, st.session_state["chat_history"])
                    answer = res.get("answer", "No response generated.")

                st.session_state["chat_history"].append({"role": "assistant", "content": answer})
                st.rerun()

