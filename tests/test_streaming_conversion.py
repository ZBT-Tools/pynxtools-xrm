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
    assert template["/ENTRY[entry]/USER[user]/name"] == "Example Author"
    assert template["/ENTRY[entry]/USER[experimenter]/name"] == "Example Operator"
    assert template["/ENTRY[entry]/entry_identifier"] == "20261002-example"
    assert template["/ENTRY[entry]/experiment_identifier"] == "project-7"
    assert template["/ENTRY[entry]/SAMPLE[sample]/temperature"] == 20.0
    assert template["/ENTRY[entry]/SAMPLE[sample]/POSITIONER[stage_y]/value"] == 2.0
    assert (
        template["/ENTRY[entry]/INSTRUMENT[instrument]/DETECTOR[detector]/count_time"]
        == 4.0
    )


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
    assert any("Detector layout" in assumption for assumption in report.assumptions)
    assert any("signed distances" in assumption for assumption in report.assumptions)
    assert seen == [1, 2, 3]
    with h5py.File(output, "r") as handle:
        data = handle["/entry/data/data"]
        assert data.shape == (4, 3, 3)
        assert data.compression == "gzip"
        assert data.attrs["offset"] == "0.0"
        assert data.attrs["scaling"] == "1.0"
        assert handle["/entry/instrument/source/type"].asstr()[()] == "Fixed Tube X-ray"
        assert handle["/entry/instrument/name"].asstr()[()] == (
            "XRM system / instrument 109"
        )
        assert (
            handle["/entry/instrument/source/name"].id
            == handle["/entry/instrument/name"].id
        )
        assert handle["/entry/instrument/source/power"][()] == 4.5
        assert handle["/entry/instrument/source/power"].attrs["units"] == "W"
        assert handle["/entry/instrument/source/voltage"][()] == 50.0
        assert handle["/entry/instrument/detector"].attrs["NX_class"] == "NXdetector"
        assert handle["/entry/instrument/detector/distance"][()] == 5.5
        assert handle["/entry/instrument/detector/count_time"][()] == 4.0
        assert handle["/entry/user"].attrs["NX_class"] == "NXuser"
        assert handle["/entry/user/name"].asstr()[()] == "Example Author"
        assert handle["/entry/experimenter/name"].asstr()[()] == "Example Operator"
        assert handle["/entry/sample/description"].asstr()[()] == "test coupon"
        assert handle["/entry/sample/temperature"][()] == 20.0
        assert handle["/entry/sample/stage_z/value"][()] == 3.0
        assert handle["/entry/sample/stage_z/value"].attrs["units"] == "mm"
        assert handle["/entry/experiment_identifier"].asstr()[()] == "project-7"
        assert handle["/entry/collection_time"][()] == 1.0
        assert handle["/entry/collection_time"].attrs["units"] == "hour"
        assert handle["/entry/acquisition/number_of_projections"][()] == 1000.0
        assert (
            handle["/entry/reconstruction/parameters/beam_hardening_correction"][()]
            == 0.0
        )
        assert (
            handle["/entry/reconstruction/parameters/beam_hardening_correction"].attrs[
                "units"
            ]
            == "%"
        )
        assert handle["/entry/notes/author"].id == handle["/entry/user/name"].id
        assert (
            handle["/entry/elabftw/identifier_elabftw"].id
            == handle["/entry/entry_identifier"].id
        )
        assert (
            handle["/entry/data_provenance/raw_data_path"].id
            == handle["/entry/reconstruction/parameters/raw_file"].id
        )
        assert (
            handle["/entry/data_provenance/reconstruction_path"].id
            == handle["/entry/data_provenance/analysis_path"].id
            == handle["/entry/data_provenance/results_storage_path"].id
        )
        for y_index, layer in enumerate(layers):
            np.testing.assert_array_equal(data[:, y_index, :], layer.T)
        np.testing.assert_allclose(handle["/entry/data/x"][:], centered_axis(4, 0.5))
        np.testing.assert_allclose(handle["/entry/data/y"][:], centered_axis(3, 0.5))
        np.testing.assert_allclose(handle["/entry/data/z"][:], centered_axis(3, 0.5))
