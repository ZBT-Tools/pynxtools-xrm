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

from pynxtools_xrm.metadata import json_value
from pynxtools_xrm.models import CompressionConfig, ConversionReport
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


def _validate_result(
    path, expected_shape, target="NXtomoproc", dataset_path="/entry/data/data"
):
    with h5py.File(path, "r") as h:
        data = h[dataset_path]
        if data.shape != expected_shape or data.compression != "gzip":
            raise RuntimeError("Written dataset violates shape/compression contract")
        if target == "NXtomo":
            if h["entry/sample/rotation_angle"].shape != (expected_shape[0],) or h[
                "entry/instrument/detector/image_key"
            ].shape != (expected_shape[0],):
                raise RuntimeError("NXtomo frame metadata dimensions disagree")
        if not validate_hdf_group_against(
            target, h["entry"], str(path), ignore_undocumented=True
        ):
            raise RuntimeError(f"NXDL validation failed for {target}")


def _identity(source, target, meta, compression, nxdl_path):
    paths = source.manifest.paths if isinstance(source, TiffSource) else (source.path,)
    stamps = [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths]
    payload = {
        "inputs": stamps,
        "target": target,
        "values": meta.values,
        "sources": meta.sources,
        "compression": asdict(compression),
        "nxdl_sha256": hashlib.sha256(Path(nxdl_path).read_bytes()).hexdigest(),
        "implementation": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(__file__).parent.glob("*.py")
        },
    }
    return hashlib.sha256(
        json.dumps(payload, default=json_value, sort_keys=True).encode()
    ).hexdigest(), stamps


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
    source = (
        TiffSource(discover_tiff_stack(input_path))
        if input_path.is_dir()
        else ZeissSource(input_path)
    )
    if isinstance(source, TiffSource) and output in source.manifest.paths:
        raise ValueError("Output aliases an input TIFF")
    compression = compression or CompressionConfig()
    compression.validate()
    reader = XRMReader()
    template = reader.read(
        template={},
        objects=(source,),
        streaming=True,
        target_definition=target_definition,
        metadata_file=metadata_file,
        recipe_paths=recipe_paths,
        supplements=supplements,
    )
    target, shape, dataset_path = reader.target, reader.shape, reader.dataset_path
    # Resolve before opening any output: absent custom definitions are an explicit setup error.
    _, nxdl_path = helpers.get_nxdl_root_and_path(target)
    identity, stamps = _identity(
        source, target, reader.metadata, compression, nxdl_path
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    chunks = _chunk_shape(
        shape,
        source.dtype,
        compression.target_chunk_bytes,
        1 if target == "NXtomoproc" else 0,
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
                    _validate_result(output, shape, target, dataset_path)
                    return replace(report, reused=True)
        descriptor, name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".part", dir=output.parent
        )
        os.close(descriptor)
        temporary = Path(name)
        try:
            # Writer removes unresolved links from its input template. Defer
            # pixel links until their streamed targets have been created.
            deferred_links = {
                path: value
                for path, value in template.items()
                if isinstance(value, dict) and set(value) == {"link"}
            }
            for path in deferred_links:
                del template[path]
            Writer(
                data=template, nxdl_f_path=nxdl_path, output_path=str(temporary)
            ).write()
            with h5py.File(temporary, "a") as h:
                h.attrs["file_name"] = output.name
                h.attrs["default"] = "entry"
                h.attrs["xrm_input_identity"] = identity
                h["entry"].attrs["default"] = (
                    "image" if target == "NXxrm_image" else "data"
                )
                if target == "NXxrm_image":
                    h["entry/image"].attrs["default"] = "image_2d"
                else:
                    h["entry/data"].attrs["signal"] = "data"
                parent, _, name = dataset_path.rpartition("/")
                dataset = h[parent].create_dataset(
                    name,
                    shape=shape,
                    dtype=source.dtype,
                    chunks=chunks,
                    compression="gzip",
                    compression_opts=compression.level,
                    shuffle=compression.shuffle,
                )
                dataset.attrs.update(
                    interpretation="volume" if target == "NXtomoproc" else "image"
                )
                dataset.attrs["target"] = dataset_path
                if target == "NXtomoproc":
                    dataset.attrs.update(transform="none", offset="0.0", scaling="1.0")
                    dataset.attrs["depends_on"] = "/entry/sample_frame"
                digest = hashlib.sha256()
                written = 0
                for i, frame in enumerate(source.iter_frames()):
                    if (
                        i >= source.frame_count
                        or frame.shape != source.image_shape
                        or frame.dtype != source.dtype
                    ):
                        raise ValueError("Frame changed after inspection")
                    digest.update(frame.tobytes(order="C"))
                    if target == "NXtomoproc":
                        dataset[:, i, :] = frame.T
                    elif target == "NXtomo":
                        dataset[i, :, :] = frame.T
                    else:
                        dataset[:, :] = frame
                    written += 1
                    if progress:
                        progress(i + 1, source.frame_count, source.path)
                if written != source.frame_count:
                    raise ValueError("Frame iterator ended early")
                dataset.attrs["source_frames_sha256"] = digest.hexdigest()
                # Core Writer cannot link a pixel dataset before it exists.
                # Resolve the same standard link instructions after streaming.
                for path, instruction in deferred_links.items():
                    link_path = helpers.convert_data_dict_path_to_hdf5_path(path)
                    if link_path not in h:
                        h[link_path] = h[instruction["link"]]
                for i, block in enumerate(source.auxiliary):
                    group = h[f"entry/auxiliary_{i}"]
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
                        shuffle=True,
                    )
                    for j, frame in enumerate(source.iter_frames(block)):
                        aux[j] = frame
                for filename, size, mtime in stamps:
                    st = Path(filename).stat()
                    if (st.st_size, st.st_mtime_ns) != (size, mtime):
                        raise ValueError(f"Input changed during conversion: {filename}")
                h.flush()
            _validate_result(temporary, shape, target, dataset_path)
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
