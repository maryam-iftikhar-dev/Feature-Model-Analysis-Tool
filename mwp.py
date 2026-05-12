from logic import eval_expr
from typing import List, Dict, Optional
from parser import FeatureModel
from logic import build_cnf, add_constraint_to_cnf

try:
    from pysat.solvers import Glucose3
    PYSAT_AVAILABLE = True
except ImportError:
    PYSAT_AVAILABLE = False

# =====================================
# HELPERS
# =====================================

def _solution_to_names(solution: List[int], var_map: dict) -> List[str]:
    inv = {v: k for k, v in var_map.items()}
    return sorted([inv[lit] for lit in solution if lit > 0 and lit in inv])

def _is_subset(a: List[str], b: List[str]) -> bool:
    return set(a).issubset(set(b))

# =====================================
# MAIN MWP FINDER
# =====================================
def find_mwps(
    model: FeatureModel,
    extra_bool_constraints: Optional[List[str]] = None,
    max_solutions: int = 50,
) -> Dict:
    if not PYSAT_AVAILABLE:
        return {
            "mwps": [],
            "all_valid": [],
            "error": "PySAT is not installed. Run: pip install python-sat"
        }

    var_map, cnf = build_cnf(model)

    # Add cross-tree constraints
    if extra_bool_constraints:
        for expr in extra_bool_constraints:
            add_constraint_to_cnf(expr, var_map, cnf)

    solver = Glucose3()
    for clause in cnf:
        solver.add_clause(clause)

    all_solutions = []
    count = 0

    while solver.solve() and count < max_solutions:
        model_sol = solver.get_model()
        positive = [lit for lit in model_sol if lit > 0]
        all_solutions.append(_solution_to_names(positive, var_map))

        blocking_clause = [-lit for lit in model_sol]
        solver.add_clause(blocking_clause)
        count += 1

    solver.delete()

    #  configurations with no proper subset that is also valid
    mwps = []
    valid_sets = [set(s) for s in all_solutions]

    for i, sol in enumerate(all_solutions):
        sol_set = set(sol)
        is_minimal = True
        for j, other_set in enumerate(valid_sets):
            if i != j and other_set.issubset(sol_set) and other_set != sol_set:
                is_minimal = False
                break
        if is_minimal:
            mwps.append(sol)

    return {
        "mwps": mwps,
        "all_valid": all_solutions,
        "error": None
    }

# =====================================
# SINGLE CONFIGURATION VALIDATOR
# =====================================
def verify_configuration(selected: List[str],model: FeatureModel,extra_bool_constraints: Optional[List[str]] = None,
) -> Dict:

    reasons = []
    features = model.features

    # 1. Root must be selected
    if model.root not in selected:
        reasons.append(f"Root feature '{model.root}' must always be selected.")

    selected_set = set(selected)

    for name in selected:
        feat = features.get(name)
        if not feat:
            continue

        # 2. If a feature is selected, its parent must be selected
        if feat.parent and feat.parent not in selected_set:
            reasons.append(
                f"'{name}' is selected but its parent '{feat.parent}' is not."
            )

        # 3. Mandatory children must be selected if parent is selected
        for child_name in feat.children:
            child = features.get(child_name)
            if child and child.mandatory and child_name not in selected_set:
                if child_name not in feat.group_members:
                    reasons.append(
                        f"Mandatory child '{child_name}' of '{name}' is not selected."
                    )

        # 4. Group constraints
        if feat.group_type and feat.group_members:
            group_selected = [m for m in feat.group_members if m in selected_set]

            if feat.group_type == "or":
                if len(group_selected) == 0:
                    reasons.append(
                        f"OR group under '{name}': at least one of "
                        f"{feat.group_members} must be selected."
                    )

            elif feat.group_type == "xor":
                if len(group_selected) == 0:
                    reasons.append(
                        f"XOR group under '{name}': exactly one of "
                        f"{feat.group_members} must be selected."
                    )
                elif len(group_selected) > 1:
                    reasons.append(
                        f"XOR group under '{name}': only one may be selected, "
                        f"but got {group_selected}."
                    )
                    
    # 5. Cross-tree constraints (boolean expressions)
    if extra_bool_constraints:
        for expr in extra_bool_constraints:
            ok, msg = _check_bool_expr(expr, selected_set, features)
            if not ok:
                reasons.append(f"Cross-tree constraint violated: {expr}  — {msg}")

    return {"valid": len(reasons) == 0, "reasons": reasons}

def _check_bool_expr(expr: str, selected: set, features: dict):
    selected_lower = {s.lower() for s in selected}

    if eval_expr(expr, selected_lower):
        return True, ""

    return False, "Expression evaluates to False."