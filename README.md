# Feature Model Analysis Tool

## User Guide

This repository contains a Streamlit-based tool for feature model analysis and feature-to-code dependency inspection.

### What the tool does

- Loads an XML feature model
- Parses feature hierarchy and cross-tree constraints
- Translates the model into propositional logic clauses
- Computes Minimum Working Products (MWPs)
- Allows interactive feature selection and validation
- Loads a codebase from a local folder or Git repository
- Maps features to implementation files/modules
- Extracts lightweight file dependencies
- Infers feature-level dependencies from code
- Compares code-derived dependencies with feature model constraints
- Highlights inconsistencies and impact of selected features

## Prerequisites

- Python 3.10+ installed
- `git` installed if you want to clone a repository

## Install dependencies

From the project root, run:

```bash
pip install -r requirements.txt
```

## Run the app

From the project root, run:

```bash
python -m streamlit run app.py
```

Then open the browser link provided by Streamlit.

## Using the tool

### 1. Load a feature model

- Use the sidebar to upload an XML feature model file.
- The model is parsed and displayed in the `Parse & Summary` tab.
- The sidebar also shows the root feature, number of features, and number of constraints.

### 2. Review the parsed feature model

In the `Parse & Summary` tab:

- View the feature hierarchy
- See raw textual summary of the tree
- Inspect cross-tree constraints from XML

### 3. View logic translation

In the `Logic Translation` tab:

- See the model translated into propositional logic clauses
- Review automatic constraint translations
- Add custom constraints in English or boolean form

### 4. Compute MWPs

In the `MWP Identification` tab:

- Click `Compute MWPs`
- The tool finds minimum valid configurations
- View each MWP and the list of all valid configurations

### 5. Verify selections

In the `Visualize & Verify` tab:

- Interactively select or deselect features
- The tool enforces mandatory/optional relationships and XOR/OR groups
- Auto-applies simple cross-tree constraints
- Verify current selection viability with the `Verify Configuration` button

### 6. Analyze codebase dependencies

In the `Codebase Analysis` tab:

- Load a local codebase folder or clone a Git repository using the sidebar controls
- Supported file types: `.py`, `.js`, `.ts`, `.java`, `.c`, `.cpp`, `.h`
- The tool displays the codebase folder structure and detected files

### 7. Map features to code artifacts

- For each feature, select one or more implementation files from the detected file list
- At least 5 features should be mapped to satisfy the analysis requirements

### 8. Inspect extracted dependencies

- The tool lists file-to-file dependencies found in the codebase
- Evidence is shown using import/include statements from the source files

### 9. Review inferred feature dependencies

- The tool computes feature-level relationships based on your feature-to-file mapping and file dependencies
- Shows which feature depends on which other feature and the code evidence

### 10. Consistency analysis and inconsistency detection

- The tool compares feature model constraints with code-derived feature dependencies
- It identifies:
  - `hidden dependency`
  - `missing constraint`
  - `incorrect constraint`
- Issues are highlighted and displayed as cards with evidence

### 11. Impact analysis

- The tool shows files triggered by selected features
- It also lists indirect file dependencies that are brought in by the selected code artifacts

## Sample inputs

- `sample_feature_model.xml`: example feature model with features like `Authentication`, `Checkout`, `Payment`, `Shipping`, `Promotions`.
- `sample_codebase/`: a small sample project with 12 files and dependency relationships.

## Notes

- The tool uses lightweight dependency extraction, not deep static analysis.
- If a feature constraint is only written in English and not automatically parsed, you may need to add the boolean constraint manually.
- The highlighted consistency issues help identify hidden code dependencies and mismatches between design and implementation.
