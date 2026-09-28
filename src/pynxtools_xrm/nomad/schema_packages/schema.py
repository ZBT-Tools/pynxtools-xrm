"""ELN schema that executes the XRM streaming conversion in a NOMAD worker."""

from __future__ import annotations

from pathlib import Path

from nomad.datamodel import EntryArchive
from nomad.datamodel.data import EntryData
from nomad.metainfo import Package, Quantity

from pynxtools_xrm.models import CompressionConfig
from pynxtools_xrm.streaming_writer import convert_tomoproc

m_package = Package(name="pynxtools_xrm.schema")


def _safe_raw_path(raw_root: Path, relative: str, *, directory: bool) -> Path:
    candidate = (raw_root / relative).resolve()
    try:
        candidate.relative_to(raw_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Raw path escapes the NOMAD upload: {relative}") from exc
    if directory and not candidate.is_dir():
        raise NotADirectoryError(candidate)
    if not directory and not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


class XRMDataConverter(EntryData):
    """NOMAD ELN entry that creates and reparses a compressed NeXus file."""

    metadata_file = Quantity(
        type=str,
        description="eLabFTW JSON export containing the XRM metadata.",
        a_eln=dict(component="FileEditQuantity"),
        a_browser=dict(adaptor="RawFileAdaptor"),
    )
    tiff_directory = Quantity(
        type=str,
        description="Upload-relative directory containing numbered TIFF layers.",
        a_eln=dict(component="StringEditQuantity"),
    )
    output = Quantity(
        type=str,
        default="xrm_volume.nxs",
        description="Upload-relative output NXtomoproc filename.",
        a_eln=dict(component="StringEditQuantity"),
        a_browser=dict(adaptor="RawFileAdaptor"),
    )
    gzip_level = Quantity(
        type=int,
        default=4,
        description="Portable HDF5 gzip level (0..9).",
        a_eln=dict(component="NumberEditQuantity", minValue=0, maxValue=9),
    )
    target_chunk_mib = Quantity(
        type=float,
        default=1.0,
        description="Approximate maximum size of one HDF5 chunk in MiB.",
        a_eln=dict(component="NumberEditQuantity", minValue=0.01),
    )
    export = Quantity(
        type=bool,
        default=True,
        description="Run conversion automatically when the ELN entry is processed.",
        a_eln=dict(component="BoolEditQuantity"),
    )
    assumptions = Quantity(
        type=str,
        shape=["*"],
        description="Fallbacks applied because source metadata were unavailable.",
    )

    def normalize(self, archive: EntryArchive, logger) -> None:
        super().normalize(archive, logger)
        if not self.export:
            return
        if not self.metadata_file or not self.tiff_directory or not self.output:
            logger.warning(
                "XRM conversion skipped: metadata_file, tiff_directory and output "
                "must all be set."
            )
            return

        raw_root = Path(archive.m_context.raw_path()).resolve()
        metadata = _safe_raw_path(raw_root, self.metadata_file, directory=False)
        tiffs = _safe_raw_path(raw_root, self.tiff_directory, directory=True)
        output = (raw_root / self.output).resolve()
        try:
            output.relative_to(raw_root)
        except ValueError as exc:
            raise ValueError(f"Output escapes the NOMAD upload: {self.output}") from exc

        report = convert_tomoproc(
            metadata,
            tiffs,
            output,
            compression=CompressionConfig(
                level=int(self.gzip_level),
                target_chunk_bytes=max(
                    1, round(float(self.target_chunk_mib) * 1024 * 1024)
                ),
            ),
            overwrite=True,
        )
        self.assumptions = list(report.assumptions)
        archive.m_context.process_updated_raw_file(self.output, allow_modify=True)
        logger.info(
            "created streamed NXtomoproc file",
            output=self.output,
            shape=report.shape,
            chunks=report.chunks,
        )


m_package.__init_metainfo__()
