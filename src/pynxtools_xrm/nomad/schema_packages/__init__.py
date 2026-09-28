"""NOMAD schema-package entry point for streamed XRM conversion."""

from nomad.config.models.plugins import SchemaPackageEntryPoint


class XRMDataConverterEntryPoint(SchemaPackageEntryPoint):
    def load(self):
        # NOMAD schema entry points are intentionally lazy-loaded here.
        from pynxtools_xrm.nomad.schema_packages.schema import m_package  # noqa: PLC0415

        return m_package


xrm_data_converter = XRMDataConverterEntryPoint(
    name="XRM TIFF to NXtomoproc converter",
    description=(
        "Streams reconstructed TIFF layers into a compressed NXtomoproc file "
        "inside a NOMAD Oasis upload."
    ),
)
