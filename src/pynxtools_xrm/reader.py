"""pynxtools metadata reader shared by the streaming entry points."""

from pathlib import Path

import numpy as np
from pynxtools.dataconverter.readers.multi.reader import MultiFormatReader

from pynxtools_xrm.mapping import build_template
from pynxtools_xrm.metadata import resolve_metadata
from pynxtools_xrm.models import TiffStackManifest
from pynxtools_xrm.tiff_stack import TiffSource, discover_tiff_stack
from pynxtools_xrm.zeiss import ZeissSource, associate_recipe, read_recipe


def centered_axis(length, spacing_um):
    """Local coordinates only; no assertion about the stage origin."""
    return (np.arange(length, dtype=float) - (length - 1) / 2) * spacing_um


class XRMReader(MultiFormatReader):
    supported_nxdls = ["NXtomo", "NXtomoproc", "NXxrm_image"]
    conversion_capabilities = {
        "standard_writer": False,
        "streaming_writer": "pynxtools_xrm.streaming_writer:convert",
        "cli": "pynx-xrm convert",
    }

    def __init__(self, config_file=None):
        super().__init__(config_file=config_file)
        self.extensions = {
            ext: self._handle_file
            for ext in (".json", ".rcp", ".txrm", ".txm", ".xrm", ".tif", ".tiff")
        }
        self.processing_order = list(self.extensions)

    def _handle_file(self, path):
        self.inputs.append(Path(path))
        return {}

    def handle_objects(self, objects):
        for obj in objects:
            if isinstance(obj, TiffStackManifest):
                self.source = TiffSource(obj)
            elif isinstance(obj, (ZeissSource, TiffSource)):
                self.source = obj
        return {}

    def read(self, template=None, file_paths=None, objects=None, **kwargs):
        if not kwargs.pop("streaming", False):
            raise RuntimeError(
                "Large images require the streaming adapter; use pynx-xrm convert or XRMDataConverter"
            )
        self.inputs, self.source, self.metadata = [], None, None
        self.target = kwargs.pop("target_definition", None)
        self.supplements = kwargs.pop("supplements", None)
        self.metadata_file = kwargs.pop("metadata_file", None)
        self.recipe_paths = kwargs.pop("recipe_paths", ())
        # Source objects avoid re-inspection and preserve original path casing.
        return super().read(
            template=template,
            file_paths=file_paths or (),
            objects=objects or (),
            **kwargs,
        )

    def post_process(self):
        images = [
            p for p in self.inputs if p.suffix.casefold() in {".txrm", ".txm", ".xrm"}
        ]
        jsons = [p for p in self.inputs if p.suffix.casefold() == ".json"]
        recipes = [p for p in self.inputs if p.suffix.casefold() == ".rcp"] + list(
            self.recipe_paths
        )
        if len(images) > 1 or len(jsons) > 1:
            raise ValueError(
                "Exactly one image dataset and at most one assigned eLabFTW JSON per conversion are supported"
            )
        if self.source is None:
            if images:
                self.source = ZeissSource(images[0])
            else:
                tiffs = [
                    p for p in self.inputs if p.suffix.casefold() in {".tif", ".tiff"}
                ]
                if not tiffs or len({p.parent.resolve() for p in tiffs}) != 1:
                    raise ValueError("One image source or TIFF manifest is required")
                self.source = TiffSource(discover_tiff_stack(tiffs[0].parent))
        self.target = (
            self.target
            or {
                ".txrm": "NXtomo",
                ".txm": "NXtomoproc",
                ".xrm": "NXxrm_image",
                ".tiff": "NXtomoproc",
            }[self.source.kind]
        )
        if (
            self.source.kind != ".tiff"
            and self.target
            != {".txrm": "NXtomo", ".txm": "NXtomoproc", ".xrm": "NXxrm_image"}[
                self.source.kind
            ]
        ):
            raise ValueError("ZEISS file extension and target definition disagree")
        if self.source.kind == ".tiff" and self.target not in {"NXtomo", "NXtomoproc"}:
            raise ValueError("TIFF stacks require NXtomo or NXtomoproc")
        match = (
            associate_recipe(self.source, [read_recipe(p) for p in recipes])
            if recipes and self.source.kind != ".tiff"
            else None
        )
        if recipes and match is None:
            raise ValueError(
                "Provided RCP is not unambiguously associated with this image source"
            )
        self.metadata = resolve_metadata(
            self.source,
            recipe_match=match,
            metadata_file=self.metadata_file or (jsons[0] if jsons else None),
            supplements=self.supplements,
            target=self.target,
        )
        result, self.shape, self.dataset_path = build_template(
            self.source, self.metadata, self.target
        )
        for i, block in enumerate(self.source.auxiliary):
            prefix = f"/ENTRY[entry]/DATA[auxiliary_{i}]"
            result[prefix + "/title"] = block.name
            result[prefix + "/@signal"] = "data"
        return result


READER = XRMReader
