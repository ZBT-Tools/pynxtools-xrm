"""Header validation and one-image-at-a-time access for reconstructed TIFFs."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import numpy as np
from PIL import Image, ImageMode

from pynxtools_xrm.models import TiffStackManifest

_INDEX_RE = re.compile(r"(\d+)$")


def _slice_index(path: Path) -> int:
    match = _INDEX_RE.search(path.stem)
    if match is None:
        raise ValueError(
            f"TIFF filename must end in a numeric layer index: {path.name}"
        )
    return int(match.group(1))


def discover_tiff_stack(directory: str | Path) -> TiffStackManifest:
    """Discover and validate TIFF headers without retaining image payloads."""

    directory = Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(f"TIFF directory does not exist: {directory}")

    paths = tuple(
        sorted(
            (*directory.glob("*.tif"), *directory.glob("*.tiff")),
            key=lambda path: (_slice_index(path), path.name.casefold()),
        )
    )
    if not paths:
        raise ValueError(f"No .tif or .tiff files found in {directory}")

    indices = tuple(_slice_index(path) for path in paths)
    if len(indices) != len(set(indices)):
        raise ValueError("Duplicate numeric TIFF layer indices were found.")
    expected = tuple(range(indices[0], indices[0] + len(indices)))
    if indices != expected:
        raise ValueError(
            "TIFF layer numbering is not contiguous: "
            f"expected {expected[0]}..{expected[-1]}, got "
            f"{indices[0]}..{indices[-1]}."
        )

    reference_shape: tuple[int, int] | None = None
    reference_dtype: np.dtype | None = None
    for path in paths:
        with Image.open(path) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError(f"Multi-page TIFF is not supported: {path}")
            shape = (image.height, image.width)
            # Mode metadata is sufficient here; np.asarray(image) would decode
            # every layer during what must remain a header-only validation pass.
            dtype = np.dtype(ImageMode.getmode(image.mode).typestr)
        if reference_shape is None:
            reference_shape, reference_dtype = shape, dtype
        elif shape != reference_shape or dtype != reference_dtype:
            raise ValueError(
                f"Inconsistent TIFF stack at {path.name}: shape={shape}, "
                f"dtype={dtype}; expected shape={reference_shape}, "
                f"dtype={reference_dtype}."
            )

    assert reference_shape is not None and reference_dtype is not None
    return TiffStackManifest(paths, reference_shape, reference_dtype, indices)


def iter_tiff_layers(manifest: TiffStackManifest) -> Iterator[np.ndarray]:
    """Yield one independent ``(z, x)`` array and close its file immediately."""

    for path in manifest.paths:
        with Image.open(path) as image:
            layer = np.asarray(image)
            if layer.shape != manifest.image_shape or layer.dtype != manifest.dtype:
                raise ValueError(f"TIFF changed after stack inspection: {path}")
            yield np.array(layer, copy=True)
