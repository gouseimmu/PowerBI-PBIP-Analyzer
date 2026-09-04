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
- Generates a compact Excel workbook with exactly 6 sheets:
  1. Summary
  2. Model Inventory
  3. Report Usage
  4. Relationships & Lineage
  5. Data Sources
  6. DAX Analysis

## Run locally

```bash
python -m venv .venv
.venv\\Scripts\\activate        # Windows
source .venv/bin/activate         # macOS/Linux
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## AI configuration

AI is optional. Without credentials, static DAX analysis continues to work.
See `.env.example` for supported environment variables.

## Input

Upload a ZIP containing the complete PBIP project folder. The ZIP should preserve the PBIP project file, `.Report` folder and `.SemanticModel` folder.

## Security

Uploaded projects are processed in temporary storage and are not committed to the repository. API keys should be supplied through environment variables or Streamlit secrets, never hard-coded.
