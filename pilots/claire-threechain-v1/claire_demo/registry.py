"""Offline platform source registry. Source hashes are checked before decoding.

Official published addresses and layouts establish attribution candidates. They
do not by themselves establish historical proxy implementations or upgrade
boundaries; those remain null until independent chain evidence is available.
"""
from pathlib import Path
import ast
import hashlib
import json
import re


def load(root):
    root = Path(root)
    source_path = root / "sources/manifest.json"
    if source_path.exists():
        for item in json.loads(source_path.read_text()):
            p = root / item["path"]
            if hashlib.sha256(p.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError(f"Official source hash mismatch: {p}")
    path = root / "config/platform_registry.json"
    return json.loads(path.read_text()) if path.exists() else []


def abi_from_typescript(path):
    """Parse literal ABI arrays without evaluating JavaScript or source code."""
    text = Path(path).read_text()
    begin = text.index("[", text.index("export const"))
    end = text.rindex("]") + 1
    literal = text[begin:end]
    literal = re.sub(r"//[^\n]*", "", literal)
    literal = re.sub(r"([,{]\s*)([A-Za-z_$][\w$]*)(\s*:)", r"\1'\2'\3", literal)
    literal = re.sub(r"\btrue\b", "True", literal)
    literal = re.sub(r"\bfalse\b", "False", literal)
    literal = re.sub(r"\bnull\b", "None", literal)
    return ast.literal_eval(literal)


def read_layout(root, entry):
    path = Path(root) / entry["layout_path"]
    return abi_from_typescript(path) if path.suffix == ".ts" else json.loads(path.read_text())


def source_status(entry):
    return entry.get("verification_status", "unknown")
