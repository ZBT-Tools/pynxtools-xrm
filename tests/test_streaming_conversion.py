"""Streaming, provenance and strict semantic regression tests."""

import json

import h5py
import numpy as np
import pytest

from pynxtools_xrm.errors import MissingRequiredMetadata
from pynxtools_xrm.models import CompressionConfig
from pynxtools_xrm.reader import XRMReader, centered_axis
from pynxtools_xrm.streaming_writer import convert, convert_tomoproc
from pynxtools_xrm.tiff_stack import discover_tiff_stack


def edit_json(path, update):
    data = json.loads(path.read_text())
    update(data)
    path.write_text(json.dumps(data))


@pytest.mark.parametrize(("value", "unit"), [(500, "nm"), (0.5, "um"), (0.0005, "mm")])
def test_voxel_units(xrm_inputs, value, unit):
    metadata, tiffs, _ = xrm_inputs
    edit_json(
        metadata,
        lambda d: d["metadata_decoded"]["extra_fields"].update(
            {"Reconstructed voxel size": {"value": value, "unit": unit}}
        ),
    )
    template = XRMReader().read(
        template={},
        file_paths=(str(metadata),),
        objects=(discover_tiff_stack(tiffs),),
        streaming=True,
    )
    np.testing.assert_allclose(template["/ENTRY[entry]/data/x"], centered_axis(4, 0.5))


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_voxels(xrm_inputs, value):
    metadata, tiffs, _ = xrm_inputs
    edit_json(
        metadata,
        lambda d: d["metadata_decoded"]["extra_fields"][
            "Reconstructed voxel size"
        ].update(value=value),
    )
    with pytest.raises(ValueError, match="finite and greater than zero"):
        convert_tomoproc(metadata, tiffs, tiffs.parent / "invalid.nxs")


def test_streamed_volume(tmp_path, xrm_inputs):
    metadata, tiffs, layers = xrm_inputs
    seen = []
    output = tmp_path / "volume.nxs"
    report = convert_tomoproc(
        metadata,
        tiffs,
        output,
        compression=CompressionConfig(level=1, target_chunk_bytes=32),
        progress=lambda i, n, p: seen.append(i),
    )
    assert report.shape == (4, 3, 3) and seen == [1, 2, 3]
    assert report.assumptions == ()
    with h5py.File(output) as h:
        a = h["entry/data/data"]
        assert a.dtype == np.dtype("uint16") and a.chunks[1] == 1
        for i, frame in enumerate(layers):
            np.testing.assert_array_equal(a[:, i, :], frame.T)
        assert h["entry/instrument/detector/layout"].asstr()[()] == "area"
        assert h["entry/instrument/detector/type"].asstr()[()] == "planar area detector"
        assert h["entry/reconstruction/date"].asstr()[()] == "2026-08-27T10:00:00+02:00"
        assert h["entry/notes/data"][()] == b"Synthetic scan"
        np.testing.assert_array_equal(h["entry/global_frame/x"][:], [0, 0, 1])


def test_no_reconstruction_date_fallback(tmp_path, xrm_inputs):
    metadata, tiffs, _ = xrm_inputs
    edit_json(
        metadata,
        lambda d: d["metadata_decoded"]["extra_fields"].pop("Reconstruction date"),
    )
    with pytest.raises(MissingRequiredMetadata, match="reconstruction_date"):
        convert_tomoproc(metadata, tiffs, tmp_path / "missing.nxs")
    assert not (tmp_path / "missing.nxs").exists()


def test_no_acquisition_voxel_fallback(tmp_path, xrm_inputs):
    metadata, tiffs, _ = xrm_inputs
    edit_json(
        metadata,
        lambda d: d["metadata_decoded"]["extra_fields"].pop("Reconstructed voxel size"),
    )
    with pytest.raises(MissingRequiredMetadata, match="pixel_size_um"):
        convert_tomoproc(metadata, tiffs, tmp_path / "missing.nxs")


def test_tiff_raw_target_and_frame_keys(tmp_path, xrm_inputs):
    metadata, tiffs, layers = xrm_inputs
    edit_json(
        metadata,
        lambda d: d["xrm_configuration"].update(
            theta=[-2, 0.25, 8], image_key=[0, 1, 2]
        ),
    )
    output = tmp_path / "raw.nxs"
    convert(tiffs, output, metadata_file=metadata, target_definition="NXtomo")
    with h5py.File(output) as h:
        np.testing.assert_array_equal(
            h["entry/sample/rotation_angle"][:], [-2, 0.25, 8]
        )
        np.testing.assert_array_equal(h["entry/data/image_key"][:], [0, 1, 2])
        for i, frame in enumerate(layers):
            np.testing.assert_array_equal(h["entry/data/data"][i], frame.T)


def test_atomic_failure_preserves_previous_output(tmp_path, xrm_inputs, monkeypatch):
    metadata, tiffs, _ = xrm_inputs
    output = tmp_path / "existing.nxs"
    convert_tomoproc(metadata, tiffs, output)
    previous = output.read_bytes()
    edit_json(metadata, lambda d: d.update(title="changed"))

    def fail(self, block=None):
        raise OSError("simulated frame read failure")
        yield

    monkeypatch.setattr("pynxtools_xrm.tiff_stack.TiffSource.iter_frames", fail)
    with pytest.raises(OSError, match="simulated"):
        convert_tomoproc(metadata, tiffs, output, overwrite=True)
    assert output.read_bytes() == previous
    assert not list(tmp_path.glob("*.part"))
    assert not list(tmp_path.glob("*.lock"))


def test_standard_reader_guidance_and_reuse(xrm_inputs):
    metadata, tiffs, _ = xrm_inputs
    reader = XRMReader()
    with pytest.raises(RuntimeError, match="pynx-xrm convert"):
        reader.read(template={}, file_paths=(str(metadata),))
    for _ in range(2):
        t = reader.read(
            template={},
            file_paths=(str(metadata),),
            objects=(discover_tiff_stack(tiffs),),
            streaming=True,
        )
        assert "/ENTRY[entry]/data/data" not in t


def test_tiff_stack_cannot_use_single_image_target(tmp_path, xrm_inputs):
    metadata, tiffs, _ = xrm_inputs
    output = tmp_path / "single.nxs"
    with pytest.raises(ValueError, match="TIFF stacks require"):
        convert(tiffs, output, metadata_file=metadata, target_definition="NXxrm_image")
    assert not output.exists()
