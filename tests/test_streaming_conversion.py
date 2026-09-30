"""Tests for deterministic axes and bounded-memory TIFF streaming."""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from pynxtools_xrm.models import CompressionConfig
from pynxtools_xrm.reader import XRMReader, centered_axis
from pynxtools_xrm.streaming_writer import convert_tomoproc
from pynxtools_xrm.tiff_stack import discover_tiff_stack


def test_manifest_and_centered_axis(xrm_inputs):
    _, tiffs, _ = xrm_inputs
    manifest = discover_tiff_stack(tiffs)
    assert manifest.image_shape == (3, 4)
    assert manifest.volume_shape == (4, 3, 3)
    np.testing.assert_allclose(centered_axis(4, 0.5), [-0.75, -0.25, 0.25, 0.75])
    np.testing.assert_allclose(centered_axis(3, 0.5), [-0.5, 0.0, 0.5])


def test_multiformat_reader_does_not_add_volume(xrm_inputs):
    metadata, tiffs, _ = xrm_inputs
    manifest = discover_tiff_stack(tiffs)
    template = XRMReader().read(
        template={},
        file_paths=(str(metadata),),
        objects=(manifest,),
        streaming=True,
    )
    assert "/ENTRY[entry]/data/data" not in template
    assert template["/ENTRY[entry]/definition"] == "NXtomoproc"
    assert template["/ENTRY[entry]/data/y"].shape == (3,)


def test_standard_pynxtools_writer_is_rejected_with_guidance(xrm_inputs):
    metadata, tiffs, _ = xrm_inputs
    inputs = (str(metadata), *(str(path) for path in sorted(tiffs.glob("*.tiff"))))

    with pytest.raises(RuntimeError, match="pynx-xrm convert"):
        XRMReader().read(template={}, file_paths=inputs)


def test_streamed_volume_shape_orientation_and_compression(tmp_path, xrm_inputs):
    metadata, tiffs, layers = xrm_inputs
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
        assert data.attrs["offset"] == "0.0"
        assert data.attrs["scaling"] == "1.0"
        assert handle["/entry/instrument/source/type"].asstr()[()] == "Fixed Tube X-ray"
        for y_index, layer in enumerate(layers):
            np.testing.assert_array_equal(data[:, y_index, :], layer.T)
        np.testing.assert_allclose(handle["/entry/data/x"][:], centered_axis(4, 0.5))
        np.testing.assert_allclose(handle["/entry/data/y"][:], centered_axis(3, 0.5))
        np.testing.assert_allclose(handle["/entry/data/z"][:], centered_axis(3, 0.5))
