"""Synthetic compound streams exercise actual decoding and streaming selections."""

import base64
import io
import struct

import h5py
import numpy as np
import pytest

from pynxtools_xrm.errors import (
    AmbiguousMetadataAssociation,
    MetadataConflict,
    MissingRequiredMetadata,
)
from pynxtools_xrm.geometry import berlin_timestamp, stage_orientation
from pynxtools_xrm.metadata import ResolvedMetadata
from pynxtools_xrm.streaming_writer import convert
from pynxtools_xrm.zeiss import ZeissSource, associate_recipe, read_recipe


@pytest.fixture
def compound_files(tmp_path, monkeypatch):
    files = {}

    class Ole:
        def __init__(self, path):
            self.data = files[str(path)]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def exists(self, name):
            return name in self.data

        def listdir(self):
            return [p.split("/") for p in self.data]

        def get_size(self, name):
            return len(self.data["/".join(name) if isinstance(name, list) else name])

        def openstream(self, name):
            return io.BytesIO(
                self.data["/".join(name) if isinstance(name, list) else name]
            )

    monkeypatch.setattr("pynxtools_xrm.zeiss.olefile.OleFileIO", Ole)

    def make(suffix=".txrm", n=3, code=5, auxiliary=False):
        path = tmp_path / (f"input-{len(files)}" + suffix)
        path.write_bytes(b"synthetic test fixture")
        dtype = {5: "<u2", 10: "<f4"}[code]
        data = {
            "ImageInfo/" + k: struct.pack("<I", v)
            for k, v in {
                "NoOfImages": n,
                "ImageHeight": 3,
                "ImageWidth": 4,
                "DataType": code,
            }.items()
        }
        for k, values in {
            "PixelSize": [0.5],
            "Angles": [0] * n,
            "ExpTimes": [4] * n,
            "XPosition": [0] * n,
            "YPosition": [10 + 0.5 * i for i in range(n)]
            if suffix == ".txm"
            else [10] * n,
            "ZPosition": [0] * n,
        }.items():
            data["ImageInfo/" + k] = np.asarray(values, dtype="<f4").tobytes()
        data["ImageInfo/Date"] = b"".join(
            f"08/26/2026 09:44:{i % 60:02d}.487".encode().ljust(40, b"\0")
            for i in range(n)
        )
        frames = [np.arange(12, dtype=dtype).reshape(3, 4) + i for i in range(n)]
        for i, a in enumerate(frames):
            data[f"ImageData{i // 100 + 1}/Image{i + 1}"] = a.tobytes()
        if suffix == ".txm":
            for a, value in zip("XYZ", [0, 10 + 0.5 * (n - 1) / 2, 0], strict=True):
                data["ReconInputTomoParams/MeanSample" + a] = struct.pack("<f", value)
            data["ReconSettings/InputFileName"] = b"original.txrm\0"
        if auxiliary:
            data["ReferenceData/ImageInfo/ImageHeight"] = struct.pack("<I", 3)
            data["ReferenceData/ImageInfo/ImageWidth"] = struct.pack("<I", 4)
            data["ReferenceData/DataType"] = struct.pack("<I", 10)
            data["ReferenceData/Image"] = np.full((3, 4), 1.25, dtype="<f4").tobytes()
        data["unknown/vendor_code"] = b"\0\xff\x02"
        files[str(path)] = data
        return path, frames, data

    return make, files


def test_numeric_stream_order_and_one_frame_access(compound_files):
    make, _ = compound_files
    path, frames, data = make(n=101)
    source = ZeissSource(path)
    np.testing.assert_array_equal(source.read_frame(100), frames[100])
    assert source.primary.streams[99:101] == (
        "ImageData1/Image100",
        "ImageData2/Image101",
    )
    assert len(list(source.iter_frames())) == 101
    assert (
        base64.b64decode(source.raw_metadata["unknown/vendor_code"])
        == data["unknown/vendor_code"]
    )
    assert source.values["frame_times"][0].endswith("+02:00")


@pytest.mark.parametrize("code", [5, 10])
def test_single_image_preserves_dtype(tmp_path, compound_files, code):
    make, _ = compound_files
    path, frames, _ = make(".xrm", n=1, code=code)
    output = tmp_path / "image.nxs"
    convert(path, output, supplements={"sample_name": "explicit sample"})
    with h5py.File(output) as h:
        a = h["entry/image/image_2d/intensity"]
        assert a.dtype == frames[0].dtype
        np.testing.assert_array_equal(a[:], frames[0])
        assert h["entry/definition"].asstr()[()] == "NXxrm_image"


def test_auxiliary_float_images_not_cast_into_primary(tmp_path, compound_files):
    make, _ = compound_files
    path, frames, _ = make(auxiliary=True)
    output = tmp_path / "raw.nxs"
    convert(path, output, supplements={"sample_name": "sample"})
    with h5py.File(output) as h:
        assert h["entry/instrument/detector/data"].dtype == np.dtype("uint16")
        assert h["entry/auxiliary_0/data"].dtype == np.dtype("float32")
        np.testing.assert_array_equal(
            h["entry/auxiliary_0/data"][0], np.full((3, 4), 1.25)
        )
        for i, frame in enumerate(frames):
            np.testing.assert_array_equal(h["entry/data/data"][i], frame.T)


def test_txm_missing_metadata_and_calibrated_volume(tmp_path, compound_files):
    make, _ = compound_files
    path, frames, _ = make(".txm")
    output = tmp_path / "volume.nxs"
    with pytest.raises(MissingRequiredMetadata) as exc:
        convert(path, output)
    assert "reconstruction_date" in exc.value.missing and not output.exists()
    supplements = dict(
        sample_name="sample",
        source_type="Fixed Tube X-ray",
        source_name="test",
        reconstruction_program="Test reconstruction",
        reconstruction_version="1",
        reconstruction_date="2026-08-27T09:00:00",
        image_orientation=dict(
            row_axis="z", column_axis="x", row_sign=1, column_sign=-1
        ),
    )
    convert(path, output, supplements=supplements)
    with h5py.File(output) as h:
        for i, frame in enumerate(frames):
            np.testing.assert_array_equal(h["entry/data/data"][:, i, :], frame.T)
        assert np.all(np.diff(h["entry/data/x"][:]) < 0)
        assert h["entry/reconstruction/date"].asstr()[()].endswith("+02:00")


def test_strict_precedence_and_explicit_no_override():
    meta = ResolvedMetadata()
    meta.add({"sample_name": "binary", "zero": 0}, "image")
    meta.add({"sample_name": "recipe", "extra": 4}, "RCP")
    assert meta.values["sample_name"] == "binary" and meta.values["zero"] == 0
    assert len(meta.conflicts) == 1
    with pytest.raises(MetadataConflict):
        meta.add({"sample_name": "explicit"}, "config", supplement=True)


def test_txm_distances_use_reconstruction_um_not_acquisition_mm(compound_files):
    make, _ = compound_files
    path, _, streams = make(".txm")
    for field, distance in (("StoRADistance", 6003.3716), ("DtoRADistance", 6001.8433)):
        streams["ImageInfo/" + field] = np.full(3, distance, dtype="<f4").tobytes()
        streams["ReconInputTomoParams/" + field] = struct.pack("<f", distance)
    source = ZeissSource(path)
    assert source.values["source_x_mm"] == pytest.approx(-6.0033716)
    assert source.values["detector_x_mm"] == pytest.approx(6.0018433)
    assert (
        base64.b64decode(source.raw_metadata["ImageInfo/StoRADistance"])
        == streams["ImageInfo/StoRADistance"]
    )
    raw, _, raw_streams = make(".txrm")
    raw_streams["ImageInfo/StoRADistance"] = np.full(
        3, -6.0033716, dtype="<f4"
    ).tobytes()
    np.testing.assert_allclose(
        ZeissSource(raw).values["source_x_mm"], source.values["source_x_mm"], atol=1e-6
    )


@pytest.mark.parametrize(
    ("text", "offset"),
    [
        ("2026-08-26T10:00:00", "+02:00"),
        ("2026-01-26T10:00:00", "+01:00"),
        ("2026-08-26T08:00:00Z", "+02:00"),
    ],
)
def test_berlin_times(text, offset):
    assert berlin_timestamp(text).endswith(offset)


@pytest.mark.parametrize(
    "text", ["2026-08-26", "2026-03-29T02:30:00", "2026-10-25T02:30:00"]
)
def test_missing_or_ambiguous_times(text):
    with pytest.raises(ValueError):
        berlin_timestamp(text)


def test_rotating_stage_is_right_handed():
    for angle, expected in [
        (0, [[0, 0, 1], [0, 1, 0], [-1, 0, 0]]),
        (90, [[-1, 0, 0], [0, 1, 0], [0, 0, -1]]),
        (-90, np.eye(3)),
    ]:
        actual = stage_orientation(angle)
        np.testing.assert_allclose(actual, expected, atol=1e-12)
        assert np.linalg.det(actual) == pytest.approx(1)


def test_recipe_stream_preservation_and_association(tmp_path, compound_files):
    make, files = compound_files
    path, _, _ = make()
    recipe_path = tmp_path / "recipe.rcp"
    recipe_path.write_bytes(b"fixture")
    files[str(recipe_path)] = {
        "RecipePoint1/SampleName": b"sample\0",
        "RecipePoint1/AcquisitionSettings/AcqFileName": str(path).encode() + b"\0",
        "UnknownSetting": b"\x00\xff\x01",
    }
    recipe = read_recipe(recipe_path)
    assert (
        base64.b64decode(recipe["raw_streams_base64"]["UnknownSetting"])
        == b"\x00\xff\x01"
    )
    assert associate_recipe(ZeissSource(path), [recipe])[2]["SampleName"] == "sample"
    with pytest.raises(AmbiguousMetadataAssociation):
        associate_recipe(ZeissSource(path), [recipe, recipe])


def test_reuse_and_compression_change(tmp_path, compound_files):
    from pynxtools_xrm.models import CompressionConfig  # noqa: PLC0415

    make, _ = compound_files
    path, _, _ = make(".xrm", n=1)
    output = tmp_path / "cache.nxs"
    options = dict(supplements={"sample_name": "test"}, overwrite=True)
    assert not convert(path, output, **options).reused
    assert convert(path, output, **options).reused
    assert not convert(
        path, output, compression=CompressionConfig(level=1), **options
    ).reused
    with h5py.File(output) as h:
        assert h["entry/instrument/detector/data"].compression_opts == 1


def test_unknown_datatype_is_rejected(compound_files):
    make, files = compound_files
    path, _, _ = make()
    files[str(path)]["ImageInfo/DataType"] = struct.pack("<I", 99)
    with pytest.raises(ValueError, match="Unsupported ZEISS DataType"):
        ZeissSource(path)
