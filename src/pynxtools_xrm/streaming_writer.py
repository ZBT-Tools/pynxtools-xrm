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


def _optional_value(template: Mapping[str, Any], path: str) -> Any | None:
    return template.get(path)


def _number_with_unit(
    group: h5py.Group,
    name: str,
    value: float,
    unit: str | None,
) -> h5py.Dataset:
    dataset = group.create_dataset(name, data=value)
    if unit is not None:
        dataset.attrs["units"] = unit
    return dataset


def _scalar_with_unit(
    group: h5py.Group,
    name: str,
    value: Any,
    unit: str | None = None,
) -> h5py.Dataset:
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, bool
    ):
        return _number_with_unit(group, name, value, unit)
    dataset = _text(group, name, value)
    if unit is not None:
        dataset.attrs["units"] = unit
    return dataset


def _write_template_fields(
    group: h5py.Group,
    template: Mapping[str, Any],
    prefix: str,
    *,
    exclude: set[str] | None = None,
) -> dict[str, h5py.Dataset]:
    """Write direct children below a template prefix, preserving scalar types."""

    datasets: dict[str, h5py.Dataset] = {}
    exclude = exclude or set()
    for path, value in template.items():
        if not path.startswith(f"{prefix}/") or path.endswith("/@units"):
            continue
        name = path.removeprefix(f"{prefix}/")
        if "/" in name or name.startswith("@") or name in exclude:
            continue
        datasets[name] = _scalar_with_unit(
            group, name, value, template.get(f"{path}/@units")
        )
    return datasets


def _write_note(
    parent: h5py.Group,
    name: str,
    template: Mapping[str, Any],
    prefix: str,
    *,
    author: h5py.Dataset | None = None,
) -> h5py.Group | None:
    fields = {
        field: template.get(f"{prefix}/{field}")
        for field in ("date", "file_name", "description", "data")
    }
    if not any(value is not None for value in fields.values()):
        return None
    note = parent.create_group(name)
    note.attrs["NX_class"] = "NXnote"
    if author is not None:
        note["author"] = author
    for field, value in fields.items():
        if value is not None:
            if field == "data":
                note.create_dataset(field, data=np.bytes_(str(value).encode("utf-8")))
            else:
                _text(note, field, value)
    if fields["data"] is not None:
        _text(note, "type", "text/plain")
    return note


def _write_optional_number(
    group: h5py.Group,
    template: Mapping[str, Any],
    path: str,
) -> None:
    value = _optional_value(template, path)
    if value is not None:
        _number_with_unit(
            group, path.rsplit("/", 1)[-1], value, template.get(f"{path}/@units")
        )


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
    definition_local = _text(entry, "definition_local", "NXxrm_tomoproc")
    definition_local.attrs["URL"] = (
        "https://github.com/FAIRmat-NFDI/pynxtools-xrm/blob/main/"
        "src/pynxtools_xrm/definitions/applications/NXxrm_tomoproc.nxdl.xml"
    )
    entry_identifier = None
    for name in (
        "entry_identifier",
        "experiment_identifier",
        "experiment_description",
        "start_time",
        "end_time",
    ):
        value = _optional_value(template, f"/ENTRY[entry]/{name}")
        if value is not None:
            dataset = _text(entry, name, value)
            if name == "entry_identifier":
                entry_identifier = dataset
    collection_time = _optional_value(template, "/ENTRY[entry]/collection_time")
    if collection_time is not None:
        _number_with_unit(
            entry,
            "collection_time",
            collection_time,
            template.get("/ENTRY[entry]/collection_time/@units"),
        )

    instrument = entry.create_group("instrument")
    instrument.attrs["NX_class"] = "NXinstrument"
    instrument_prefix = "/ENTRY[entry]/INSTRUMENT[instrument]"
    instrument_name_value = _template_value(template, f"{instrument_prefix}/name")
    instrument_name = _text(instrument, "name", instrument_name_value)
    source = instrument.create_group("source")
    source.attrs["NX_class"] = "NXsource"
    prefix = "/ENTRY[entry]/INSTRUMENT[instrument]/SOURCE[source]"
    for name in ("type", "probe"):
        _text(source, name, _template_value(template, f"{prefix}/{name}"))
    source_name = _template_value(template, f"{prefix}/name")
    if str(source_name) == str(instrument_name_value):
        source["name"] = instrument_name
    else:
        _text(source, "name", source_name)
    for name in ("distance", "power", "voltage"):
        _write_optional_number(source, template, f"{prefix}/{name}")

    detector = instrument.create_group("detector")
    detector.attrs["NX_class"] = "NXdetector"
    _text(detector, "layout", "area")
    prefix = f"{instrument_prefix}/DETECTOR[detector]"
    for name in ("distance", "count_time"):
        _write_optional_number(detector, template, f"{prefix}/{name}")

    sample = entry.create_group("sample")
    sample.attrs["NX_class"] = "NXsample"
    _text(
        sample,
        "name",
        _template_value(template, "/ENTRY[entry]/SAMPLE[sample]/name"),
    )
    _text(sample, "type", "sample")
    sample_description = _optional_value(
        template, "/ENTRY[entry]/SAMPLE[sample]/description"
    )
    if sample_description is not None:
        _text(sample, "description", sample_description)
    _write_optional_number(sample, template, "/ENTRY[entry]/SAMPLE[sample]/temperature")
    for name in ("stage_x", "stage_y", "stage_z"):
        prefix = f"/ENTRY[entry]/SAMPLE[sample]/POSITIONER[{name}]"
        value = _optional_value(template, f"{prefix}/value")
        if value is None:
            continue
        positioner = sample.create_group(name)
        positioner.attrs["NX_class"] = "NXpositioner"
        _text(positioner, "name", _template_value(template, f"{prefix}/name"))
        _number_with_unit(
            positioner,
            "value",
            value,
            template.get(f"{prefix}/value/@units"),
        )

    user_name_datasets: dict[str, h5py.Dataset] = {}
    for group_name in ("user", "experimenter", "owner"):
        prefix = f"/ENTRY[entry]/USER[{group_name}]"
        user_name = _optional_value(template, f"{prefix}/name")
        if user_name is None:
            continue
        user = entry.create_group(group_name)
        user.attrs["NX_class"] = "NXuser"
        user_name_datasets[group_name] = _text(user, "name", user_name)
        for name in ("role", "affiliation", "facility_user_id", "ORCID"):
            value = _optional_value(template, f"{prefix}/{name}")
            if value is not None:
                _text(user, name, value)

    reconstruction = entry.create_group("reconstruction")
    reconstruction.attrs["NX_class"] = "NXprocess"
    prefix = "/ENTRY[entry]/reconstruction"
    for name in ("program", "version", "date"):
        _text(reconstruction, name, _template_value(template, f"{prefix}/{name}"))
    parameters = reconstruction.create_group("parameters")
    parameters.attrs["NX_class"] = "NXparameters"
    raw_file = _text(
        parameters,
        "raw_file",
        _template_value(template, f"{prefix}/parameters/raw_file"),
    )
    parameters_prefix = f"{prefix}/parameters/"
    _write_template_fields(
        parameters,
        template,
        parameters_prefix.rstrip("/"),
        exclude={"raw_file"},
    )

    acquisition = entry.create_group("acquisition")
    acquisition.attrs["NX_class"] = "NXcollection"
    _write_template_fields(
        acquisition, template, "/ENTRY[entry]/COLLECTION[acquisition]"
    )

    provenance = entry.create_group("data_provenance")
    provenance.attrs["NX_class"] = "NXcollection"
    provenance_prefix = "/ENTRY[entry]/COLLECTION[data_provenance]"
    path_datasets: dict[str, h5py.Dataset] = {str(raw_file.asstr()[()]): raw_file}
    for name in (
        "raw_data_path",
        "reconstruction_path",
        "analysis_path",
        "results_storage_path",
    ):
        value = _optional_value(template, f"{provenance_prefix}/{name}")
        if value is None:
            continue
        key = str(value)
        if key in path_datasets:
            provenance[name] = path_datasets[key]
        else:
            path_datasets[key] = _text(provenance, name, value)
    _write_template_fields(
        provenance,
        template,
        provenance_prefix,
        exclude={
            "raw_data_path",
            "reconstruction_path",
            "analysis_path",
            "results_storage_path",
        },
    )

    author = user_name_datasets.get("user")
    _write_note(
        entry,
        "notes",
        template,
        "/ENTRY[entry]/NOTE[notes]",
        author=author,
    )
    _write_note(
        sample,
        "preparation",
        template,
        "/ENTRY[entry]/SAMPLE[sample]/NOTE[preparation]",
        author=author,
    )
    elabftw = _write_note(
        entry,
        "elabftw",
        template,
        "/ENTRY[entry]/NOTE[elabftw]",
        author=author,
    )
    if elabftw is not None and entry_identifier is not None:
        elabftw["identifier_elabftw"] = entry_identifier

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
            "/entry/instrument/detector",
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
        streaming=True,
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
                offset="0.0",
                scaling="1.0",
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
