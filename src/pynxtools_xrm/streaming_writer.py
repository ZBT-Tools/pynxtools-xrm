"""Fixed-shape, chunked HDF5 writer for NXtomoproc volumes."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from pynxtools_xrm.models import CompressionConfig, ConversionReport
from pynxtools_xrm.reader import XRMReader
from pynxtools_xrm.tiff_stack import discover_tiff_stack, iter_tiff_layers

ProgressCallback = Callable[[int, int, Path], None]


def _chunk_shape(
    volume_shape: tuple[int, int, int], dtype: np.dtype, target_bytes: int
) -> tuple[int, int, int]:
    """Choose chunks aligned to a single Y layer and below the target size."""

    n_x, _, n_z = volume_shape
    chunk_x, chunk_z = n_x, n_z
    while chunk_x * chunk_z * dtype.itemsize > target_bytes:
        if chunk_z >= chunk_x and chunk_z > 1:
            chunk_z = (chunk_z + 1) // 2
        elif chunk_x > 1:
            chunk_x = (chunk_x + 1) // 2
        else:
            break
    return chunk_x, 1, chunk_z


def _template_value(template: Mapping[str, Any], path: str) -> Any:
    try:
        return template[path]
    except KeyError as exc:
        raise ValueError(f"Required reader value is missing: {path}") from exc


def _text(group: h5py.Group, name: str, value: Any) -> h5py.Dataset:
    return group.create_dataset(name, data=str(value), dtype=h5py.string_dtype("utf-8"))


def _write_metadata(
    handle: h5py.File, template: Mapping[str, Any], final_file_name: str
) -> h5py.Dataset:
    handle.attrs["default"] = "entry"
    handle.attrs["file_name"] = final_file_name
    handle.attrs["file_time"] = datetime.now(timezone.utc).isoformat()
    handle.attrs["HDF5_Version"] = h5py.version.hdf5_version
    handle.attrs["h5py_version"] = h5py.version.version

    entry = handle.create_group("entry")
    entry.attrs.update(NX_class="NXentry", default="data")
    _text(entry, "title", _template_value(template, "/ENTRY[entry]/title"))
    _text(entry, "definition", "NXtomoproc")

    instrument = entry.create_group("instrument")
    instrument.attrs["NX_class"] = "NXinstrument"
    source = instrument.create_group("source")
    source.attrs["NX_class"] = "NXsource"
    prefix = "/ENTRY[entry]/INSTRUMENT[instrument]/SOURCE[source]"
    for name in ("type", "name", "probe"):
        _text(source, name, _template_value(template, f"{prefix}/{name}"))

    sample = entry.create_group("sample")
    sample.attrs["NX_class"] = "NXsample"
    _text(
        sample,
        "name",
        _template_value(template, "/ENTRY[entry]/SAMPLE[sample]/name"),
    )

    reconstruction = entry.create_group("reconstruction")
    reconstruction.attrs["NX_class"] = "NXprocess"
    prefix = "/ENTRY[entry]/reconstruction"
    for name in ("program", "version", "date"):
        _text(reconstruction, name, _template_value(template, f"{prefix}/{name}"))
    parameters = reconstruction.create_group("parameters")
    parameters.attrs["NX_class"] = "NXparameters"
    _text(
        parameters,
        "raw_file",
        _template_value(template, f"{prefix}/parameters/raw_file"),
    )
    parameters_prefix = f"{prefix}/parameters/"
    for path, value in template.items():
        if path.startswith(parameters_prefix) and path != f"{parameters_prefix}raw_file":
            name = path.removeprefix(parameters_prefix)
            if "/" not in name and not name.startswith("@"):
                _text(parameters, name, value)

    data_group = entry.create_group("data")
    data_group.attrs["NX_class"] = "NXdata"
    data_group.attrs["signal"] = "data"
    data_group.attrs.create(
        "axes", np.asarray(["x", "y", "z"], dtype=h5py.string_dtype("utf-8"))
    )
    for position, axis_name in enumerate(("x", "y", "z"), start=1):
        axis_path = f"/ENTRY[entry]/data/{axis_name}"
        axis = data_group.create_dataset(axis_name, data=template[axis_path])
        axis.attrs["units"] = template[f"{axis_path}/@units"]
        axis.attrs["axis"] = position
    return data_group


def _validate_result(path: Path, expected_shape: tuple[int, int, int]) -> None:
    """Run structural checks that do not require loading the volume."""

    with h5py.File(path, "r") as handle:
        dataset = handle["/entry/data/data"]
        if dataset.shape != expected_shape:
            raise RuntimeError(
                f"Written shape {dataset.shape} does not match {expected_shape}."
            )
        if dataset.chunks is None or dataset.compression != "gzip":
            raise RuntimeError("Volume dataset is not chunked and gzip-compressed.")
        for required in (
            "/entry/title",
            "/entry/definition",
            "/entry/instrument/source/probe",
            "/entry/sample/name",
            "/entry/reconstruction/program",
            "/entry/reconstruction/version",
            "/entry/reconstruction/date",
            "/entry/reconstruction/parameters/raw_file",
            "/entry/data/x",
            "/entry/data/y",
            "/entry/data/z",
        ):
            if required not in handle:
                raise RuntimeError(f"Required NXtomoproc path is missing: {required}")


def convert_tomoproc(
    metadata_file: str | Path,
    tiff_directory: str | Path,
    output_file: str | Path,
    *,
    compression: CompressionConfig | None = None,
    overwrite: bool = False,
    progress: ProgressCallback | None = None,
) -> ConversionReport:
    """Convert a numbered TIFF stack without ever constructing a 3-D array."""

    metadata_file = Path(metadata_file).resolve()
    output_file = Path(output_file).resolve()
    manifest = discover_tiff_stack(tiff_directory)
    compression = compression or CompressionConfig()
    compression.validate()
    if output_file.exists() and not overwrite:
        raise FileExistsError(f"Output exists; pass overwrite=True: {output_file}")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_file.with_name(f".{output_file.name}.part")
    if temporary.exists():
        temporary.unlink()

    reader = XRMReader()
    template = reader.read(
        template={},
        file_paths=(str(metadata_file),),
        objects=(manifest,),
    )
    if reader.metadata is None:  # defensive: post_process already enforces this
        raise RuntimeError("Metadata reader did not return metadata.")
    chunks = _chunk_shape(
        manifest.volume_shape, manifest.dtype, compression.target_chunk_bytes
    )

    try:
        with h5py.File(temporary, "w") as handle:
            data_group = _write_metadata(handle, template, output_file.name)
            dataset = data_group.create_dataset(
                "data",
                shape=manifest.volume_shape,
                dtype=manifest.dtype,
                chunks=chunks,
                compression=compression.algorithm,
                compression_opts=compression.level,
                shuffle=compression.shuffle,
            )
            dataset.attrs.update(
                units="1",
                transform="none",
                offset=0.0,
                scaling=1.0,
                interpretation="volume",
            )
            total = len(manifest.paths)
            for y_index, (path, layer) in enumerate(
                zip(manifest.paths, iter_tiff_layers(manifest), strict=True)
            ):
                dataset[:, y_index, :] = layer.T
                if progress is not None:
                    progress(y_index + 1, total, path)
            handle.flush()
        _validate_result(temporary, manifest.volume_shape)
        os.replace(temporary, output_file)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise

    return ConversionReport(
        output_path=output_file,
        shape=manifest.volume_shape,
        dtype=str(manifest.dtype),
        chunks=chunks,
        compression=compression.algorithm,
        compression_level=compression.level,
        slices_written=len(manifest.paths),
        assumptions=reader.metadata.assumptions,
    )
