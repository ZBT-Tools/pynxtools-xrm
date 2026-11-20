"""One atomic conversion lifecycle, standard metadata Writer and frame streaming."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path

import h5py
import numpy as np
from pynxtools.dataconverter import helpers
from pynxtools.dataconverter.validate_file import validate_hdf_group_against
from pynxtools.dataconverter.writer import Writer

from pynxtools_xrm.binary_mapping import BINARY_MAPPINGS, nxgroup
from pynxtools_xrm.metadata import json_value
from pynxtools_xrm.models import CompressionConfig, ConversionReport, ImageLayout
from pynxtools_xrm.reader import XRMReader
from pynxtools_xrm.tiff_stack import TiffSource, discover_tiff_stack
from pynxtools_xrm.zeiss import ZeissSource


@contextmanager
def _exclusive_output_lock(output_file):
    lock = output_file.with_name(f".{output_file.name}.lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(
            f"Another XRM conversion is targeting {output_file}"
        ) from exc
    try:
        os.close(descriptor)
        yield
    finally:
        lock.unlink(missing_ok=True)


def _chunk_shape(shape, dtype, target_bytes, stream_axis=0):
    chunks = list(shape)
    if len(chunks) == 3:
        chunks[stream_axis] = 1
    while np.prod(chunks) * np.dtype(dtype).itemsize > target_bytes:
        axis = max(range(len(chunks)), key=lambda i: chunks[i])
        chunks[axis] = max(1, (chunks[axis] + 1) // 2)
    return tuple(chunks)


def _validate_result(path, layout):
    with h5py.File(path, "r") as h:
        data = h[layout.path]
        if data.shape != layout.shape or data.compression != "gzip":
            raise RuntimeError("Written dataset violates shape/compression contract")
        target = layout.definition
        if target == "NXtomo":
            if h["entry/sample/rotation_angle"].shape != (layout.shape[0],) or h[
                "entry/instrument/detector/image_key"
            ].shape != (layout.shape[0],):
                raise RuntimeError("NXtomo frame metadata dimensions disagree")
        if target is None:
            view = h["entry/data"]
            if (
                view.attrs["NX_class"] != "NXdata"
                or view[view.attrs["signal"]].id != data.id
            ):
                raise RuntimeError("XRM image is missing its NXdata signal link")
        elif not validate_hdf_group_against(
            target, h["entry"], str(path), ignore_undocumented=True
        ):
            raise RuntimeError(f"NXDL validation failed for {target}")


def _identity(source, target, meta, compression, nxdl_path):
    paths = source.manifest.paths if isinstance(source, TiffSource) else (source.path,)
    stamps = [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths]
    payload = {
        "inputs": stamps,
        "target": target,
        "values": meta.values if meta is not None else None,
        "sources": meta.sources if meta is not None else None,
        "compression": asdict(compression),
        "nxdl_sha256": hashlib.sha256(Path(nxdl_path).read_bytes()).hexdigest()
        if nxdl_path
        else None,
        "implementation": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(__file__).parent.glob("*.py")
        },
    }
    return hashlib.sha256(
        json.dumps(payload, default=json_value, sort_keys=True).encode()
    ).hexdigest(), stamps


def _tiff_layout(source, target_definition, metadata_file, supplements):
    """Adapt the existing TIFF/ELN reader to the shared image writer."""
    reader = XRMReader()
    template = reader.read(
        template={},
        objects=(source,),
        streaming=True,
        target_definition=target_definition,
        metadata_file=metadata_file,
        supplements=supplements,
    )
    links = {}
    for path, value in list(template.items()):
        if isinstance(value, dict) and set(value) == {"link"}:
            links[helpers.convert_data_dict_path_to_hdf5_path(path)] = value["link"]
            del template[path]
    volume = reader.target == "NXtomoproc"
    attributes = {"interpretation": "volume" if volume else "image"}
    if volume:
        attributes.update(
            transform="none",
            offset="0.0",
            scaling="1.0",
            depends_on="/entry/sample_frame",
        )
    layout = ImageLayout(
        reader.target, reader.shape, reader.dataset_path, int(volume), attributes, links
    )
    return layout, reader.metadata, template


def _write_frames(dataset, source, axis, progress):
    digest = hashlib.sha256()
    written = 0
    for index, frame in enumerate(source.iter_frames()):
        if (
            index >= source.frame_count
            or frame.shape != source.image_shape
            or frame.dtype != source.dtype
        ):
            raise ValueError("Frame changed after inspection")
        digest.update(frame.tobytes(order="C"))
        if axis is None:
            dataset[...] = frame
        else:
            selection = [slice(None)] * dataset.ndim
            selection[axis] = index
            dataset[tuple(selection)] = frame.T
        written += 1
        if progress:
            progress(written, source.frame_count, source.path)
    if written != source.frame_count:
        raise ValueError("Frame iterator ended early")
    dataset.attrs["source_frames_sha256"] = digest.hexdigest()


def convert(
    input_path,
    output_file,
    *,
    target_definition=None,
    metadata_file=None,
    recipe_paths=(),
    supplements=None,
    compression=None,
    overwrite=False,
    progress=None,
):
    input_path, output = Path(input_path).resolve(), Path(output_file).resolve()
    if output.suffix.casefold() != ".nxs" or output == input_path:
        raise ValueError("Output must be a separate .nxs file")
    compression = compression or CompressionConfig()
    compression.validate()
    if recipe_paths:
        raise ValueError("RCP files are available for inspection, not conversion")
    if input_path.is_dir():
        source = TiffSource(discover_tiff_stack(input_path))
        if output in source.manifest.paths:
            raise ValueError("Output aliases an input TIFF")
        layout, metadata, template = _tiff_layout(
            source, target_definition, metadata_file, supplements
        )
    else:
        if metadata_file is not None or supplements is not None:
            raise ValueError(
                "ZEISS conversion accepts only metadata embedded in the input file"
            )
        source = ZeissSource(input_path)
        layout = BINARY_MAPPINGS[source.kind](source)
        if target_definition is not None and target_definition != layout.definition:
            raise ValueError("ZEISS file extension and target definition disagree")
        metadata = template = None
    target, shape = layout.definition, layout.shape
    nxdl_path = helpers.get_nxdl_root_and_path(target)[1] if target else None
    identity, stamps = _identity(source, target, metadata, compression, nxdl_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    chunks = _chunk_shape(
        shape,
        source.dtype,
        compression.target_chunk_bytes,
        layout.frame_axis or 0,
    )
    report = ConversionReport(
        output,
        shape,
        str(source.dtype),
        chunks,
        compression.algorithm,
        compression.level,
        source.frame_count,
    )
    with _exclusive_output_lock(output):
        if output.exists():
            if not overwrite:
                raise FileExistsError(output)
            with h5py.File(output, "r") as existing:
                if existing.attrs.get("xrm_input_identity") == identity:
                    _validate_result(output, layout)
                    return replace(report, reused=True)
        descriptor, name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".part", dir=output.parent
        )
        os.close(descriptor)
        temporary = Path(name)
        try:
            if template is not None:
                Writer(
                    data=template, nxdl_f_path=nxdl_path, output_path=str(temporary)
                ).write()
            with h5py.File(temporary, "a") as h:
                if layout.write_metadata is not None:
                    layout.write_metadata(h)
                h.attrs["file_name"] = output.name
                h.attrs["default"] = "entry"
                h.attrs["xrm_input_identity"] = identity
                h["entry"].attrs["default"] = "data"
                h["entry/data"].attrs["signal"] = "data"
                parent, _, name = layout.path.rpartition("/")
                dataset = h[parent].create_dataset(
                    name,
                    shape=shape,
                    dtype=source.dtype,
                    chunks=chunks,
                    compression="gzip",
                    compression_opts=compression.level,
                    shuffle=compression.shuffle,
                )
                dataset.attrs.update(layout.attributes)
                dataset.attrs["target"] = layout.path
                _write_frames(dataset, source, layout.frame_axis, progress)
                for path, destination in layout.links.items():
                    if path not in h:
                        h[path] = h[destination]
                for i, block in enumerate(source.auxiliary):
                    group = nxgroup(h["entry"], f"auxiliary_{i}", "NXdata")
                    group.attrs["signal"] = "data"
                    group.create_dataset("title", data=block.name)
                    group.create_dataset(
                        "original_streams",
                        data=np.asarray(block.streams, dtype=h5py.string_dtype()),
                    )
                    aux_shape = (len(block.streams), *block.shape)
                    aux = group.create_dataset(
                        "data",
                        shape=aux_shape,
                        dtype=block.dtype,
                        chunks=_chunk_shape(
                            aux_shape, block.dtype, compression.target_chunk_bytes
                        ),
                        compression="gzip",
                        compression_opts=compression.level,
                        shuffle=compression.shuffle,
                    )
                    for j, frame in enumerate(source.iter_frames(block)):
                        aux[j] = frame
                for filename, size, mtime in stamps:
                    st = Path(filename).stat()
                    if (st.st_size, st.st_mtime_ns) != (size, mtime):
                        raise ValueError(f"Input changed during conversion: {filename}")
                h.flush()
            _validate_result(temporary, layout)
            os.replace(temporary, output)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    return report


def convert_tomoproc(metadata_file, tiff_directory, output_file, **kwargs):
    """Compatibility wrapper; missing required metadata now fails explicitly."""
    return convert(
        tiff_directory,
        output_file,
        target_definition="NXtomoproc",
        metadata_file=metadata_file,
        **kwargs,
    )
