import re
from itertools import product
from typing import List, Tuple

from parser import Feature, FeatureModel


# ================================
# 1. CLAUSE GENERATION
# ================================
def generate_clauses(model: FeatureModel) -> List[str]:
    clauses = []
    features = model.features

    clauses.append(f"{model.root}  [Root - always true]")

    def walk(name):
        feat: Feature = features.get(name)
        if not feat:
            return

        for child_name in feat.children:
            child: Feature = features.get(child_name)
            if not child:
                continue

            if child_name in feat.group_members:
                continue

            if child.mandatory:
                clauses.append(f"{name} -> {child_name}  [Mandatory child: parent requires child]")
                clauses.append(f"{child_name} -> {name}  [Mandatory child: child requires parent]")
            else:
                clauses.append(f"{child_name} -> {name}  [Optional child: child requires parent]")

            walk(child_name)

        if feat.group_type and feat.group_members:
            members = feat.group_members
            members_str = " | ".join(members)

            if feat.group_type == "or":
                clauses.append(f"{name} -> ({members_str})  [OR group: at least one]")
                for member in members:
                    clauses.append(f"{member} -> {name}  [OR member implies parent]")

            elif feat.group_type == "xor":
                combinations = []
                for i, _ in enumerate(members):
                    parts = []
                    for j, member in enumerate(members):
                        parts.append(member if i == j else f"!{member}")
                    combinations.append("(" + " & ".join(parts) + ")")
                xor_formula = " | ".join(combinations)
                clauses.append(f"{name} -> ({xor_formula})  [XOR group: exactly one]")
                for member in members:
                    clauses.append(f"{member} -> {name}  [XOR member implies parent]")

            for member in members:
                walk(member)

    walk(model.root)

    for constraint in model.constraints:
        if constraint.boolean_expr:
            clauses.append(f"{normalize_expr(constraint.boolean_expr)}  [Cross-tree constraint]")

    return clauses


def format_clauses(clauses: List[str]) -> str:
    return "\n".join(f"  {i + 1}. {clause}" for i, clause in enumerate(clauses))


def generate_structured_clauses(model: FeatureModel) -> str:
    features = model.features

    root_section = [model.root]
    child_parent = []
    parent_mandatory = []
    group_section = []
    constraints_section = []

    def walk(name):
        feat = features.get(name)
        if not feat:
            return

        for child_name in feat.children:
            child = features.get(child_name)
            if not child:
                continue

            if child_name in feat.group_members:
                continue

            child_parent.append(f"({child_name} -> {name})")

            if child.mandatory:
                parent_mandatory.append(f"({name} -> {child_name})")

            walk(child_name)

        if feat.group_type and feat.group_members:
            members = feat.group_members

            for member in members:
                child_parent.append(f"({member} -> {name})")

            if feat.group_type == "or":
                members_str = " | ".join(members)
                group_section.append(f"({name} -> ({members_str}))")

            elif feat.group_type == "xor":
                xor_parts = []
                for i, _ in enumerate(members):
                    parts = []
                    for j, member in enumerate(members):
                        parts.append(member if i == j else f"!{member}")
                    xor_parts.append("(" + " & ".join(parts) + ")")
                group_section.append(f"({name} -> ({' | '.join(xor_parts)}))")

            for member in members:
                walk(member)

    walk(model.root)

    for constraint in model.constraints:
        if constraint.boolean_expr:
            constraints_section.append(f"({normalize_expr(constraint.boolean_expr)})")

    output = []
    output.append("ROOT:")
    output.extend(root_section)
    output.append("\nCHILD REQUIRES PARENT:")
    output.extend(child_parent)
    output.append("\nPARENT REQUIRES MANDATORY CHILDREN:")
    output.extend(parent_mandatory)
    output.append("\nCHILDREN OF NODES (GROUP RELATIONS):")
    output.extend(group_section)
    output.append("\nEXPLICIT CONSTRAINTS:")
    output.extend(constraints_section if constraints_section else ["None"])

    return "\n".join(output)


# ========================================
# 2. PYSAT CNF BUILDER
# ========================================
def build_cnf(model: FeatureModel):
    features = model.features

    var_map = {}
    for i, name in enumerate(features.keys(), start=1):
        var_map[name] = i

    def v(name):
        return var_map[name]

    cnf = [[v(model.root)]]

    def walk(name):
        feat: Feature = features.get(name)
        if not feat:
            return

        for child_name in feat.children:
            child: Feature = features.get(child_name)
            if not child:
                continue
            if child_name in feat.group_members:
                continue

            if child.mandatory:
                cnf.append([-v(name), v(child_name)])
            cnf.append([-v(child_name), v(name)])

            walk(child_name)

        if feat.group_type and feat.group_members:
            members = feat.group_members
            member_vars = [v(member) for member in members]

            if feat.group_type in ("or", "xor"):
                cnf.append([-v(name)] + member_vars)

            if feat.group_type == "xor":
                for i in range(len(members)):
                    for j in range(i + 1, len(members)):
                        cnf.append([-member_vars[i], -member_vars[j]])

            for member in members:
                cnf.append([-v(member), v(name)])

            for member in members:
                walk(member)

    walk(model.root)

    return var_map, cnf


# ====================================
# 3. CROSS-TREE CONSTRAINT PARSING
# ====================================
_REQUIRES_PATTERN = re.compile(
    r"(?:the\s+)?(\w+)\s+(?:feature\s+)?(?:requires?|needs?|implies?)\s+(?:the\s+)?(\w+)",
    re.IGNORECASE,
)
_EXCLUDES_PATTERN = re.compile(
    r"(?:the\s+)?(\w+)\s+(?:feature\s+)?(?:excludes?|conflicts?\s+with|cannot\s+coexist\s+with)\s+(?:the\s+)?(\w+)",
    re.IGNORECASE,
)


def parse_english_constraint(text: str) -> Tuple[str | None, str | None]:
    match = _REQUIRES_PATTERN.search(text)
    if match:
        left, right = match.group(1), match.group(2)
        return f"{left} -> {right}", f"If {left} is selected then {right} must also be selected."

    match = _EXCLUDES_PATTERN.search(text)
    if match:
        left, right = match.group(1), match.group(2)
        return f"!{left} | !{right}", f"{left} and {right} cannot both be selected."

    return None, None


def extract_simple_constraint(expr: str) -> Tuple[str | None, str | None, str | None]:
    """Return ('requires'|'excludes', left, right) for simple UI-enforceable constraints."""
    normalized = normalize_expr(expr)
    name = r"[A-Za-z]\w*"

    match = re.fullmatch(rf"\s*({name})\s*->\s*({name})\s*", normalized)
    if match:
        return "requires", match.group(1), match.group(2)

    patterns = [
        rf"\s*!\s*({name})\s*\|\s*!\s*({name})\s*",
        rf"\s*!\s*\(\s*({name})\s*&\s*({name})\s*\)\s*",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, normalized)
        if match:
            return "excludes", match.group(1), match.group(2)

    return None, None, None


def add_constraint_to_cnf(bool_expr: str, var_map: dict, cnf: list) -> bool:
    bool_expr = normalize_expr(bool_expr)
    vars_ = list(var_map.keys())

    for assignment in product([False, True], repeat=len(vars_)):
        selected = {vars_[i].lower() for i, value in enumerate(assignment) if value}

        if not eval_expr(bool_expr, selected):
            clause = []
            for i, value in enumerate(assignment):
                var_id = var_map[vars_[i]]
                clause.append(-var_id if value else var_id)
            cnf.append(clause)

    return True


# =====================================
# 4. GENERAL BOOLEAN EXPRESSION SUPPORT
# =====================================
def normalize_expr(expr: str) -> str:
    expr = expr.strip()

    replacements = {
        "â†’": "->",
        "→": "->",
        "â‡’": "->",
        "⇒": "->",
        "â†”": "<->",
        "↔": "<->",
        "â‡”": "<->",
        "⇔": "<->",
        "âˆ§": "&",
        "∧": "&",
        "âˆ¨": "|",
        "∨": "|",
        "Â¬": "!",
        "¬": "!",
        "~": "!",
    }
    for old, new in replacements.items():
        expr = expr.replace(old, new)

    expr = re.sub(r"\bimplies\b", "->", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\brequires\b", "->", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\biff\b", "<->", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\band\b", "&", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bor\b", "|", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bnot\b", "!", expr, flags=re.IGNORECASE)

    return re.sub(r"\s+", " ", expr).strip()


def eval_expr(expr: str, selected: set) -> bool:
    parser = _BoolParser(_tokenize_expr(normalize_expr(expr)), selected)
    value = parser.parse()
    if parser.peek() is not None:
        raise ValueError(f"Unexpected token: {parser.peek()}")
    return value


def _tokenize_expr(expr: str) -> List[str]:
    token_re = re.compile(r"\s*(<->|->|[()!&|]|[A-Za-z]\w*)")
    tokens = []
    pos = 0

    while pos < len(expr):
        match = token_re.match(expr, pos)
        if not match:
            raise ValueError(f"Invalid token near: {expr[pos:]}")
        tokens.append(match.group(1))
        pos = match.end()

    return tokens


class _BoolParser:
    def __init__(self, tokens: List[str], selected: set):
        self.tokens = tokens
        self.selected = {item.lower() for item in selected}
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consume(self, expected=None):
        token = self.peek()
        if token is None:
            raise ValueError("Unexpected end of expression.")
        if expected is not None and token != expected:
            raise ValueError(f"Expected '{expected}', got '{token}'.")
        self.pos += 1
        return token

    def parse(self) -> bool:
        return self.parse_iff()

    def parse_iff(self) -> bool:
        left = self.parse_implies()
        while self.peek() == "<->":
            self.consume("<->")
            right = self.parse_implies()
            left = left == right
        return left

    def parse_implies(self) -> bool:
        left = self.parse_or()
        if self.peek() == "->":
            self.consume("->")
            right = self.parse_implies()
            return (not left) or right
        return left

    def parse_or(self) -> bool:
        left = self.parse_and()
        while self.peek() == "|":
            self.consume("|")
            right = self.parse_and()
            left = left or right
        return left

    def parse_and(self) -> bool:
        left = self.parse_not()
        while self.peek() == "&":
            self.consume("&")
            right = self.parse_not()
            left = left and right
        return left

    def parse_not(self) -> bool:
        if self.peek() == "!":
            self.consume("!")
            return not self.parse_not()
        return self.parse_atom()

    def parse_atom(self) -> bool:
        token = self.peek()
        if token == "(":
            self.consume("(")
            value = self.parse_iff()
            self.consume(")")
            return value

        if token and re.fullmatch(r"[A-Za-z]\w*", token):
            self.consume()
            return token.lower() in self.selected

        raise ValueError(f"Expected feature name or '(' but got '{token}'.")
