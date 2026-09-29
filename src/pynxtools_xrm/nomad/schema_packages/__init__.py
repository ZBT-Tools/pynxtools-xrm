"""NOMAD schema-package entry point for streamed XRM conversion."""

from importlib import import_module

from nomad.config.models.plugins import SchemaPackageEntryPoint


class XRMDataConverterEntryPoint(SchemaPackageEntryPoint):
    def load(self):
        schema = import_module("pynxtools_xrm.nomad.schema_packages.schema")
        return schema.m_package


xrm_data_converter = XRMDataConverterEntryPoint(
    name="XRM TIFF to NXtomoproc converter",
    description=(
        "Streams reconstructed TIFF layers into a compressed NXtomoproc file "
        "inside a NOMAD Oasis upload."
    ),
)
