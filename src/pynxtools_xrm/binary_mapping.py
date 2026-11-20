"""Map each ZEISS image format directly to NeXus using its own metadata."""

from functools import partial
from pathlib import PureWindowsPath

import h5py
import numpy as np

from pynxtools_xrm.errors import MissingRequiredMetadata
from pynxtools_xrm.models import ImageLayout

DETECTOR_DATA = "/entry/instrument/detector/data"
ROTATION = "/entry/sample/rotation_angle"
IMAGE_KEY = "/entry/instrument/detector/image_key"


def nxgroup(parent, name, nx_class):
    group = parent.require_group(name)
    group.attrs["NX_class"] = nx_class
    return group


def field(group, name, value, units=None):
    dataset = group.create_dataset(name, data=value)
    if units is not None:
        dataset.attrs["units"] = units
    return dataset


def _write_original_streams(entry, streams):
    """Store opaque OLE streams as bytes indexed by their original paths."""
    collection = nxgroup(entry, "zeiss_metadata", "NXcollection")
    field(
        collection, "stream_paths", np.asarray(list(streams), dtype=h5py.string_dtype())
    )
    offsets = np.cumsum(
        [0, *(len(value) for value in streams.values())], dtype=np.int64
    )
    field(collection, "stream_offsets", offsets)
    collection.create_dataset(
        "stream_bytes",
        data=np.frombuffer(b"".join(streams.values()), dtype=np.uint8),
        compression="gzip",
    )


def _entry(handle, source, definition=None):
    handle.attrs["NX_class"] = "NXroot"
    entry = nxgroup(handle, "entry", "NXentry")
    if definition is not None:
        field(entry, "definition", definition)
    data = nxgroup(entry, "data", "NXdata")
    data.attrs["signal"] = "data"
    values = source.values
    instrument = nxgroup(entry, "instrument", "NXinstrument")
    detector = nxgroup(instrument, "detector", "NXdetector")
    for key, name, unit in (
        ("camera_name", "description", None),
        ("camera_serial", "serial_number", None),
        ("exposure_s", "count_time", "s"),
    ):
        if key in values:
            field(detector, name, values[key], unit)
    if "camera_pixel_size_um" in values:
        sensor = nxgroup(detector, "sensor", "NXcollection")
        field(sensor, "unbinned_pixel_size", values["camera_pixel_size_um"], "um")
    if "objective" in values or "optical_magnification" in values:
        lens = nxgroup(instrument, "objective", "NXoptical_lens")
        if "objective" in values:
            field(lens, "description", values["objective"])
        if "optical_magnification" in values:
            field(lens, "magnification", values["optical_magnification"])
    if "filter" in values:
        field(
            nxgroup(instrument, "filter", "NXfilter"), "description", values["filter"]
        )
    source_fields = (
        ("probe", "probe", None),
        ("source_name", "name", None),
        ("source_type", "type", None),
        ("source_voltage_kv", "voltage", "kV"),
        ("source_current_ua", "current", "uA"),
    )
    for key, name, unit in source_fields:
        if key in values:
            field(nxgroup(instrument, "source", "NXsource"), name, values[key], unit)
    if "sample_name" in values:
        field(nxgroup(entry, "sample", "NXsample"), "name", values["sample_name"])
    positions = {
        axis: values[f"stage_{axis}_um"]
        for axis in "xyz"
        if f"stage_{axis}_um" in values
    }
    if positions or (definition is None and "theta" in values):
        sample = nxgroup(entry, "sample", "NXsample")
        stage = nxgroup(sample, "stage_readback", "NXcollection")
        for axis, position in positions.items():
            field(stage, axis, position, "um")
        if definition is None and "theta" in values:
            field(sample, "rotation_angle", values["theta"], "deg")
    if any(key in values for key in ("source_x_mm", "detector_x_mm", "recorded_times")):
        acquisition = nxgroup(
            entry,
            "acquisition" if definition != "NXtomoproc" else "layer_metadata",
            "NXcollection",
        )
        for key, name in (
            ("source_x_mm", "source_to_rotation_axis"),
            ("detector_x_mm", "detector_to_rotation_axis"),
        ):
            if key in values:
                field(acquisition, name, values[key], "mm")
        if "recorded_times" in values:
            times = np.asarray(values["recorded_times"], dtype=h5py.string_dtype())
            field(acquisition, "recorded_local_times", times)
    if source.raw_metadata:
        _write_original_streams(entry, source.raw_metadata)
    return entry, data


def _required(target, fields):
    missing = [name for name, value in fields.items() if value is None]
    if missing:
        raise MissingRequiredMetadata(target, missing)


def _write_txrm(handle, source, angles, keys):
    entry, data = _entry(handle, source, "NXtomo")
    field(entry["sample"], "rotation_angle", angles, "deg").attrs["target"] = ROTATION
    field(entry["instrument/detector"], "image_key", keys).attrs["target"] = IMAGE_KEY
    data.attrs["axes"] = ["rotation_angle", ".", "."]
    size = source.values.get("pixel_size_um")
    if np.ndim(size) == 0 and size is not None and size > 0:
        calibration = nxgroup(
            entry["instrument/detector"], "object_sampling", "NXcollection"
        )
        field(calibration, "pixel_size", size, "um")


def map_txrm(source):
    """Use the primary tomography bundle and preserve references separately."""
    values = source.values
    n, (rows, columns) = source.frame_count, source.image_shape
    angles = np.atleast_1d(values.get("theta")) if "theta" in values else None
    if angles is not None and angles.shape != (n,):
        angles = None
    mode = values.get("acquisition_mode", "").casefold()
    keys = None
    if mode == "tomography":
        keys = np.zeros(n, dtype=np.int32)
        has_image = source.raw_metadata.get("ImageInfo/HasImage")
        if has_image is not None:
            if len(has_image) == n * 4:
                flags = np.frombuffer(has_image, dtype="<i4")
                if np.all(np.isin(flags, (0, 1))):
                    keys[flags == 0] = 3
                else:
                    keys = None
            else:
                keys = None
    _required(
        "NXtomo",
        {
            "sample/name": values.get("sample_name"),
            "sample/rotation_angle": angles,
            "instrument/detector/image_key": keys,
        },
    )
    if not np.issubdtype(source.dtype, np.integer):
        raise ValueError("NXtomo requires integer primary images")
    return ImageLayout(
        "NXtomo",
        (n, columns, rows),
        DETECTOR_DATA,
        0,
        {"interpretation": "image"},
        {
            "/entry/data/data": DETECTOR_DATA,
            "/entry/data/rotation_angle": ROTATION,
            "/entry/data/image_key": IMAGE_KEY,
        },
        partial(_write_txrm, source=source, angles=angles, keys=keys),
    )


def _write_txm(handle, source, title, axes):
    entry, data = _entry(handle, source, "NXtomoproc")
    field(entry, "title", title)
    data.attrs["axes"] = list("xyz")
    for name, axis in zip("xyz", axes, strict=True):
        field(data, name, axis, "um")
    process = nxgroup(entry, "reconstruction", "NXprocess")
    for name in ("program", "version", "date"):
        field(process, name, source.values[f"reconstruction_{name}"])
    field(
        nxgroup(process, "parameters", "NXparameters"),
        "raw_file",
        source.values["raw_file"],
    )


def map_txm(source):
    """Use volume-local coordinates and require positively identified process metadata."""
    values = source.values
    rows, columns = source.image_shape
    y = np.atleast_1d(values["slice_y_um"]) if "slice_y_um" in values else None
    spacing = values.get("pixel_size_um")
    if np.ndim(spacing) != 0 or spacing is None or spacing <= 0:
        spacing = None
    title = (
        PureWindowsPath(values["output_file"]).name
        if values.get("output_file")
        else None
    )
    # The audited TXM layout has no verified streams for the program, version,
    # or process date. exeVersion and the layer timestamps cannot substitute.
    _required(
        "NXtomoproc",
        {
            "title": title,
            "sample/name": values.get("sample_name"),
            "instrument/source/name": values.get("source_name"),
            "instrument/source/probe": values.get("probe"),
            "instrument/source/type": values.get("source_type"),
            "reconstruction/program": values.get("reconstruction_program"),
            "reconstruction/version": values.get("reconstruction_version"),
            "reconstruction/date": values.get("reconstruction_date"),
            "reconstruction/parameters/raw_file": values.get("raw_file"),
            "data/x": spacing,
            "data/y": y if y is not None and y.shape == (source.frame_count,) else None,
            "data/z": spacing,
        },
    )
    axes = (np.arange(columns) * spacing, y - y[0], np.arange(rows) * spacing)
    # Describe the unchanged stored grey values, with no physical rescaling.
    attributes = {
        "interpretation": "volume",
        "transform": "none",
        "offset": "0.0",
        "scaling": "1.0",
    }
    return ImageLayout(
        "NXtomoproc",
        (columns, source.frame_count, rows),
        "/entry/data/data",
        1,
        attributes,
        write_metadata=partial(_write_txm, source=source, title=title, axes=axes),
    )


def _write_xrm(handle, source):
    _, data = _entry(handle, source)
    size = source.values.get("pixel_size_um")
    if np.ndim(size) == 0 and size is not None and size > 0:
        data.attrs["axes"] = ["row", "column"]
        for name, length in zip(("row", "column"), source.image_shape, strict=True):
            field(data, name, np.arange(length) * size, "um")


def map_xrm(source):
    return ImageLayout(
        None,
        source.image_shape,
        DETECTOR_DATA,
        None,
        {"interpretation": "image"},
        {"/entry/data/data": DETECTOR_DATA},
        partial(_write_xrm, source=source),
    )


BINARY_MAPPINGS = {".txrm": map_txrm, ".txm": map_txm, ".xrm": map_xrm}
