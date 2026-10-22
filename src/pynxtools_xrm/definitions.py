"""Prepare an explicit shared NXDL overlay; do not patch installed pynxtools."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import pynxtools


def prepare_definitions(destination):
    source = Path(pynxtools.__file__).parent / "definitions"
    destination = Path(destination).resolve()
    if destination == source.resolve() or source.resolve() in destination.parents:
        raise ValueError("Definition overlay must be outside installed pynxtools")
    revision = (source.parent / "nexus-version.txt").read_text().strip()
    marker = destination / "xrm-overlay.json"
    if destination.exists() and not marker.exists():
        raise ValueError("Refusing to overwrite an unrecognized definitions directory")
    if marker.exists() and json.loads(marker.read_text())["base_revision"] != revision:
        raise ValueError("Base definitions changed; choose a fresh overlay directory")
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
    )
    custom = (
        Path(__file__).parent / "definitions" / "applications" / "NXxrm_image.nxdl.xml"
    )
    shutil.copy2(custom, destination / "applications" / custom.name)
    marker.write_text(
        json.dumps(
            {
                "base_revision": revision,
                "NXxrm_image_sha256": hashlib.sha256(custom.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )
    return destination


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("destination")
    print(prepare_definitions(p.parse_args().destination))
