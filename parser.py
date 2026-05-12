import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Feature:
    name: str
    mandatory: bool = True        
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    group_type: Optional[str] = None   # 'xor' | 'or' | None
    group_members: List[str] = field(default_factory=list)  # siblings in same group

@dataclass
class Constraint:
    english: Optional[str] = None
    boolean_expr: Optional[str] = None

@dataclass
class FeatureModel:
    features: dict             
    root: str
    constraints: List[Constraint] = field(default_factory=list)

def _parse_feature(elem, parent_name: str | None, features: dict, mandatory_override: bool | None = None):
    name = elem.attrib.get("name")
    if not name:
        return

    if parent_name is None:
        mandatory = True
    else:
        raw = elem.attrib.get("mandatory", "false").lower()
        mandatory = raw == "true"

    # Only apply override if the feature doesn't have an explicit mandatory attribute
    if mandatory_override is not None and "mandatory" not in elem.attrib:
        mandatory = mandatory_override

    feat = Feature(name=name, mandatory=mandatory, parent=parent_name)
    features[name] = feat

    if parent_name and parent_name in features:
        features[parent_name].children.append(name)

    # Parse children 
    for child in elem:
        if child.tag == "feature":
            _parse_feature(child, name, features)
        elif child.tag == "group":
            group_type = child.attrib.get("type", "or").lower()
            group_members = []
            for gchild in child:
                if gchild.tag == "feature":
                    gname = gchild.attrib.get("name")
                    if gname:
                        group_members.append(gname)
                        _parse_feature(gchild, name, features, mandatory_override=False)

            # Store group info on the parent feature
            feat.group_type = group_type
            feat.group_members = group_members


def parse_xml(xml_source) -> FeatureModel:
    if hasattr(xml_source, "read"):
        tree = ET.parse(xml_source)
    else:
        tree = ET.parse(xml_source)

    root_elem = tree.getroot()  # <featureModel>

    features = {}
    root_feature_name = None
    constraints = []

    for child in root_elem:
        if child.tag == "feature":
            #  root feature
            root_feature_name = child.attrib.get("name")
            _parse_feature(child, None, features)
        elif child.tag == "constraints":
            for c in child:
                if c.tag == "constraint":
                    eng = None
                    bool_expr = None
                    for sub in c:
                        if sub.tag == "englishStatement":
                            eng = sub.text.strip() if sub.text else None
                        elif sub.tag == "booleanExpression":
                            bool_expr = sub.text.strip() if sub.text else None
                    constraints.append(Constraint(english=eng, boolean_expr=bool_expr))

    if root_feature_name is None:
        raise ValueError("No root <feature> found inside <featureModel>.")

    return FeatureModel(features=features, root=root_feature_name, constraints=constraints)


def get_feature_tree_summary(model: FeatureModel) -> str:
    lines = []

    def walk(name, indent=0):
        f = model.features.get(name)
        if not f:
            return
        prefix = "  " * indent
        mand = "[mandatory]" if f.mandatory else "[optional]"
        group = f"  (group: {f.group_type.upper()})" if f.group_type else ""
        lines.append(f"{prefix}• {name} {mand}{group}")
        for ch in f.children:
            walk(ch, indent + 1)

    walk(model.root)

    if model.constraints:
        lines.append("\nConstraints:")
        for c in model.constraints:
            if c.english:
                lines.append(f"  [EN]   {c.english}")
            if c.boolean_expr:
                lines.append(f"  [BOOL] {c.boolean_expr}")

    return "\n".join(lines)
