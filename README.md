# Power BI PBIP Analyzer

A Streamlit application for analyzing Power BI PBIP projects.

## What it does

- Reads PBIP/TMDL semantic model definitions.
- Reads PBIR report pages and visuals.
- Extracts tables, columns, calculated columns and measures.
- Maps semantic objects to report visuals.
- Classifies usage as Direct, Indirect or Unused.
- Builds DAX dependency and usage lineage information.
- Extracts data-source/Power Query metadata.
- Runs deterministic and optional AI-assisted DAX analysis.
- Includes a PBIP-grounded **Power BI AI Assistant (Chatbot)** for interactive multi-turn technical Q&A.
- Generates a compact Excel workbook with exactly 6 sheets:
  1. Summary
  2. Model Inventory
  3. Report Usage
  4. Relationships & Lineage
  5. Data Sources
  6. DAX Analysis

## Power BI AI Assistant (Chatbot)

The platform features an integrated **Power BI AI Assistant** that answers technical questions grounded directly in the analyzed PBIP project metadata:

- **Targeted Context Extraction**: The Context Builder extracts only the relevant measures, tables, relationships, sources, or DAX expressions matching the user's question without sending the entire model.
- **Strict Grounding & Anti-Hallucination**: The assistant answers using ONLY the supplied PBIP metadata. If an object is not present in the model, it explicitly states that it is not available rather than hallucinating.
- **Supported Question Types**:
  - *Model Inventory*: "Which tables are unused?", "What tables exist?"
  - *DAX Analysis*: "Explain [Total Revenue]", "Why is this measure complex?", "Suggest an optimization for [Sales YTD]"
  - *Visual Usage*: "Which visuals use [Total Revenue]?", "Is Sales[Amount] used in reports?"
  - *Relationships & Lineage*: "Which relationships use bidirectional filtering?", "Show active relationships"
  - *Data Sources*: "What data sources and Power Query M expressions are used?"
  - *Model Health*: "Why is my Model Health Score 85?"
  - *Executive Summary*: "Give me an executive summary of this model."
- **Grounding Limitation Notice**: The assistant answers questions using the analyzed PBIP metadata in read-only mode. It does not execute live DAX queries against Power BI Service or modify the PBIP project automatically.
- **Request Limits & Caching**: Supports up to 50 AI requests per analysis run with SHA-256 context caching to prevent duplicate API calls.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate         # macOS/Linux
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## AI configuration

AI is optional. Without credentials, static DAX analysis and deterministic model health evaluation continue to work seamlessly.
See `.env.example` for supported environment variables (e.g. `AI_PROVIDER=azure_openai`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini`).

## Input

Upload a ZIP containing the complete PBIP project folder. The ZIP should preserve the PBIP project file, `.Report` folder and `.SemanticModel` folder.

## Security & Privacy

Uploaded projects are processed in temporary storage and are not committed to the repository. API keys are loaded via environment variables and are never hard-coded, logged, or exposed in the Streamlit UI or Excel files. Power Query connection strings and secrets are sanitized before sending context to Azure OpenAI.
