#
# Copyright The NOMAD Authors.
#
# This file is part of NOMAD. See https://nomad-lab.eu for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from pathlib import Path
from typing import Any

import numpy as np
from pynxtools.dataconverter.readers.multi.reader import MultiFormatReader

from pynxtools_xrm.metadata import XRMMetadata, read_elabftw_metadata
from pynxtools_xrm.models import TiffStackManifest
from pynxtools_xrm.tiff_stack import discover_tiff_stack


def centered_axis(length: int, spacing_um: float) -> np.ndarray:
    """Return coordinates whose geometric center is exactly zero."""

    return (np.arange(length, dtype=np.float64) - (length - 1) / 2) * spacing_um


class XRMReader(MultiFormatReader):
    """Collect small metadata while leaving the TIFF pixel stack on disk.

    The reader intentionally places no 3-D pixel array in the template. The
    companion streaming writer creates and fills that dataset afterwards.
    """

    supported_nxdls = ["NXtomoproc"]

    def __init__(self, config_file: str | None = None):
        super().__init__(config_file=config_file)
        self.metadata: XRMMetadata | None = None
        self.manifest: TiffStackManifest | None = None
        self.tiff_paths: list[Path] = []
        self.extensions = {
            ".json": self._handle_json,
            ".tif": self._handle_tiff,
            ".tiff": self._handle_tiff,
        }
        self.processing_order = [".json", ".tif", ".tiff"]

    def _handle_json(self, file_path: str) -> dict[str, Any]:
        self.metadata = read_elabftw_metadata(file_path)
        return {}

    def _handle_tiff(self, file_path: str) -> dict[str, Any]:
        self.tiff_paths.append(Path(file_path))
        return {}

    def handle_objects(self, objects: tuple[Any]) -> dict[str, Any]:
        for item in objects:
            if isinstance(item, TiffStackManifest):
                self.manifest = item
        return {}

    def post_process(self) -> dict[str, Any]:
        if self.manifest is None and self.tiff_paths:
            parents = {path.parent.resolve() for path in self.tiff_paths}
            if len(parents) != 1:
                raise ValueError("All TIFF inputs must belong to one directory.")
            self.manifest = discover_tiff_stack(parents.pop())
        if self.metadata is None:
            raise ValueError("Exactly one eLabFTW metadata JSON file is required.")
        if self.manifest is None:
            raise ValueError("A TIFF stack manifest or TIFF input is required.")

        n_x, n_y, n_z = self.manifest.volume_shape
        meta = self.metadata
        result: dict[str, Any] = {
            "/ENTRY[entry]/title": meta.title,
            "/ENTRY[entry]/definition": "NXtomoproc",
            "/ENTRY[entry]/INSTRUMENT[instrument]/SOURCE[source]/type": meta.source_type,
            "/ENTRY[entry]/INSTRUMENT[instrument]/SOURCE[source]/name": meta.source_name,
            "/ENTRY[entry]/INSTRUMENT[instrument]/SOURCE[source]/probe": "x-ray",
            "/ENTRY[entry]/SAMPLE[sample]/name": meta.sample_name,
            "/ENTRY[entry]/reconstruction/program": meta.reconstruction_program,
            "/ENTRY[entry]/reconstruction/version": meta.reconstruction_version,
            "/ENTRY[entry]/reconstruction/date": meta.reconstruction_date,
            "/ENTRY[entry]/reconstruction/parameters/raw_file": meta.raw_file,
            "/ENTRY[entry]/data/x": centered_axis(n_x, meta.voxel_size_um),
            "/ENTRY[entry]/data/x/@units": "um",
            "/ENTRY[entry]/data/y": centered_axis(n_y, meta.voxel_size_um),
            "/ENTRY[entry]/data/y/@units": "um",
            "/ENTRY[entry]/data/z": centered_axis(n_z, meta.voxel_size_um),
            "/ENTRY[entry]/data/z/@units": "um",
        }
        for name, value in meta.parameters.items():
            safe_name = name.casefold().replace(" ", "_").replace("/", "_")
            result[f"/ENTRY[entry]/reconstruction/parameters/{safe_name}"] = value
        return result


READER = XRMReader
