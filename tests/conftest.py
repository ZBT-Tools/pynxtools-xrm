"""Shared synthetic XRM inputs for unit and integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def xrm_inputs(tmp_path: Path) -> tuple[Path, Path, list[np.ndarray]]:
    """Create a tiny numbered TIFF stack and matching eLabFTW JSON export."""

    tiffs = tmp_path / "layers"
    tiffs.mkdir()
    layers = [
        np.arange(12, dtype=np.uint16).reshape(3, 4) + index * 100 for index in range(3)
    ]
    for index, layer in enumerate(layers, start=1):
        Image.fromarray(layer).save(tiffs / f"slice{index:04d}.tiff")

    metadata = tmp_path / "metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "title": "Synthetic XRM",
                "metadata_decoded": {
                    "extra_fields": {
                        "Sample name": {"value": "sample-a"},
                        "Acquisition pixel size": {"value": 0.5, "unit": "um"},
                        "Reconstruction software": {"value": "Dragonfly 3D"},
                        "Software version": {"value": "2024.1"},
                        "Measurement date": {"value": "2026-08-26"},
                        "Raw data path": {"value": "raw.txrm"},
                        "XRM system / instrument": {"value": 109},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return metadata, tiffs, layers
