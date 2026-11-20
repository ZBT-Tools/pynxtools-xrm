"""Upload-scoped associations shared by the binary parser and YAML adapter."""

from pathlib import Path

import yaml

from pynxtools_xrm.errors import AmbiguousMetadataAssociation


def safe_raw_path(root, relative, *, directory=False):
    root = Path(root).resolve()
    if Path(relative).is_absolute():
        raise ValueError("NOMAD inputs must be upload-relative")
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path escapes NOMAD upload: {relative}")
    if directory and not path.is_dir():
        raise NotADirectoryError(path)
    if not directory and not path.is_file():
        raise FileNotFoundError(path)
    return path


def output_relative(source, root):
    relative = source.resolve().relative_to(Path(root).resolve())
    return (Path("_nexus") / relative.parent / (relative.name + ".nxs")).as_posix()


def find_config(source, root):
    matches = []
    for path in Path(root).rglob("*.archive.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        section = data.get("data", {})
        if not isinstance(section, dict) or not str(section.get("m_def", "")).endswith(
            "XRMDataConverter"
        ):
            continue
        relative = section.get("input_file")
        if relative and safe_raw_path(root, relative) == source:
            matches.append(section)
    if len(matches) > 1:
        raise AmbiguousMetadataAssociation(
            "Multiple YAML jobs refer to the same binary input"
        )
    return matches[0] if matches else {}
