"""Read ZEISS compound files without materializing an image stack.

Decoding is deliberately scoped to documented stream paths. All other metadata
are retained as bytes, not guessed from their apparent numeric values.
"""

from __future__ import annotations

import base64
import re
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import olefile

DTYPES = {5: np.dtype("<u2"), 10: np.dtype("<f4")}
IMAGE_STREAM = re.compile(r"(?:^|/)(?:ImageData\d+/Image\d+|Image\d*)$", re.I)


def _scalar(ole, path, fmt):
    if not ole.exists(path):
        return None
    raw = ole.openstream(path).read()
    if len(raw) != struct.calcsize(fmt):
        raise ValueError(f"Unexpected scalar stream size: {path}")
    return struct.unpack(fmt, raw)[0]


def _text(ole, path):
    if not ole.exists(path):
        return None
    return (
        ole.openstream(path)
        .read()
        .split(b"\0", 1)[0]
        .decode("cp1252", errors="replace")
        .strip()
    )


def _array(ole, path, dtype="<f4"):
    if not ole.exists(path):
        return None
    raw = ole.openstream(path).read()
    if len(raw) % np.dtype(dtype).itemsize:
        raise ValueError(f"Invalid array byte count: {path}")
    return np.frombuffer(raw, dtype=dtype).copy()


def metadata_streams(ole, excluded):
    """Keep every non-pixel stream, including unrecognized manufacturer fields."""
    return {
        "/".join(p): ole.openstream(p).read()
        for p in ole.listdir()
        if "/".join(p) not in excluded
    }


@dataclass(frozen=True)
class ImageBlock:
    name: str
    streams: tuple[str, ...]
    shape: tuple[int, int]
    dtype: np.dtype


class ZeissSource:
    """Header manifest plus reopenable, bounded-memory access to frames."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.kind = self.path.suffix.casefold()
        if self.kind not in {".txrm", ".txm", ".xrm"}:
            raise ValueError(f"Not a ZEISS image filename: {self.path}")
        self.values = {}
        with olefile.OleFileIO(str(self.path)) as ole:
            n = _scalar(ole, "ImageInfo/NoOfImages", "<I")
            h = _scalar(ole, "ImageInfo/ImageHeight", "<I")
            w = _scalar(ole, "ImageInfo/ImageWidth", "<I")
            code = _scalar(ole, "ImageInfo/DataType", "<I")
            if not n or not h or not w:
                raise ValueError("Missing or invalid ZEISS image dimensions")
            if code not in DTYPES:
                raise ValueError(f"Unsupported ZEISS DataType {code}")
            if self.kind == ".xrm" and n != 1:
                raise ValueError("XRM single-image file contains multiple frames")
            self.frame_count, self.image_shape, self.dtype = n, (h, w), DTYPES[code]
            streams = tuple(f"ImageData{i // 100 + 1}/Image{i + 1}" for i in range(n))
            primary_streams = set(streams)
            self.primary = ImageBlock("primary", streams, (h, w), self.dtype)
            blocks = {}
            for parts in ole.listdir():
                key = "/".join(parts)
                if not IMAGE_STREAM.search(key) or key in primary_streams:
                    continue
                prefix = key.split("/", 1)[0]
                blocks.setdefault(prefix, []).append(key)
            self.auxiliary = []
            for prefix, names in sorted(blocks.items()):
                ah = _scalar(ole, f"{prefix}/ImageInfo/ImageHeight", "<I")
                aw = _scalar(ole, f"{prefix}/ImageInfo/ImageWidth", "<I")
                ac = _scalar(ole, f"{prefix}/DataType", "<I")
                if ac is None:
                    ac = _scalar(ole, f"{prefix}/ImageInfo/DataType", "<I")
                if not ah or not aw or ac not in DTYPES:
                    raise ValueError(f"Unsupported auxiliary image header: {prefix}")
                names.sort(
                    key=lambda s: int(re.search(r"Image(\d*)$", s, re.I)[1] or "1")
                )
                self.auxiliary.append(
                    ImageBlock(prefix, tuple(names), (ah, aw), DTYPES[ac])
                )
            excluded = {
                s for block in [self.primary, *self.auxiliary] for s in block.streams
            }
            for block in [self.primary, *self.auxiliary]:
                for stream in block.streams:
                    if (
                        not ole.exists(stream)
                        or ole.get_size(stream)
                        != np.prod(block.shape) * block.dtype.itemsize
                    ):
                        raise ValueError(f"Missing or invalid image stream: {stream}")
            self.raw_metadata = metadata_streams(ole, excluded)
            self._read_values(ole)

    def _read_values(self, ole):
        mapping = {
            "pixel_size_um": "PixelSize",
            "camera_pixel_size_um": "CamPixelSize",
            "optical_magnification": "OpticalMagnification",
        }
        if self.kind == ".txm":
            mapping["slice_y_um"] = "YPosition"
        else:
            mapping.update(
                theta="Angles",
                exposure_s="ExpTimes",
                stage_x_um="XPosition",
                stage_y_um="YPosition",
                stage_z_um="ZPosition",
                source_voltage_kv="XrayVoltage",
                source_current_ua="XrayCurrent",
                source_x_mm="StoRADistance",
                detector_x_mm="DtoRADistance",
            )
        for name, field in mapping.items():
            a = _array(ole, "ImageInfo/" + field)
            if (
                a is not None
                and a.size in {1, self.frame_count}
                and np.all(np.isfinite(a))
            ):
                self.values[name] = a.item() if a.size == 1 else a
        for name, stream in {
            "camera_name": "ImageInfo/CameraName",
            "camera_serial": "ImageInfo/CameraSerialNumberString",
            "objective": "ImageInfo/ObjectiveName",
            "filter": "ImageInfo/SourceFilterName",
            "acquisition_mode": "AcquisitionSettings/AcqModeString",
        }.items():
            value = _text(ole, stream)
            if value:
                self.values[name] = value
        status = _text(ole, "AcquisitionSettings/StatusString") or ""
        names = {
            line.strip()
            for line in re.findall(r"(?im)^[ \t]*sample:[ \t]*([^\r\n]+)", status)
        } - {""}
        if len(names) == 1:
            self.values["sample_name"] = names.pop()
        dates = self.raw_metadata.get("ImageInfo/Date", b"")
        if len(dates) == 40 * self.frame_count:
            records = [
                dates[i : i + 40].partition(b"\0")[0] for i in range(0, len(dates), 40)
            ]
            if all(
                re.fullmatch(
                    rb"\d{1,2}/\d{1,2}/\d{4} \d{2}:\d{2}:\d{2}(?:\.\d+)?", record
                )
                for record in records
            ):
                self.values["recorded_times"] = [
                    record.decode("ascii") for record in records
                ]
        if self.raw_metadata.get("ImageInfo/XrayPresent") == b"\x01":
            self.values["probe"] = "x-ray"
            index = _scalar(ole, "ImageInfo/SrcAssemblyIndex", "<i")
            if index is not None and index >= 0:
                config = f"ConfigureBackup/ConfigSources/Source {index + 1}"
                name = _text(ole, f"{config}/SourceName")
                if name:
                    self.values["source_name"] = name
        if self.kind == ".txm":
            for name, stream in (
                ("raw_file", "ReconSettings/InputFileName"),
                ("output_file", "ReconSettings/OutputFileLocation"),
            ):
                value = _text(ole, stream)
                if value:
                    self.values[name] = value

    def iter_frames(self, block=None):
        block = block or self.primary
        with olefile.OleFileIO(str(self.path)) as ole:
            for stream in block.streams:
                raw = ole.openstream(stream).read()
                if len(raw) != np.prod(block.shape) * block.dtype.itemsize:
                    raise ValueError(f"Image changed after inspection: {stream}")
                yield np.frombuffer(raw, dtype=block.dtype).reshape(block.shape)

    def read_frame(self, index):
        if not 0 <= index < self.frame_count:
            raise IndexError(index)
        with olefile.OleFileIO(str(self.path)) as ole:
            raw = ole.openstream(self.primary.streams[index]).read()
        if len(raw) != np.prod(self.image_shape) * self.dtype.itemsize:
            raise ValueError("Image changed after inspection")
        return np.frombuffer(raw, dtype=self.dtype).reshape(self.image_shape)


def read_recipe(path):
    path = Path(path).resolve()
    with olefile.OleFileIO(str(path)) as ole:
        raw = {
            key: base64.b64encode(value).decode("ascii")
            for key, value in metadata_streams(ole, set()).items()
        }
        points = {}
        for parts in ole.listdir():
            if re.fullmatch(r"RecipePoint\d+", parts[0]):
                points.setdefault(parts[0], {})
        for point, values in points.items():
            for field in ("SampleName", "PointName"):
                values[field] = _text(ole, f"{point}/{field}")
            for field in ("AcqFileName", "SrcDriftFileName"):
                values[field] = _text(ole, f"{point}/AcquisitionSettings/{field}")
    return {"path": str(path), "points": points, "raw_streams_base64": raw}
