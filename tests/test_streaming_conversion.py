"""Tests for deterministic axes and bounded-memory TIFF streaming."""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
from PIL import Image

from pynxtools_xrm.models import CompressionConfig
from pynxtools_xrm.reader import XRMReader, centered_axis
from pynxtools_xrm.streaming_writer import convert_tomoproc
from pynxtools_xrm.tiff_stack import discover_tiff_stack


def _inputs(tmp_path: Path) -> tuple[Path, Path, list[np.ndarray]]:
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


def test_manifest_and_centered_axis(tmp_path):
    _, tiffs, _ = _inputs(tmp_path)
    manifest = discover_tiff_stack(tiffs)
    assert manifest.image_shape == (3, 4)
    assert manifest.volume_shape == (4, 3, 3)
    np.testing.assert_allclose(centered_axis(4, 0.5), [-0.75, -0.25, 0.25, 0.75])
    np.testing.assert_allclose(centered_axis(3, 0.5), [-0.5, 0.0, 0.5])


def test_multiformat_reader_does_not_add_volume(tmp_path):
    metadata, tiffs, _ = _inputs(tmp_path)
    manifest = discover_tiff_stack(tiffs)
    template = XRMReader().read(
        template={}, file_paths=(str(metadata),), objects=(manifest,)
    )
    assert "/ENTRY[entry]/data/data" not in template
    assert template["/ENTRY[entry]/definition"] == "NXtomoproc"
    assert template["/ENTRY[entry]/data/y"].shape == (3,)


def test_streamed_volume_shape_orientation_and_compression(tmp_path):
    metadata, tiffs, layers = _inputs(tmp_path)
    output = tmp_path / "result.nxs"
    seen: list[int] = []
    report = convert_tomoproc(
        metadata,
        tiffs,
        output,
        compression=CompressionConfig(level=1, target_chunk_bytes=32),
        progress=lambda current, _total, _path: seen.append(current),
    )
    assert report.shape == (4, 3, 3)
    assert report.slices_written == 3
    assert seen == [1, 2, 3]
    with h5py.File(output, "r") as handle:
        data = handle["/entry/data/data"]
        assert data.shape == (4, 3, 3)
        assert data.compression == "gzip"
        for y_index, layer in enumerate(layers):
            np.testing.assert_array_equal(data[:, y_index, :], layer.T)
        np.testing.assert_allclose(handle["/entry/data/x"][:], centered_axis(4, 0.5))
        np.testing.assert_allclose(handle["/entry/data/y"][:], centered_axis(3, 0.5))
        np.testing.assert_allclose(handle["/entry/data/z"][:], centered_axis(3, 0.5))
