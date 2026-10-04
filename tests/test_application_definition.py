"""Checks for the packaged local NXtomoproc extension."""

from __future__ import annotations

from importlib.resources import files
from xml.etree import ElementTree


def test_local_application_definition_is_packaged_and_optional():
    definition = (
        files("pynxtools_xrm")
        / "definitions"
        / "applications"
        / "NXxrm_tomoproc.nxdl.xml"
    )
    root = ElementTree.parse(definition).getroot()
    namespace = {"nx": "http://definition.nexusformat.org/nxdl/3.1"}

    assert root.attrib["name"] == "NXxrm_tomoproc"
    assert root.attrib["extends"] == "NXtomoproc"
    optional = root.findall(".//*[@optional='true']", namespace)
    assert optional
    assert all(item.attrib["optional"] == "true" for item in optional)
