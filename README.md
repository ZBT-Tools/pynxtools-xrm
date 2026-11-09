# pynxtools-xrm

Streaming conversion of ZEISS TXRM, TXM, XRM and numbered grayscale TIFF stacks
to NeXus, with automatic file parsing and YAML configuration in NOMAD Oasis.

Developed at **ZBT – Zentrum für BrennstoffzellenTechnik GmbH** by
**Jonas Fortmann**, [j.formtann@zbt.de](mailto:j.formtann@zbt.de).
This is an independently maintained ZBT community plugin for the NOMAD/FAIRmat
ecosystem. NOMAD and pynxtools are upstream dependencies with their own authors.

| Input | Output application | NOMAD trigger |
|---|---|---|
| `.txrm` | `NXtomo` projection series | Automatic binary parser |
| `.txm` | `NXtomoproc` reconstructed volume | Automatic binary parser |
| `.xrm` (one image) | Local `NXxrm_image` | Automatic binary parser |
| Numbered `.tif` / `.tiff` files | `NXtomoproc` or `NXtomo` | `*.archive.yaml` |
| `.rcp`, eLabFTW JSON | Associated metadata | Used by the image conversion |

## Installation and definitions

Python >=3.10 is declared by the package; Python 3.12 is the documented setup.
The supported pynxtools dependency is `>=0.15.2,<0.16`. NOMAD 2.0.0 Oasis is the
deployment addressed here; installation alone does not establish compatibility
with every NOMAD/parser combination.

From a checkout, in the intended Python environment:

```bash
python -m pip install -e .
pynx-xrm definitions --output /absolute/path/xrm-definitions
export NEXUS_DEF_PATH=/absolute/path/xrm-definitions
```

Set the variable **before starting Python, the NOMAD app and every worker**.
For Oasis, install the plugin in those environments and persist the variable in
their service/container configuration. Installing only on the host is insufficient.
Follow the [file-by-file Oasis deployment guide](docs/howto/oasis-deployment.md).

## First conversion

```bash
pynx-xrm inspect acquisition.txrm
pynx-xrm inspect recipe.rcp
pynx-xrm convert --input acquisition.txrm --recipe recipe.rcp --output acquisition.nxs
```

These commands require valid source files and complete metadata. Add an exported
eLabFTW JSON using `--metadata metadata.json`, and explicit missing values using
`--supplements missing-values.json`. Standard `pynx convert --reader xrm` is not
the supported pixel-writing entry point; use `pynx-xrm convert`.

## NOMAD uploads

Upload the original directory tree, associated RCP and eLabFTW JSON together.
Binary images are processed automatically. Their default output is
`_nexus/<input directory>/<original filename including extension>.nxs`.
For example, `scan/tomo-A/reconstruction.txm` produces
`_nexus/scan/tomo-A/reconstruction.txm.nxs`.

To supplement one binary image, use one `*.archive.yaml` with `data.input_file`
pointing to that image. All YAML paths are relative to the **upload root**, even
when the YAML is nested. TIFF jobs use `tiff_directory` instead. After changing
sidecars or YAML, reprocess the entire upload. Missing metadata and ambiguous
associations deliberately stop conversion rather than inventing values.

- [Installation](docs/tutorial/installation.md)
- [Oasis deployment: files, Docker, systemd and definition checks](docs/howto/oasis-deployment.md)
- [Upload layout and automatic processing](docs/howto/nomad-upload.md)
- [Additional metadata: YAML, JSON and CLI examples](docs/howto/additional-metadata.md)
- [Output paths and datasets](docs/reference/outputs.md)
- [Configuration reference](docs/reference/configuration.md)
- [Metadata mapping](docs/metadata-mapping.md)
- [Troubleshooting](docs/howto/troubleshooting.md)
- [Contributing](docs/tutorial/contributing.md)

## Support, citation and license

Report plugin issues at the [project repository](https://github.com/jonasdfortmann/pynxtools-xrm/issues)
or contact Jonas Fortmann. See [contact and attribution](docs/contact.md) and
`CITATION.cff`. Licensed under Apache-2.0; upstream/template attribution is
retained separately from this plugin's ZBT authorship.
