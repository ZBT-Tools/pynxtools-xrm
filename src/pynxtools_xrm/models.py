"""Small value objects used by the XRM conversion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class TiffStackManifest:
    """Validated description of a TIFF stack without its pixel payload."""

    paths: tuple[Path, ...]
    image_shape: tuple[int, int]
    dtype: np.dtype
    indices: tuple[int, ...]

    @property
    def volume_shape(self) -> tuple[int, int, int]:
        """Return NXtomoproc order ``(nX, nY, nZ)``."""

        n_z, n_x = self.image_shape
        return n_x, len(self.paths), n_z


@dataclass(frozen=True)
class CompressionConfig:
    """Portable HDF5 compression settings."""

    algorithm: str = "gzip"
    level: int = 4
    shuffle: bool = True
    target_chunk_bytes: int = 1024 * 1024

    def validate(self) -> None:
        if self.algorithm != "gzip":
            raise ValueError("Only the portable HDF5 gzip filter is supported.")
        if not 0 <= self.level <= 9:
            raise ValueError("gzip level must be between 0 and 9.")
        if self.target_chunk_bytes <= 0:
            raise ValueError("target_chunk_bytes must be positive.")


@dataclass(frozen=True)
class ConversionReport:
    """Information needed to audit a completed conversion."""

    output_path: Path
    shape: tuple[int, ...]
    dtype: str
    chunks: tuple[int, ...]
    compression: str
    compression_level: int
    slices_written: int
    assumptions: tuple[str, ...] = field(default_factory=tuple)
    reused: bool = False
