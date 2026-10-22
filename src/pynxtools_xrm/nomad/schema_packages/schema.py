"""Backward-compatible YAML adapter for the shared streaming service."""

from pathlib import Path

from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.metainfo import JSON, MEnum, Package, Quantity

from pynxtools_xrm.models import CompressionConfig
from pynxtools_xrm.nomad.jobs import output_relative, safe_raw_path
from pynxtools_xrm.streaming_writer import convert

m_package = Package(name="pynxtools_xrm.schema")
_safe_raw_path = safe_raw_path


class XRMDataConverter(EntryData):
    input_file = Quantity(type=str, a_eln=dict(component="FileEditQuantity"))
    metadata_file = Quantity(type=str, a_eln=dict(component="FileEditQuantity"))
    recipe_file = Quantity(type=str, a_eln=dict(component="FileEditQuantity"))
    tiff_directory = Quantity(type=str, a_eln=dict(component="StringEditQuantity"))
    target_definition = Quantity(
        type=MEnum("NXtomo", "NXtomoproc", "NXxrm_image"),
        a_eln=dict(component="EnumEditQuantity"),
    )
    metadata_supplements = Quantity(
        type=JSON,
        description="Explicit missing values only; never overrides image/RCP/ELN values.",
    )
    output = Quantity(
        type=str,
        a_eln=dict(component="StringEditQuantity"),
        a_browser=dict(adaptor="RawFileAdaptor"),
    )
    gzip_level = Quantity(
        type=int,
        default=4,
        a_eln=dict(component="NumberEditQuantity", minValue=0, maxValue=9),
    )
    target_chunk_mib = Quantity(
        type=float,
        default=1.0,
        a_eln=dict(component="NumberEditQuantity", minValue=0.01),
    )
    export = Quantity(type=bool, default=True, a_eln=dict(component="BoolEditQuantity"))
    assumptions = Quantity(
        type=str,
        shape=["*"],
        description="Legacy field; new conversions never fabricate required metadata.",
    )
    conversion_status = Quantity(type=str)
    nexus_view = Quantity(type=ArchiveSection, a_eln=dict(overview=True))

    def normalize(self, archive, logger):
        super().normalize(archive, logger)
        if not self.export:
            return
        root = Path(archive.m_context.raw_path()).resolve()
        if self.input_file:
            source = safe_raw_path(root, self.input_file)
            self.output = self.output or output_relative(source, root)
            # The binary mainfile is the single owner; it reads this YAML's options.
            archive.m_context.process_updated_raw_file(
                self.input_file, allow_modify=True
            )
            self.conversion_status = "requested"
            return
        if not self.tiff_directory:
            raise ValueError("Set input_file or tiff_directory")
        source = safe_raw_path(root, self.tiff_directory, directory=True)
        metadata = (
            safe_raw_path(root, self.metadata_file) if self.metadata_file else None
        )
        self.output = self.output or "xrm_volume.nxs"
        output = (root / self.output).resolve()
        if not output.is_relative_to(root):
            raise ValueError("Output escapes NOMAD upload")
        report = convert(
            source,
            output,
            target_definition=self.target_definition or "NXtomoproc",
            metadata_file=metadata,
            supplements=self.metadata_supplements,
            compression=CompressionConfig(
                level=int(self.gzip_level),
                target_chunk_bytes=round(float(self.target_chunk_mib) * 1024**2),
            ),
            overwrite=True,
        )
        if not report.reused:
            archive.m_context.process_updated_raw_file(self.output, allow_modify=True)
        self.nexus_view = f"../upload/archive/mainfile/{self.output}#/data"
        self.conversion_status = "reused" if report.reused else "converted"


m_package.__init_metainfo__()
