"""pynxtools metadata adapter for TIFF stacks and their sidecars."""

from pathlib import Path

import numpy as np
from pynxtools.dataconverter.readers.multi.reader import MultiFormatReader

from pynxtools_xrm.mapping import build_template
from pynxtools_xrm.metadata import resolve_metadata
from pynxtools_xrm.models import TiffStackManifest
from pynxtools_xrm.tiff_stack import TiffSource, discover_tiff_stack


def centered_axis(length, spacing_um):
    """Local coordinates only; no assertion about the stage origin."""
    return (np.arange(length, dtype=float) - (length - 1) / 2) * spacing_um


class XRMReader(MultiFormatReader):
    supported_nxdls = ["NXtomo", "NXtomoproc"]
    conversion_capabilities = {
        "standard_writer": False,
        "streaming_writer": "pynxtools_xrm.streaming_writer:convert",
        "cli": "pynx-xrm convert",
    }

    def __init__(self, config_file=None):
        super().__init__(config_file=config_file)
        self.extensions = {ext: self._handle_file for ext in (".json", ".tif", ".tiff")}
        self.processing_order = list(self.extensions)

    def _handle_file(self, path):
        self.inputs.append(Path(path))
        return {}

    def handle_objects(self, objects):
        for obj in objects:
            if isinstance(obj, TiffStackManifest):
                self.source = TiffSource(obj)
            elif isinstance(obj, TiffSource):
                self.source = obj
        return {}

    def read(self, template=None, file_paths=None, objects=None, **kwargs):
        if not kwargs.pop("streaming", False):
            raise RuntimeError(
                "Large images require the streaming adapter; use pynx-xrm convert or XRMDataConverter"
            )
        self.inputs, self.source, self.metadata = [], None, None
        self.target = kwargs.pop("target_definition", None) or "NXtomoproc"
        self.supplements = kwargs.pop("supplements", None)
        self.metadata_file = kwargs.pop("metadata_file", None)
        return super().read(
            template=template,
            file_paths=file_paths or (),
            objects=objects or (),
            **kwargs,
        )

    def post_process(self):
        jsons = [p for p in self.inputs if p.suffix.casefold() == ".json"]
        if len(jsons) > 1:
            raise ValueError(
                "At most one eLabFTW JSON per TIFF conversion is supported"
            )
        if self.source is None:
            tiffs = [p for p in self.inputs if p.suffix.casefold() in {".tif", ".tiff"}]
            if not tiffs or len({p.parent.resolve() for p in tiffs}) != 1:
                raise ValueError("One TIFF directory or manifest is required")
            self.source = TiffSource(discover_tiff_stack(tiffs[0].parent))
        if self.target not in self.supported_nxdls:
            raise ValueError("TIFF stacks require NXtomo or NXtomoproc")
        self.metadata = resolve_metadata(
            self.source,
            metadata_file=self.metadata_file or (jsons[0] if jsons else None),
            supplements=self.supplements,
            target=self.target,
        )
        result, self.shape, self.dataset_path = build_template(
            self.source, self.metadata, self.target
        )
        return result


READER = XRMReader
