"""NOMAD mainfile registration is distinct from pynxtools reader discovery."""

from nomad.config.models.plugins import ParserEntryPoint


class XRMRawParserEntryPoint(ParserEntryPoint):
    def load(self):
        from pynxtools_xrm.nomad.parsers.parser import XRMRawParser  # noqa: PLC0415

        return XRMRawParser(**self.model_dump())


xrm_raw_parser = XRMRawParserEntryPoint(
    name="ZEISS XRM streaming converter",
    description="Convert individual TXRM, TXM and XRM mainfiles to separate NeXus files.",
    mainfile_name_re=r"(?i).*\.(txrm|txm|xrm)$",
    mainfile_mime_re=r".*",
    mainfile_binary_header=b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
)
