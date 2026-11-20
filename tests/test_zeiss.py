"""Synthetic compound streams exercise actual decoding and streaming selections."""

import base64
import io
import struct

import h5py
import numpy as np
import pytest

from pynxtools_xrm.errors import MetadataConflict, MissingRequiredMetadata
from pynxtools_xrm.geometry import berlin_timestamp, stage_orientation
from pynxtools_xrm.metadata import ResolvedMetadata
from pynxtools_xrm.streaming_writer import convert
from pynxtools_xrm.zeiss import ZeissSource, read_recipe


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
            data["ReconSettings/OutputFileLocation"] = b"reconstruction.txm\0"
        if suffix == ".txrm":
            data["AcquisitionSettings/AcqModeString"] = b"Tomography\0"
            data["AcquisitionSettings/StatusString"] = (
                b"\n\tSample: sample-a\n\tTomo Point: A\0"
            )
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
    assert source.raw_metadata["unknown/vendor_code"] == data["unknown/vendor_code"]
    assert source.raw_metadata["ImageInfo/Date"] == data["ImageInfo/Date"]
    assert "frame_times" not in source.values


@pytest.mark.parametrize("code", [5, 10])
def test_single_image_preserves_dtype(tmp_path, compound_files, code):
    make, _ = compound_files
    path, frames, _ = make(".xrm", n=1, code=code)
    output = tmp_path / "image.nxs"
    convert(path, output)
    with h5py.File(output) as h:
        a = h["entry/data/data"]
        assert a.dtype == frames[0].dtype
        np.testing.assert_array_equal(a[:], frames[0])
        assert a.id == h["entry/instrument/detector/data"].id
        assert "definition" not in h["entry"]
        assert "name" not in h["entry/sample"]
        assert h["entry/data"].attrs["NX_class"] == "NXdata"
        raw = h["entry/zeiss_metadata"]
        paths = list(raw["stream_paths"].asstr()[:])
        offsets = raw["stream_offsets"][:]
        i = paths.index("unknown/vendor_code")
        assert (
            raw["stream_bytes"][offsets[i] : offsets[i + 1]].tobytes() == b"\0\xff\x02"
        )


def test_auxiliary_float_images_not_cast_into_primary(tmp_path, compound_files):
    make, _ = compound_files
    path, frames, _ = make(auxiliary=True)
    output = tmp_path / "raw.nxs"
    convert(path, output)
    with h5py.File(output) as h:
        assert h["entry/instrument/detector/data"].dtype == np.dtype("uint16")
        assert h["entry/auxiliary_0/data"].dtype == np.dtype("float32")
        assert h["entry/sample/name"].asstr()[()] == "sample-a"
        np.testing.assert_array_equal(
            h["entry/auxiliary_0/data"][0], np.full((3, 4), 1.25)
        )
        for i, frame in enumerate(frames):
            np.testing.assert_array_equal(h["entry/data/data"][i], frame.T)


def test_txm_missing_metadata_and_calibrated_volume(
    tmp_path, compound_files, monkeypatch
):
    make, _ = compound_files
    path, frames, _ = make(".txm")
    output = tmp_path / "volume.nxs"
    with pytest.raises(MissingRequiredMetadata) as exc:
        convert(path, output)
    assert "reconstruction/date" in exc.value.missing and not output.exists()
    # Exercise volume streaming with a synthetic decoder returning verified fields.
    source = ZeissSource(path)
    source.values.update(
        sample_name="sample",
        source_type="Fixed Tube X-ray",
        source_name="test",
        probe="x-ray",
        reconstruction_program="Test reconstruction",
        reconstruction_version="1",
        reconstruction_date="2026-08-27T09:00:00+02:00",
    )
    monkeypatch.setattr(
        "pynxtools_xrm.streaming_writer.ZeissSource", lambda path: source
    )
    convert(path, output)
    with h5py.File(output) as h:
        for i, frame in enumerate(frames):
            np.testing.assert_array_equal(h["entry/data/data"][:, i, :], frame.T)
        np.testing.assert_allclose(h["entry/data/x"][:], [0, 0.5, 1, 1.5])
        np.testing.assert_allclose(h["entry/data/y"][:], [0, 0.5, 1])
        assert h["entry/reconstruction/date"].asstr()[()].endswith("+02:00")


def test_strict_precedence_and_explicit_no_override():
    meta = ResolvedMetadata()
    meta.add({"sample_name": "binary", "zero": 0}, "image")
    meta.add({"sample_name": "recipe", "extra": 4}, "RCP")
    assert meta.values["sample_name"] == "binary" and meta.values["zero"] == 0
    assert len(meta.conflicts) == 1
    with pytest.raises(MetadataConflict):
        meta.add({"sample_name": "explicit"}, "config", supplement=True)


def test_txm_does_not_decode_layer_metadata_as_acquisition_settings(compound_files):
    make, _ = compound_files
    path, _, streams = make(".txm")
    for field, distance in (("StoRADistance", 6003.3716), ("DtoRADistance", 6001.8433)):
        streams["ImageInfo/" + field] = np.full(3, distance, dtype="<f4").tobytes()
        streams["ReconInputTomoParams/" + field] = struct.pack("<f", distance)
    source = ZeissSource(path)
    assert "source_x_mm" not in source.values
    assert "detector_x_mm" not in source.values
    assert "exposure_s" not in source.values
    assert (
        source.raw_metadata["ImageInfo/StoRADistance"]
        == streams["ImageInfo/StoRADistance"]
    )
    raw, _, raw_streams = make(".txrm")
    raw_streams["ImageInfo/StoRADistance"] = np.full(
        3, -6.0033716, dtype="<f4"
    ).tobytes()
    np.testing.assert_allclose(
        ZeissSource(raw).values["source_x_mm"], -6.0033716, atol=1e-6
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


def test_recipe_inspection_and_file_only_conversion(tmp_path, compound_files):
    make, files = compound_files
    path, _, streams = make()
    del streams["AcquisitionSettings/StatusString"]
    del streams["AcquisitionSettings/AcqModeString"]
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
    assert recipe["points"]["RecipePoint1"]["SampleName"] == "sample"
    output = tmp_path / "data.nxs"
    with pytest.raises(ValueError, match="inspection"):
        convert(path, output, recipe_paths=[recipe_path])
    with pytest.raises(ValueError, match="embedded"):
        convert(path, output, supplements={"sample_name": "external"})
    with pytest.raises(MissingRequiredMetadata) as exc:
        convert(path, output)
    assert exc.value.missing == ("sample/name", "instrument/detector/image_key")
    assert not output.exists()


def test_reuse_and_compression_change(tmp_path, compound_files):
    from pynxtools_xrm.models import CompressionConfig  # noqa: PLC0415

    make, _ = compound_files
    path, _, _ = make(".xrm", n=1)
    output = tmp_path / "cache.nxs"
    options = dict(overwrite=True)
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
