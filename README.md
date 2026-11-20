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
| `.xrm` (one image) | NeXus base classes | Automatic binary parser |
| Numbered `.tif` / `.tiff` files | `NXtomoproc` or `NXtomo` | `*.archive.yaml` |
| eLabFTW JSON | TIFF metadata | Explicitly assigned by the TIFF job |

## Installation and definitions

Python >=3.10 is declared by the package; Python 3.12 is the documented setup.
The supported pynxtools dependency is `>=0.15.2,<0.16`. NOMAD 2.0.0 Oasis is the
deployment addressed here; installation alone does not establish compatibility
with every NOMAD/parser combination.

From a checkout, in the intended Python environment:

```bash
python -m pip install -e .
```

Install the plugin in the Oasis app and worker environments. New conversions use
the standard NeXus definitions supplied with pynxtools. The custom overlay is
available for deployments that still read older `NXxrm_image` exports.
Follow the [file-by-file Oasis deployment guide](docs/howto/oasis-deployment.md).

## First conversion

```bash
pynx-xrm inspect acquisition.txrm
pynx-xrm inspect recipe.rcp
pynx-xrm convert --input acquisition.txrm --output acquisition.nxs
```

ZEISS conversions use only embedded metadata. When required fields are missing,
the command prints their NeXus paths and exits before writing an output. RCP files
can be inspected independently. `--metadata` and `--supplements` apply to TIFF
stacks. Use `pynx-xrm convert` for streamed pixel output.

## NOMAD uploads

Binary images are processed individually and automatically. Their default output is
`_nexus/<input directory>/<original filename including extension>.nxs`.
For example, `scan/tomo-A/reconstruction.txm` produces
`_nexus/scan/tomo-A/reconstruction.txm.nxs`.

To customize output or compression for one binary image, use an `*.archive.yaml`
with `data.input_file` pointing to that image. TIFF jobs use `tiff_directory` and
can assign an eLabFTW JSON explicitly. YAML paths are relative to the upload root.

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
