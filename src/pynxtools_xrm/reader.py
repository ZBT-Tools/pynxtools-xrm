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

    def read(
        self,
        template: dict | None = None,
        file_paths: tuple[str, ...] | None = None,
        objects: tuple[Any, ...] | None = None,
        **kwargs,
    ) -> dict:
        """Run only as the metadata phase of the dedicated streaming converter."""

        if not kwargs.pop("streaming", False):
            raise RuntimeError(
                "The XRM volume requires the dedicated streaming writer. "
                "Use 'pynx-xrm convert' or the NOMAD XRMDataConverter instead "
                "of standard 'pynx convert'."
            )
        return super().read(
            template=template,
            file_paths=file_paths,
            objects=objects,
            **kwargs,
        )

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
            "/ENTRY[entry]/definition_local": "NXxrm_tomoproc",
            "/ENTRY[entry]/INSTRUMENT[instrument]/name": meta.instrument_name,
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
        optional_values = {
            "/ENTRY[entry]/entry_identifier": meta.entry_identifier,
            "/ENTRY[entry]/experiment_identifier": meta.experiment_identifier,
            "/ENTRY[entry]/experiment_description": meta.experiment_description,
            "/ENTRY[entry]/start_time": meta.start_time,
            "/ENTRY[entry]/end_time": meta.end_time,
            "/ENTRY[entry]/SAMPLE[sample]/description": meta.sample_description,
            "/ENTRY[entry]/INSTRUMENT[instrument]/SOURCE[source]/distance": (
                meta.source_distance
            ),
            "/ENTRY[entry]/INSTRUMENT[instrument]/SOURCE[source]/distance/@units": (
                meta.source_distance_unit
            ),
            "/ENTRY[entry]/INSTRUMENT[instrument]/SOURCE[source]/power": (
                meta.source_power
            ),
            "/ENTRY[entry]/INSTRUMENT[instrument]/SOURCE[source]/power/@units": (
                meta.source_power_unit
            ),
            "/ENTRY[entry]/INSTRUMENT[instrument]/SOURCE[source]/voltage": (
                meta.source_voltage
            ),
            "/ENTRY[entry]/INSTRUMENT[instrument]/SOURCE[source]/voltage/@units": (
                meta.source_voltage_unit
            ),
            "/ENTRY[entry]/INSTRUMENT[instrument]/DETECTOR[detector]/distance": (
                meta.detector_distance
            ),
            "/ENTRY[entry]/INSTRUMENT[instrument]/DETECTOR[detector]/distance/@units": (
                meta.detector_distance_unit
            ),
            "/ENTRY[entry]/INSTRUMENT[instrument]/DETECTOR[detector]/count_time": (
                meta.detector_count_time
            ),
            "/ENTRY[entry]/INSTRUMENT[instrument]/DETECTOR[detector]/count_time/@units": (
                meta.detector_count_time_unit
            ),
        }
        result.update(
            {
                path: value
                for path, value in optional_values.items()
                if value is not None
            }
        )
        if meta.collection_time is not None:
            result["/ENTRY[entry]/collection_time"] = meta.collection_time.value
            if meta.collection_time.unit is not None:
                result["/ENTRY[entry]/collection_time/@units"] = (
                    meta.collection_time.unit
                )
        if meta.sample_temperature is not None:
            path = "/ENTRY[entry]/SAMPLE[sample]/temperature"
            result[path] = meta.sample_temperature.value
            if meta.sample_temperature.unit is not None:
                result[f"{path}/@units"] = meta.sample_temperature.unit
        for name, value in meta.sample_positioners.items():
            prefix = f"/ENTRY[entry]/SAMPLE[sample]/POSITIONER[{name}]"
            result[f"{prefix}/name"] = name
            result[f"{prefix}/value"] = value.value
            if value.unit is not None:
                result[f"{prefix}/value/@units"] = value.unit
        for user in meta.users:
            prefix = f"/ENTRY[entry]/USER[{user.group_name}]"
            result[f"{prefix}/name"] = user.name
            for name in ("role", "affiliation", "facility_user_id", "orcid"):
                value = getattr(user, name)
                if value is not None:
                    nexus_name = "ORCID" if name == "orcid" else name
                    result[f"{prefix}/{nexus_name}"] = value
        collections = {
            "/ENTRY[entry]/COLLECTION[acquisition]": meta.acquisition,
            "/ENTRY[entry]/COLLECTION[data_provenance]": meta.provenance,
            "/ENTRY[entry]/reconstruction/parameters": (meta.reconstruction_parameters),
        }
        for prefix, values in collections.items():
            for name, value in values.items():
                path = f"{prefix}/{name}"
                result[path] = value.value
                if value.unit is not None:
                    result[f"{path}/@units"] = value.unit
        note_values = {
            "/ENTRY[entry]/NOTE[notes]/data": meta.acquisition_note,
            "/ENTRY[entry]/SAMPLE[sample]/NOTE[preparation]/data": (
                meta.sample_preparation
            ),
            "/ENTRY[entry]/NOTE[elabftw]/date": meta.elabftw_created_at,
            "/ENTRY[entry]/NOTE[elabftw]/file_name": meta.elabftw_file_name,
        }
        result.update(
            {path: value for path, value in note_values.items() if value is not None}
        )
        return result


READER = XRMReader
