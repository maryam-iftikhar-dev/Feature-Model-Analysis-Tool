
import io
import re
import os
import streamlit as st
from parser import parse_xml, get_feature_tree_summary, FeatureModel
from logic import extract_simple_constraint, eval_expr, generate_clauses, format_clauses, normalize_expr, parse_english_constraint
from mwp import find_mwps, verify_configuration
from utils.ui import load_css
from codeanalysis import (
    analyze_feature_consistency,
    build_feature_impact,
    build_folder_summary,
    extract_code_dependencies,
    list_code_files,
    load_git_repository,
    suggest_feature_mapping,
    infer_feature_dependencies,
)

st.set_page_config(page_title="Feature Model Analyzer",layout="wide",initial_sidebar_state="expanded",)
load_css("styles/main.css")
# =======================================
# SESSION STATE 
# =======================================
def init_state():
    defaults = {
        "model": None,
        "clauses": [],
        "mwp_result": None,
        "selected_features": {},
        "bool_constraints": [],
        "constraint_translations": [],
        "verify_result": None,
        "custom_stage": "input",
        "custom_english": "",
        "custom_auto": "",
        "custom_explain": "",
        "live_auto_messages": [],
        "codebase_root": "",
        "codebase_git_url": "",
        "codebase_files": [],
        "codebase_loaded": False,
        "feature_to_files": {},
        "code_dependencies": [],
        "feature_dependencies": [],
        "consistency_issues": [],
        "impact_report": {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# =======================================
# SIDEBAR
# =======================================
with st.sidebar:
    st.markdown("## Feature Model Tool")
    st.markdown("---")
    st.markdown("**Upload XML Feature Model**")
    uploaded = st.file_uploader("Upload XML", type=["xml"], label_visibility="collapsed")

    if uploaded:
        try:
            st.session_state.model = parse_xml(uploaded)
            st.session_state.clauses = generate_clauses(st.session_state.model)
            st.session_state.mwp_result = None
            st.session_state.verify_result = None
            # Reset selection
            st.session_state.selected_features = {
                name: feat.mandatory
                for name, feat in st.session_state.model.features.items()
            }
            st.success(" Model loaded!")
        except Exception as e:
            st.error(f"Parse error: {e}")

    if st.session_state.model:
        st.markdown("---")
        st.markdown(f"**Root:** `{st.session_state.model.root}`")
        st.markdown(f"**Features:** {len(st.session_state.model.features)}")
        st.markdown(f"**Constraints:** {len(st.session_state.model.constraints)}")

    st.markdown("---")
    st.markdown("**Codebase Input**")
    st.markdown("Use a local project folder or a Git repository URL.")
    codebase_root = st.text_input("Local project folder", value=st.session_state.codebase_root, label_visibility="collapsed")
    st.session_state.codebase_root = codebase_root
    codebase_git = st.text_input("Git repo URL", value=st.session_state.get("codebase_git_url", ""), label_visibility="collapsed")
    st.session_state.codebase_git_url = codebase_git

    load_col1, load_col2 = st.columns(2)
    with load_col1:
        if st.button("Load local codebase"):
            if not codebase_root:
                st.error("Enter a local folder path.")
            elif not os.path.isdir(codebase_root):
                st.error("Local folder not found.")
            else:
                files = list_code_files(codebase_root)
                if not files:
                    st.error("No supported code files were detected in that folder.")
                else:
                    st.session_state.codebase_root = codebase_root
                    st.session_state.codebase_files = files
                    st.session_state.codebase_loaded = True
                    st.success(f"Loaded {len(files)} source files from local codebase.")
    with load_col2:
        if st.button("Clone and load repo"):
            if not codebase_git:
                st.error("Enter a Git repository URL.")
            else:
                temp_dir = os.path.join(os.getcwd(), "tmp_codebase")
                ok, msg = load_git_repository(codebase_git, temp_dir)
                if not ok:
                    st.error(msg)
                else:
                    files = list_code_files(temp_dir)
                    if not files:
                        st.error("Repository clone succeeded but no supported code files were found.")
                    else:
                        st.session_state.codebase_root = temp_dir
                        st.session_state.codebase_files = files
                        st.session_state.codebase_loaded = True
                        st.success(f"Cloned repo and loaded {len(files)} files.")

    if st.session_state.codebase_loaded:
        st.markdown("---")
        st.markdown(f"**Codebase root:** `{st.session_state.codebase_root}`")
        st.markdown(f"**Detected files:** {len(st.session_state.codebase_files)}")
        if st.session_state.codebase_files:
            st.markdown(f"`{st.session_state.codebase_files[0]}`")
            if len(st.session_state.codebase_files) > 1:
                st.markdown("...more files available.")

# =======================================
# MAIN CONTENT
# =======================================
st.markdown("# Feature Model Analysis Tool")
st.markdown("* XML Parsing · Logic Translation · MWP · Visualization*")
st.markdown("---")

if not st.session_state.model:
    st.markdown("""
    <div class="alert-info">
    Upload an XML feature model using the sidebar to get started.<br><br>
    The tool will automatically parse, translate to propositional logic,
    compute Minimum Working Products, and provide an interactive visualization.
    </div>
    """, unsafe_allow_html=True)
    st.stop()

model: FeatureModel = st.session_state.model

# =======================================
# TABS
# =======================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Parse & Summary",
    "Logic Translation",
    "MWP Identification",
    "Visualize & Verify",
    "Codebase Analysis",
])

# ========================
# TAB 1 — Parse & Summary
# =========================
with tab1:
    st.markdown("## Parsed Feature Model")
    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        st.markdown("### Feature Hierarchy")

        def render_tree(name, depth=0):
            feat = model.features.get(name)
            if not feat:
                return
            indent = "&nbsp;" * (depth * 6)

            mand_badge = '<span class="badge-mandatory">mandatory</span>' if feat.mandatory else '<span class="badge-optional">optional</span>'
            group_badge = ""
            if feat.group_type == "xor":
                group_badge = ' <span class="badge-xor">XOR</span>'
            elif feat.group_type == "or":
                group_badge = ' <span class="badge-or">OR</span>'

            icon = "[M]" if feat.mandatory else "[O]"
            st.markdown(
                f'<div class="feat-node">{indent}{icon} <b>{name}</b> {mand_badge}{group_badge}</div>',
                unsafe_allow_html=True
            )
            for child in feat.children:
                render_tree(child, depth + 1)

        render_tree(model.root)

    with col2:
        st.markdown("### Raw Summary")
        st.code(get_feature_tree_summary(model), language="text")

        st.markdown("### Cross-Tree Constraints")
        if not model.constraints:
            st.markdown('<div class="alert-info">No constraints defined in XML.</div>', unsafe_allow_html=True)
        else:
            for c in model.constraints:
                if c.english:
                    st.markdown(f'<div class="fm-card"><b>English:</b> {c.english}</div>', unsafe_allow_html=True)
                if c.boolean_expr:
                    st.markdown(f'<div class="fm-card"><b>Boolean:</b> <code>{c.boolean_expr}</code></div>', unsafe_allow_html=True)

        #  show any custom constraints added by the user
        custom_translations = st.session_state.get("constraint_translations", [])
        if custom_translations:
            st.markdown("#### Custom Constraints (Added by User)")
            for eng_label, expr_label in custom_translations:
                if expr_label and expr_label != "(skipped)":
                    if eng_label and eng_label != "(no English)":
                        st.markdown(f'<div class="fm-card"> <b>English:</b> {eng_label}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="fm-card"><b>Boolean:</b> <code>{expr_label}</code></div>', unsafe_allow_html=True)


# =======================================
# TAB 2 — Logic Translation
# =======================================
with tab2:
    st.markdown("## Propositional Logic Translation")
    st.markdown("""
    <div class="alert-info">
    <b>Translation Rules:</b><br>
    • <b>Root</b>: always <code>True</code><br>
    • <b>Mandatory child</b>: Parent → Child<br>
    • <b>Optional child</b>: Child → Parent (child requires parent)<br>
    • <b>OR group</b>: Parent → (A ∨ B ∨ …) and each member → Parent<br>
    • <b>XOR group</b>: Parent → exactly one combination + each member → Parent
    </div>
    """, unsafe_allow_html=True)
    st.caption("Mandatory children are shown with both Parent -> Child and Child -> Parent, matching the solver's CNF semantics.")
    st.markdown("### Generated Clauses")
    st.markdown(
        f'<div class="clause-box">{format_clauses(st.session_state.clauses)}</div>',
        unsafe_allow_html=True
    )
    st.markdown("---")
    st.markdown("### Cross-Tree Constraint Handling")
    st.markdown(
        "Constraints can be entered in **English** or directly as a **boolean expression**. "
        "English input will be auto-translated; you must confirm before it becomes active."
    )

    def normalize_bool_expr(expr: str) -> str:
        feat_lower = {f.lower(): f for f in model.features}
        expr = (
        expr.replace("<->", "↔")
        .replace("->", "→")
        .replace("&", "∧")
        .replace("|", "∨")
        .replace("!", "¬") )
        # Replace each word token with the correct feature name
        def fix_case(m):
            word = m.group(0)
            if word.lower() in ("or", "and", "not"):
                return word
            return feat_lower.get(word.lower(), word)

        return re.sub(r"[A-Za-z]\w*", fix_case, expr)

    def normalize_bool_expr(expr: str) -> str:
        feat_lower = {f.lower(): f for f in model.features}
        expr = normalize_expr(expr)

        def fix_case(m):
            word = m.group(0)
            if word.lower() in ("or", "and", "not", "implies", "requires", "iff"):
                return word
            return feat_lower.get(word.lower(), word)

        return re.sub(r"[A-Za-z]\w*", fix_case, expr)

    def validate_bool_expr(expr: str):
        if not expr.strip():
            return False, "Expression cannot be empty."

        normalized = normalize_bool_expr(expr)

        stack = []
        for ch in normalized:
            if ch == "(":
                stack.append(ch)
            elif ch == ")":
                if not stack:
                    return False, "Unbalanced parentheses."
                stack.pop()
        if stack:
            return False, "Unbalanced parentheses."

        try:
            eval_expr(normalized, set())
        except Exception as e:
            return False, str(e)

        return True, ""

   # =======================================
    # Section A: Constraints from XML
   # =======================================
    if model.constraints:
        st.markdown("#### From XML Model")
        for idx, c in enumerate(model.constraints):

                # Boolean already in XML — auto-add once
            if c.boolean_expr:
                key = f"xml_bool_{idx}"
                if key not in st.session_state:
                    st.session_state[key] = "confirmed"
                    normed = normalize_bool_expr(c.boolean_expr)
                    if normed not in st.session_state.bool_constraints:
                        st.session_state.bool_constraints.append(normed)
                label = c.english[:55] + "…" if c.english and len(c.english) > 55 else (c.english or c.boolean_expr)
                with st.expander(f"Constraint {idx+1}: {label}"):
                    if c.english:
                        st.markdown(f"**English:** {c.english}")
                    st.markdown(f"**Boolean:** `{c.boolean_expr}`")
                    st.markdown('<span style="color:#166534;font-weight:600;">Active — loaded directly from XML.</span>', unsafe_allow_html=True)
                continue

            # English only allowed
            if not c.english:
                continue

            status_key  = f"xml_status_{idx}"
            expr_key    = f"xml_expr_{idx}"
            if status_key not in st.session_state:
                st.session_state[status_key] = "pending"  
                st.session_state[expr_key]   = ""

            status = st.session_state[status_key]
            stored_expr = st.session_state[expr_key]
            label= c.english[:55] + "…" if len(c.english) > 55 else c.english

            with st.expander(f"Constraint {idx+1}: {label}", expanded=(status == "pending")):
                st.markdown(f"**English:** _{c.english}_")

                # Auto-translate with regex
                auto_expr, auto_explain = parse_english_constraint(c.english)

                if auto_expr and status == "pending":
                    st.markdown(f"**Auto-detected translation:** `{auto_expr}`")
                    st.markdown(f"*{auto_explain}*")
                    st.info("A translation was found. Please confirm or reject it.")
                    ca, cb, cc = st.columns(3)
                    with ca:
                        if st.button("Confirm & Use", key=f"xml_confirm_{idx}"):
                            st.session_state[status_key] = "confirmed"
                            normed = normalize_bool_expr(auto_expr)
                            st.session_state[expr_key]   = normed
                            if normed not in st.session_state.bool_constraints:
                                st.session_state.bool_constraints.append(normed)
                            st.rerun()
                    with cb:
                        if st.button("Reject", key=f"xml_reject_{idx}"):
                            st.session_state[status_key] = "rejected"
                            st.rerun()
                    with cc:
                        if st.button("Edit manually", key=f"xml_edit_{idx}"):
                            st.session_state[status_key] = "manual"
                            st.session_state[expr_key]   = auto_expr
                            st.rerun()

                elif status == "confirmed":
                    st.markdown(f"**Active expression:** `{stored_expr}`")
                    st.markdown('<span style="color:#166534;font-weight:600;">Confirmed and active.</span>', unsafe_allow_html=True)
                    if st.button("Undo", key=f"xml_undo_{idx}"):
                        if stored_expr in st.session_state.bool_constraints:
                            st.session_state.bool_constraints.remove(stored_expr)
                        st.session_state[status_key] = "pending"
                        st.session_state[expr_key]   = ""
                        st.rerun()

                elif status == "rejected":
                    st.markdown('<span style="color:#991b1b;"> Rejected — not applied to solver.</span>', unsafe_allow_html=True)
                    if st.button("Reconsider", key=f"xml_reconsider_{idx}"):
                        st.session_state[status_key] = "pending"
                        st.rerun()

                # Manual entry mode (no auto-translation OR user chose to edit)
                if status in ("manual",) or (not auto_expr and status == "pending"):
                    if not auto_expr:
                        st.warning(" Could not auto-translate this constraint.")
                    default_val = st.session_state[expr_key]
                    manual_inp = st.text_input("Enter boolean expression (leave empty to skip):",value=default_val,key=f"xml_manual_input_{idx}",placeholder="e.g.  ByLocation → Location", )
                    mc1, mc2 = st.columns(2)
                    with mc1:
                        if st.button(" + Add this expression", key=f"xml_add_manual_{idx}"):
                            if not manual_inp.strip():
                                st.warning(" Expression is empty. Enter a boolean expression or click Skip.")
                            else:
                                ok, err = validate_bool_expr(manual_inp.strip())
                                if not ok:
                                    st.error(f" X Invalid: {err}")
                                else:
                                    normed = normalize_bool_expr(manual_inp.strip())
                                    st.session_state[status_key] = "manual"
                                    st.session_state[expr_key]   = normed
                                    if normed not in st.session_state.bool_constraints:
                                        st.session_state.bool_constraints.append(normed)
                                    st.rerun()
                    with mc2:
                        if st.button("Skip (no translation)", key=f"xml_skip_{idx}"):
                            st.session_state[status_key] = "rejected"
                            st.rerun()

       # =======================================
        # Section B: Add Custom Constraint
       # =======================================
        st.markdown("---")
        st.markdown("#### Add Custom Constraint")
        st.markdown(
            "Enter an **English statement**, a **boolean expression**, or both. "
            "If you enter English, the tool will attempt to auto-translate it first."
        )

        # Sub-state for the custom constraint workflow
        if "custom_stage" not in st.session_state:
            st.session_state.custom_stage   = "input"   # input | confirm | done
            st.session_state.custom_english = ""
            st.session_state.custom_auto    = ""
            st.session_state.custom_explain = ""

        if st.session_state.custom_stage == "input":
            new_eng  = st.text_input("English statement (optional):",key="new_eng_constraint",placeholder='e.g. "Feature A requires Feature B"')
            new_bool = st.text_input("Boolean expression (optional if English provided):",key="new_bool_constraint",placeholder="e.g.  ByLocation → Location  or  ¬A ∨ ¬B")

            if st.button("+ Add Constraint", key="btn_add_custom"):
                eng  = new_eng.strip()
                bool_inp = new_bool.strip()

                # Validation: at least one field must be filled
                if not eng and not bool_inp:
                    st.error("X Please enter an English statement, a boolean expression, or both.")

                elif bool_inp and not eng:
                    # Boolean only
                    ok, err = validate_bool_expr(bool_inp)
                    if not ok:
                        st.error(f"X Invalid expression: {err}")
                    else:
                        normed = normalize_bool_expr(bool_inp)
                        if normed not in st.session_state.bool_constraints:
                            st.session_state.bool_constraints.append(normed)
                        st.session_state.constraint_translations.append(("(no English)", normed))
                        st.success(f"Added: `{normed}`")

                elif eng and bool_inp:
                    # Both provided — validate boolean and add directly
                    ok, err = validate_bool_expr(bool_inp)
                    if not ok:
                        st.error(f"X Invalid expression: {err}")
                    else:
                        normed = normalize_bool_expr(bool_inp)
                        if normed not in st.session_state.bool_constraints:
                            st.session_state.bool_constraints.append(normed)
                        st.session_state.constraint_translations.append((eng, normed))
                        st.success(f" Added: `{normed}`")

                elif eng and not bool_inp:
                    # English only — try auto-translate, then ask for confirmation
                    auto_expr, auto_explain = parse_english_constraint(eng)
                    st.session_state.custom_english = eng
                    st.session_state.custom_auto    = auto_expr or ""
                    st.session_state.custom_explain = auto_explain or ""
                    st.session_state.custom_stage   = "confirm"
                    st.rerun()

        elif st.session_state.custom_stage == "confirm":
            eng = st.session_state.custom_english
            auto_expr= st.session_state.custom_auto
            auto_explain= st.session_state.custom_explain

            st.markdown(f'<div class="fm-card"> <b>English:</b> {eng}</div>', unsafe_allow_html=True)

            if auto_expr:
                # Spec: translation exists → ask for confirmation
                st.markdown(f"**Auto-detected translation:** `{auto_expr}`")
                if auto_explain:
                    st.markdown(f"*{auto_explain}*")
                st.info("A translation was found. Please confirm, edit, or reject it.")

                ca, cb, cc = st.columns(3)
                with ca:
                    if st.button("Confirm & Use", key="custom_confirm"):
                        normed = normalize_bool_expr(auto_expr)
                        if normed not in st.session_state.bool_constraints:
                            st.session_state.bool_constraints.append(normed)
                        st.session_state.constraint_translations.append((eng, normed))
                        st.session_state.custom_stage = "input"
                        st.rerun()
                with cb:
                    if st.button("Reject", key="custom_reject"):
                        st.session_state.custom_stage = "input"
                        st.rerun()
                with cc:
                    if st.button("Edit manually", key="custom_edit"):
                        st.session_state.custom_stage = "manual_edit"
                        st.rerun()
            else:
                # Spec: no translation → prompt user to input one
                st.warning("Could not auto-translate. Please enter a boolean expression, or skip.")
                st.session_state.custom_stage = "manual_edit"
                st.rerun()

        elif st.session_state.custom_stage == "manual_edit":
            eng = st.session_state.custom_english
            st.markdown(f'<div class="fm-card"> <b>English:</b> {eng}</div>', unsafe_allow_html=True)
            st.warning("No auto-translation available. Enter the boolean expression manually.")

            manual_bool = st.text_input(
                "Boolean expression (leave empty to skip):",
                key="custom_manual_bool",
                placeholder="e.g.  ByLocation → Location",
                value=st.session_state.custom_auto,
            )
            mc1, mc2 = st.columns(2)
            with mc1:
                if st.button("+ Add", key="custom_manual_add"):
                    if not manual_bool.strip():
                        st.warning("Empty expression — constraint skipped.")
                        st.session_state.custom_stage = "input"
                        st.rerun()
                    else:
                        ok, err = validate_bool_expr(manual_bool.strip())
                        if not ok:
                            st.error(f"Invalid: {err}")
                        else:
                            normed = normalize_bool_expr(manual_bool.strip())
                            if normed not in st.session_state.bool_constraints:
                                st.session_state.bool_constraints.append(normed)
                            st.session_state.constraint_translations.append((eng, normed))
                            st.session_state.custom_stage = "input"
                            st.rerun()
            with mc2:
                if st.button("Skip", key="custom_skip"):
                    # can be left empty
                    st.session_state.constraint_translations.append((eng, "(skipped)"))
                    st.session_state.custom_stage = "input"
                    st.rerun()

        # =======================================
        # Section C: Active Boolean Constraints
        # =======================================
        st.markdown("---")
        if st.session_state.bool_constraints:
            st.markdown("#### Active Boolean Constraints")
            st.markdown(
                '<div class="alert-info" style="margin-bottom:0.8rem;">'
                ' These constraints are enforced in <b>MWP Identification</b> and <b>Visualize &amp; Verify</b>.'
                '</div>',
                unsafe_allow_html=True
            )

            # Build a reverse lookup: expr → english 
            expr_to_english = {}
            for eng_label, expr_label in st.session_state.constraint_translations:
                expr_to_english[expr_label] = eng_label
            # cover XML constraints
            for c in model.constraints:
                if c.boolean_expr:
                    expr_to_english[c.boolean_expr] = c.english or ""
                for idx2 in range(len(model.constraints)):
                    ek = f"xml_expr_{idx2}"
                    sk = f"xml_status_{idx2}"
                    if ek in st.session_state and st.session_state[ek]:
                        eng_src = model.constraints[idx2].english or ""
                        expr_to_english[st.session_state[ek]] = eng_src

            for i, bc in enumerate(st.session_state.bool_constraints):
                eng_src = expr_to_english.get(bc, "")
                cols = st.columns([7, 1])
                with cols[0]:
                    eng_line = f'<div style="font-size:0.78rem;color:#5a6a8a;margin-bottom:3px;"> {eng_src}</div>' if eng_src else ""
                    st.markdown(
                        f'<div class="fm-card" style="padding:0.8rem 1.2rem;">'
                        f'{eng_line}'
                        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.88rem;color:#1e3a6e;"> <code>{bc}</code></span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                with cols[1]:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("Delete", key=f"del_bc_{i}", help="Remove this constraint"):
                        st.session_state.bool_constraints.pop(i)
                        st.rerun()
        else:
            st.markdown(
                '<div class="alert-info">No active constraints yet. '
                'Add one above or confirm a constraint from the XML model.</div>',
                unsafe_allow_html=True
            )


# =======================================
# TAB 3 — MWP Identification
# =======================================
with tab3:
    st.markdown("## Minimum Working Products (MWP)")
    st.markdown("""
    <div class="alert-info">
    An MWP is the <b>smallest valid feature configuration</b> that satisfies all mandatory constraints 
    and cross-tree constraints, while minimising optional features.
    </div>
    """, unsafe_allow_html=True)

    if st.button("Compute MWPs", use_container_width=False):
        with st.spinner("Running SAT solver…"):
            st.session_state.mwp_result = find_mwps( model, extra_bool_constraints=st.session_state.bool_constraints)

    result = st.session_state.mwp_result

    if result:
        if result["error"]:
            st.markdown(f'<div class="alert-error"> {result["error"]}</div>', unsafe_allow_html=True)
        else:
            mwps = result["mwps"]
            all_valid = result["all_valid"]

            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("MWPs Found", len(mwps))
            with col_b:
                st.metric("Total Valid Configs", len(all_valid))

            st.markdown("---")
            st.markdown("### MWP Configurations")
            if not mwps:
                st.markdown('<div class="alert-error">No MWPs found — the model may be unsatisfiable.</div>', unsafe_allow_html=True)
            else:
                for i, mwp in enumerate(mwps):
                    chips = "".join(f'<span class="mwp-chip">{f}</span>' for f in mwp)
                    st.markdown(
                        f'<div class="mwp-block"><b>MWP {i+1}</b> ({len(mwp)} features)<br>{chips}</div>',
                        unsafe_allow_html=True
                    )

            with st.expander(f"Show all {len(all_valid)} valid configurations"):
                for i, sol in enumerate(all_valid):
                    st.markdown(f"**Config {i+1}:** `{', '.join(sol)}`")


# =======================================
# TAB 4 — Visualize & Verify
# =======================================
with tab4:
    st.markdown("## Feature Selection & Verification")

    sel = st.session_state.selected_features

    def feature_name(name):
        for existing in model.features:
            if existing.lower() == name.lower():
                return existing
        return name

    def select_with_dependencies(name):
        name = feature_name(name)
        feat = model.features.get(name)
        if not feat:
            return []

        changes = []
        if not sel.get(name, False):
            sel[name] = True
            changes.append(f"Selected '{name}'.")

        if feat.parent:
            changes.extend(select_with_dependencies(feat.parent))
            parent = model.features.get(feat.parent)
            if parent and parent.group_type == "xor" and name in parent.group_members:
                for sibling in parent.group_members:
                    if sibling != name and sel.get(sibling, False):
                        sel[sibling] = False
                        changes.append(f"Deselected '{sibling}' because '{name}' is in the same XOR group.")

        for child_name in feat.children:
            child = model.features.get(child_name)
            if child and child.mandatory and child_name not in feat.group_members:
                changes.extend(select_with_dependencies(child_name))

        return changes

    def deselect_with_descendants(name):
        name = feature_name(name)
        feat = model.features.get(name)
        if not feat or feat.mandatory:
            return []

        changes = []
        if sel.get(name, False):
            sel[name] = False
            changes.append(f"Deselected '{name}'.")

        for child_name in feat.children:
            changes.extend(deselect_with_descendants(child_name))
        for member in feat.group_members:
            changes.extend(deselect_with_descendants(member))

        return changes

    def apply_simple_cross_tree_constraints():
        changes = []
        warnings = []

        for expr in st.session_state.bool_constraints:
            kind, left_raw, right_raw = extract_simple_constraint(expr)
            if not kind:
                continue

            left = feature_name(left_raw)
            right = feature_name(right_raw)
            if left not in model.features or right not in model.features:
                warnings.append(f"Constraint '{expr}' refers to an unknown feature.")
                continue

            if kind == "requires" and sel.get(left, False) and not sel.get(right, False):
                changes.append(f"'{left}' requires '{right}'.")
                changes.extend(select_with_dependencies(right))

            if kind == "excludes" and sel.get(left, False) and sel.get(right, False):
                right_feat = model.features[right]
                left_feat = model.features[left]
                changes.append(f"'{left}' excludes '{right}'.")
                if not right_feat.mandatory:
                    changes.extend(deselect_with_descendants(right))
                elif not left_feat.mandatory:
                    changes.extend(deselect_with_descendants(left))
                else:
                    warnings.append(f"Cannot auto-enforce '{expr}' because both features are mandatory.")

        return changes, warnings

    def render_interactive(name, depth=0):
        feat = model.features.get(name)
        if not feat:
            return

        if depth == 0:
            content_cols = st.columns([1])
            content_col = content_cols[0]
        else:
            ratio = min(depth * 0.05, 0.5)
            spacer, content_col = st.columns([ratio, 1 - ratio])

        with content_col:
            if feat.mandatory:
                st.checkbox(
                    f"{name}  M",
                    value=True,
                    disabled=True,
                    key=f"feat_{name}",
                )
                sel[name] = True
            else:
                parent_selected = sel.get(feat.parent, True) if feat.parent else True
                checked = st.checkbox(
                    name,
                    value=sel.get(name, False),
                    disabled=not parent_selected, 
                    key=f"feat_{name}",
                )
                sel[name] = checked if parent_selected else False

                if not sel[name]:
                    def deselect_descendants(n):
                        f = model.features.get(n)
                        if not f:
                            return
                        for ch in f.children:
                            if not model.features[ch].mandatory:
                                sel[ch] = False
                                deselect_descendants(ch)
                        for gm in f.group_members:
                            sel[gm] = False
                            deselect_descendants(gm)
                    deselect_descendants(name)


            if feat.group_type and feat.group_members and sel.get(name, feat.mandatory):
                if feat.group_type == "xor":
                    options = feat.group_members
                    current_selected = [m for m in options if sel.get(m, False)]
                    current = current_selected[0] if current_selected else options[0]

                    r_ratio = min((depth + 1) * 0.05, 0.55)
                    r_spacer, r_col = st.columns([r_ratio, 1 - r_ratio])
                    with r_col:
                        chosen = st.radio(
                            f"Choose one  *(XOR)*",
                            options=options,
                            index=options.index(current) if current in options else 0,
                            horizontal=True,
                            key=f"xor_radio_{name}",
                        )
                    for m in options:
                        sel[m] = (m == chosen)

                elif feat.group_type == "or":
                    r_ratio = min((depth + 1) * 0.05, 0.55)
                    r_spacer, r_col = st.columns([r_ratio, 1 - r_ratio])
                    with r_col:
                        st.markdown(
                            '<span style="font-size:0.78rem;color:#f7c87e;font-family:\'JetBrains Mono\',monospace;">OR — select one or more:</span>',
                            unsafe_allow_html=True,
                        )
                        for m in feat.group_members:
                            val = st.checkbox(m, value=sel.get(m, False), key=f"or_cb_{name}_{m}", )
                            sel[m] = val

        non_group_children = [c for c in feat.children if c not in feat.group_members]
        for child in non_group_children:
            render_interactive(child, depth + 1)

        if feat.group_type and feat.group_members and sel.get(name, feat.mandatory):
            for m in feat.group_members:
                child_feat = model.features.get(m)
                if child_feat and child_feat.children:
                    # Only show a member's children when that member is selected
                    if sel.get(m, False):
                        render_interactive_children_only(m, depth + 2)

    def render_interactive_children_only(name, depth):
        feat = model.features.get(name)
        if not feat:
            return
        non_group_children = [c for c in feat.children if c not in feat.group_members]
        for child in non_group_children:
            render_interactive(child, depth)
        
        # Render the feature's own group if it has one
        if feat.group_type and feat.group_members and sel.get(name, False):
            if feat.group_type == "xor":
                options = feat.group_members
                current_selected = [m for m in options if sel.get(m, False)]
                current = current_selected[0] if current_selected else options[0]

                ratio = min(depth * 0.05, 0.5)
                spacer, content_col = st.columns([ratio, 1 - ratio])
                with content_col:
                    r_ratio = min((depth + 1) * 0.05, 0.55)
                    r_spacer, r_col = st.columns([r_ratio, 1 - r_ratio])
                    with r_col:
                        chosen = st.radio(
                            f"Choose one  *(XOR)*",
                            options=options,
                            index=options.index(current) if current in options else 0,
                            horizontal=True,
                            key=f"xor_radio_{name}_children_{depth}",
                        )
                    for m in options:
                        sel[m] = (m == chosen)

            elif feat.group_type == "or":
                ratio = min(depth * 0.05, 0.5)
                spacer, content_col = st.columns([ratio, 1 - ratio])
                with content_col:
                    r_ratio = min((depth + 1) * 0.05, 0.55)
                    r_spacer, r_col = st.columns([r_ratio, 1 - r_ratio])
                    with r_col:
                        st.markdown(
                            '<span style="font-size:0.78rem;color:#f7c87e;font-family:\'JetBrains Mono\',monospace;">OR — select one or more:</span>',
                            unsafe_allow_html=True,
                        )
                        for m in feat.group_members:
                            val = st.checkbox(m, value=sel.get(m, False), key=f"or_cb_{name}_children_{m}_{depth}")
                            sel[m] = val
            
            # Recursively render children of group members
            for m in feat.group_members:
                child_feat = model.features.get(m)
                if child_feat and child_feat.children and sel.get(m, False):
                    render_interactive_children_only(m, depth + 1)

    st.markdown("*M = mandatory (always on) · greyed = parent not selected*")
    st.markdown("---")

    render_interactive(model.root)

    if st.session_state.live_auto_messages:
        st.info("Live constraints adjusted the selection: " + " ".join(st.session_state.live_auto_messages))
        st.session_state.live_auto_messages = []

    auto_changes, auto_warnings = apply_simple_cross_tree_constraints()
    live_chosen = [name for name, v in sel.items() if v]
    live_result = verify_configuration(
        live_chosen,
        model,
        extra_bool_constraints=st.session_state.bool_constraints,
    )

    if auto_changes:
        unique_changes = []
        for msg in auto_changes:
            if msg not in unique_changes:
                unique_changes.append(msg)
        st.session_state.selected_features.update(sel)
        st.session_state.live_auto_messages = unique_changes
        st.rerun()

    if auto_warnings:
        for warning in auto_warnings:
            st.warning(warning)

    if st.session_state.bool_constraints:
        st.markdown("### Live Constraint Check")
        if live_result["valid"]:
            st.markdown(
                '<div class="alert-success"><b>Current selection is feasible.</b></div>',
                unsafe_allow_html=True,
            )
        else:
            live_reasons_html = "<br>".join(f"- {r}" for r in live_result["reasons"])
            st.markdown(
                f'<div class="alert-error"><b>Current selection needs attention.</b><br><br>'
                f'{live_reasons_html}</div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")

    col_verify, col_reset = st.columns([2, 1])
    with col_verify:
        if st.button("Verify Configuration", use_container_width=True):
            chosen = [name for name, v in sel.items() if v]
            result = verify_configuration(chosen,model,extra_bool_constraints=st.session_state.bool_constraints,)
            st.session_state.verify_result = (chosen, result)

    with col_reset:
        if st.button(" Reset Defaults", use_container_width=True):
            st.session_state.selected_features = {
                name: feat.mandatory
                for name, feat in model.features.items()
            }
            st.session_state.verify_result = None
            st.rerun()

    if st.session_state.verify_result:
        chosen, result = st.session_state.verify_result
        st.markdown("---")
        st.markdown("### Verification Result")
        if result["valid"]:
            st.markdown(
                f'<div class="alert-success"> <b>Valid Configuration!</b><br>'
                f'Selected features: {", ".join(sorted(chosen))}</div>',
                unsafe_allow_html=True
            )
        else:
            reasons_html = "<br>".join(f"• {r}" for r in result["reasons"])
            st.markdown(
                f'<div class="alert-error"> <b>Invalid Configuration</b><br><br>'
                f'{reasons_html}</div>',
                unsafe_allow_html=True
            )
with tab5:
    st.markdown("## Codebase Feature Mapping & Dependency Analysis")
    if not st.session_state.codebase_loaded:
        st.markdown(
            '<div class="alert-info">Load a local project folder or clone a Git repository from the sidebar first.</div>',
            unsafe_allow_html=True,
        )
        st.stop()

    root_path = st.session_state.codebase_root
    files = st.session_state.codebase_files
    st.markdown(f"**Codebase root:** `{root_path}`")
    st.markdown(f"**Detected source files:** {len(files)}")

    file_tree = build_folder_summary(root_path)
    st.markdown("### Folder structure")
    for path in file_tree:
        st.markdown(f"- `{path}`")

    st.markdown("### Feature-to-Code Mapping")
    features = list(st.session_state.model.features.keys())
    suggested = suggest_feature_mapping(features, files)

    for feature in features:
        default_files = st.session_state.feature_to_files.get(feature, suggested.get(feature, []))
        selection = st.multiselect(
            f"Map feature '{feature}' to implementation artifacts:",
            options=files,
            default=default_files,
            key=f"map_{feature}",
        )
        st.session_state.feature_to_files[feature] = selection

    mapped_features = [f for f, mapped in st.session_state.feature_to_files.items() if mapped]
    st.markdown(f"**Features mapped to code:** {len(mapped_features)}/{len(features)}")

    if len(mapped_features) < 5:
        st.warning("At least 5 features must be mapped to code artifacts to enable dependency inference.")

    st.markdown("---")
    st.markdown("### Extracted File Dependencies")
    code_deps = extract_code_dependencies(root_path, files)
    st.session_state.code_dependencies = code_deps

    if not code_deps:
        st.markdown('<div class="alert-error">No code dependencies were detected. Check the codebase or supported file types.</div>', unsafe_allow_html=True)
    else:
        for dep in code_deps[:10]:
            st.markdown(f"- `{dep['source']}` → `{dep['target']}` : _{dep['evidence']}_")
        if len(code_deps) > 10:
            st.markdown(f"- ...and {len(code_deps) - 10} more dependencies")

    if len(mapped_features) >= 5 and code_deps:
        st.markdown("---")
        st.markdown("### Inferred Feature-Level Dependencies")
        feature_deps = infer_feature_dependencies(st.session_state.feature_to_files, code_deps)
        st.session_state.feature_dependencies = feature_deps

        if not feature_deps:
            st.markdown('<div class="alert-info">No feature-to-feature dependencies could be inferred from the current mapping.</div>', unsafe_allow_html=True)
        else:
            for rel in feature_deps:
                st.markdown(
                    f"- `{rel['feature_source']}` depends on `{rel['feature_target']}` "
                    f"(via `{rel['source_file']}` → `{rel['target_file']}`; evidence: `{rel['evidence']}`)"
                )

        st.markdown("---")
        st.markdown("### Consistency Analysis")
        issues = analyze_feature_consistency(
            st.session_state.feature_to_files,
            feature_deps,
            st.session_state.model.constraints,
        )
        st.session_state.consistency_issues = issues

        if not issues:
            st.markdown('<div class="alert-success">No inconsistencies detected between feature model constraints and code-derived dependencies.</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div class="alert-error"><b>{len(issues)} inconsistency(s) detected.</b> Review the highlighted issues below.</div>',
                unsafe_allow_html=True,
            )
            for issue in issues:
                issue_class = issue['classification'].replace(' ', '-').lower()
                st.markdown(
                    f'<div class="issue-card issue-{issue_class}">'
                    f'<div class="issue-title">{issue["classification"].upper()}: {issue["feature_source"]} → {issue["feature_target"]}</div>'
                    f'<div class="issue-meta">{issue["reason"]}</div>'
                    f'<div class="issue-evidence">Evidence: {issue["evidence"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")
        st.markdown("### Impact Analysis")

        selected = [name for name, value in st.session_state.selected_features.items() if value]
        impact = build_feature_impact(selected, st.session_state.feature_to_files, code_deps)
        st.session_state.impact_report = impact

        st.markdown(f"**Selected features:** {', '.join(selected)}")
        st.markdown(f"**Direct files triggered:** {', '.join(impact['direct_files']) or 'None'}")
        st.markdown(f"**Indirect files triggered:** {', '.join(impact['indirect_files']) or 'None'}")

        if impact['triggered_dependencies']:
            st.markdown("#### Triggered code dependencies")
            for dep in impact['triggered_dependencies']:
                st.markdown(
                    f"- `{dep['source']}` → `{dep['target']}` : _{dep['evidence']}_"
                )