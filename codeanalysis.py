import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

KNOWN_EXTS = {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h"}


def list_code_files(root_dir: str) -> List[str]:
    root = Path(root_dir)
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in KNOWN_EXTS:
            if any(part in {"__pycache__", ".git"} for part in path.parts):
                continue
            rel = path.relative_to(root).as_posix()
            files.append(rel)
    return files


def build_folder_summary(root_dir: str, max_depth: int = 4) -> List[str]:
    root = Path(root_dir)
    summary = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if path.suffix.lower() not in KNOWN_EXTS:
            continue
        if any(part in {"__pycache__", ".git"} for part in path.parts):
            continue
        depth = len(path.relative_to(root).parts) - 1
        if depth >= max_depth:
            continue
        summary.append(path.relative_to(root).as_posix())
    return summary


def load_git_repository(git_url: str, target_dir: str) -> Tuple[bool, str]:
    target = Path(target_dir)
    if target.exists() and any(target.iterdir()):
        return False, f"Target folder '{target_dir}' is not empty."
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", git_url, target_dir],
            capture_output=True,
            text=True,
            check=True,
        )
        return True, "Repository cloned successfully."
    except FileNotFoundError:
        return False, "Git is not available in this environment."
    except subprocess.CalledProcessError as exc:
        return False, f"Git clone failed: {exc.stderr.strip() or exc.stdout.strip()}"


def _python_import_targets(import_name: str, current_rel: str, files: List[str]) -> List[str]:
    if import_name.startswith("."):
        parts = import_name.split(".")
        base = Path(current_rel).parent
        while parts and parts[0] == "":
            parts.pop(0)
        for part in parts:
            base = base / part
        candidates = [base.with_suffix(ext).as_posix() for ext in [".py"]]
        return [candidate for candidate in candidates if candidate in files]

    name = import_name.split(".")[0]
    candidates = []
    for f in files:
        stem = Path(f).stem
        if stem == name:
            candidates.append(f)
    return candidates


def _js_import_targets(import_path: str, current_rel: str, files: List[str]) -> List[str]:
    if import_path.startswith("."):
        base = Path(current_rel).parent / import_path
        candidates = []
        for ext in [".js", ".ts"]:
            candidate = (base.with_suffix(ext)).as_posix()
            if candidate in files:
                candidates.append(candidate)
            index_candidate = (base / "index").with_suffix(ext).as_posix()
            if index_candidate in files:
                candidates.append(index_candidate)
        return candidates

    name = Path(import_path).stem
    return [f for f in files if Path(f).stem == name]


def _line_from_match(text: str, match: re.Match) -> str:
    start = text.rfind("\n", 0, match.start())
    end = text.find("\n", match.end())
    if start == -1:
        start = 0
    else:
        start += 1
    if end == -1:
        end = len(text)
    return text[start:end].strip()


def extract_code_dependencies(root_dir: str, files: List[str]) -> List[Dict[str, str]]:
    dependencies = []
    for rel_path in files:
        full_path = Path(root_dir) / rel_path
        try:
            text = full_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        ext = full_path.suffix.lower()
        if ext == ".py":
            pattern = re.compile(r"^\s*(?:from\s+([.\w]+)\s+import|import\s+([\w.]+))", re.MULTILINE)
            for match in pattern.finditer(text):
                module = match.group(1) or match.group(2)
                if not module:
                    continue
                targets = _python_import_targets(module, rel_path, files)
                for target in targets:
                    line = _line_from_match(text, match)
                    dependencies.append({
                        "source": rel_path,
                        "target": target,
                        "evidence": line,
                        "type": "import",
                    })

        elif ext in {".js", ".ts"}:
            patterns = [
                re.compile(r"^\s*import\s+.*?from\s+[\"'](.+?)[\"']", re.MULTILINE),
                re.compile(r"require\([\"'](.+?)[\"']\)", re.MULTILINE),
            ]
            for pattern in patterns:
                for match in pattern.finditer(text):
                    module = match.group(1)
                    targets = _js_import_targets(module, rel_path, files)
                    for target in targets:
                        line = _line_from_match(text, match)
                        dependencies.append({
                            "source": rel_path,
                            "target": target,
                            "evidence": line,
                            "type": "import",
                        })

        elif ext in {".java", ".c", ".cpp", ".h"}:
            pattern = re.compile(r"^\s*(?:import|#include)\s+[<\"]?([\w./-]+)[>\"]?", re.MULTILINE)
            for match in pattern.finditer(text):
                module = match.group(1)
                candidates = [f for f in files if Path(f).stem == Path(module).stem]
                for target in candidates:
                    line = _line_from_match(text, match)
                    dependencies.append({
                        "source": rel_path,
                        "target": target,
                        "evidence": line,
                        "type": "include",
                    })

    unique = []
    seen = set()
    for dep in dependencies:
        key = (dep["source"], dep["target"], dep["evidence"])
        if key not in seen and dep["source"] != dep["target"]:
            seen.add(key)
            unique.append(dep)
    return unique


def infer_feature_dependencies(feature_to_files: Dict[str, List[str]], file_dependencies: List[Dict[str, str]]) -> List[Dict[str, object]]:
    file_to_feature = {}
    for feature, files in feature_to_files.items():
        for path in files:
            file_to_feature.setdefault(path, []).append(feature)

    feature_rels = []
    seen = set()
    for dep in file_dependencies:
        source_feats = file_to_feature.get(dep["source"], [])
        target_feats = file_to_feature.get(dep["target"], [])
        for sf in source_feats:
            for tf in target_feats:
                if sf == tf:
                    continue
                key = (sf, tf, dep["source"], dep["target"])
                if key in seen:
                    continue
                seen.add(key)
                feature_rels.append({
                    "feature_source": sf,
                    "feature_target": tf,
                    "source_file": dep["source"],
                    "target_file": dep["target"],
                    "evidence": dep["evidence"],
                })
    return feature_rels


def parse_constraints(constraints: List[object]) -> List[Dict[str, str]]:
    parsed = []
    for constraint in constraints:
        expr = constraint.boolean_expr or ""
        if "->" in expr:
            parts = expr.split("->")
            if len(parts) == 2:
                left = parts[0].strip().strip("() ")
                right = parts[1].strip().strip("() ")
                parsed.append({"type": "requires", "source": left, "target": right, "expr": expr})
        elif "!" in expr and "|" in expr:
            parts = [p.strip().strip("! ()") for p in expr.split("|")]
            if len(parts) == 2:
                parsed.append({"type": "excludes", "source": parts[0], "target": parts[1], "expr": expr})
    return parsed


def analyze_feature_consistency(
    feature_to_files: Dict[str, List[str]],
    inferred_deps: List[Dict[str, object]],
    model_constraints: List[object],
) -> List[Dict[str, str]]:
    constraint_edges = []
    for c in parse_constraints(model_constraints):
        constraint_edges.append((c["source"], c["target"], c["type"]))

    evidence = []
    seen = set()
    for dep in inferred_deps:
        source = dep["feature_source"]
        target = dep["feature_target"]
        if (source, target, "requires") not in constraint_edges and (source, target, "excludes") not in constraint_edges:
            key = (source, target, "hidden")
            if key not in seen:
                seen.add(key)
                evidence.append({
                    "classification": "hidden dependency",
                    "feature_source": source,
                    "feature_target": target,
                    "reason": f"Code file '{dep['source_file']}' depends on '{dep['target_file']}' while no feature-level constraint exists.",
                    "evidence": dep["evidence"],
                })

    for c in parse_constraints(model_constraints):
        source = c["source"]
        target = c["target"]
        supported = any(
            dep["feature_source"] == source and dep["feature_target"] == target
            for dep in inferred_deps
        )
        if not supported:
            classification = "incorrect constraint" if c["type"] == "requires" else "missing constraint"
            key = (source, target, classification)
            if key not in seen:
                seen.add(key)
                evidence.append({
                    "classification": classification,
                    "feature_source": source,
                    "feature_target": target,
                    "reason": f"Model constraint '{c['expr']}' is not reflected by the current code mapping and dependencies.",
                    "evidence": c["expr"],
                })
    return evidence


def build_feature_impact(
    selected_features: List[str],
    feature_to_files: Dict[str, List[str]],
    file_dependencies: List[Dict[str, str]],
) -> Dict[str, object]:
    direct_files = set()
    for feature in selected_features:
        direct_files.update(feature_to_files.get(feature, []))

    indirect_files = set()
    edges = []
    changed = True
    while changed:
        changed = False
        for dep in file_dependencies:
            if dep["source"] in direct_files.union(indirect_files):
                if dep["target"] not in direct_files and dep["target"] not in indirect_files:
                    indirect_files.add(dep["target"])
                    edges.append(dep)
                    changed = True
    return {
        "selected_features": selected_features,
        "direct_files": sorted(direct_files),
        "indirect_files": sorted(indirect_files - direct_files),
        "triggered_dependencies": edges,
    }


def suggest_feature_mapping(features: List[str], files: List[str]) -> Dict[str, List[str]]:
    suggestions = {}
    normalized_files = [f.lower() for f in files]
    for feature in features:
        feature_name = feature.lower()
        matched = [files[idx] for idx, f in enumerate(normalized_files) if feature_name in f or any(token in f for token in re.split(r"\W+", feature_name) if token)]
        suggestions[feature] = matched[:3]
    return suggestions
