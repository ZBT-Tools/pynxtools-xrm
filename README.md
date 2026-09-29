[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
![](https://github.com/FAIRmat-NFDI/pynxtools-xrm/actions/workflows/pytest.yml/badge.svg)
![](https://github.com/FAIRmat-NFDI/pynxtools-xrm/actions/workflows/pylint.yml/badge.svg)
![](https://github.com/FAIRmat-NFDI/pynxtools-xrm/actions/workflows/publish.yml/badge.svg)
![](https://img.shields.io/pypi/pyversions/pynxtools-xrm)
![](https://img.shields.io/pypi/l/pynxtools-xrm)
![](https://img.shields.io/pypi/v/pynxtools-xrm)
![Coverage Status](https://coveralls.io/repos/github/FAIRmat-NFDI/pynxtools-xrm/badge.svg?branch=main)

# `pynxtools-xrm`: streaming XRM TIFF conversion

This plugin converts numbered, reconstructed X-ray microscopy TIFF layers into
a compressed `NXtomoproc` NeXus file. Metadata are handled by a
`MultiFormatReader`; image pixels are deliberately kept out of its template and
written one TIFF at a time into a fixed-shape, chunked HDF5 dataset.

This `pynxtools` plugin was generated with [`cookiecutter`](https://github.com/cookiecutter/cookiecutter) using the [`pynxtools-plugin-template`](https://github.com/FAIRmat-NFDI/pynxtools-plugin-template) template.

## Installation

It is recommended to use python 3.12 with a dedicated virtual environment for this package. Learn how to manage [python versions](https://github.com/pyenv/pyenv) and [virtual environments](https://realpython.com/python-virtual-environments-a-primer/).

This package is a reader plugin for [`pynxtools`](https://github.com/FAIRmat-NFDI/pynxtools) and should be installed together with `pynxtools`:

```shell
uv pip install -e .
```

## Convert a stack

```shell
pynx-xrm inspect "AvCarb_FLEX_20bar/Bilder 20 bar"
pynx-xrm convert \
  --metadata 6100_SDP_XRM_576_001.json \
  --tiffs "AvCarb_FLEX_20bar/Bilder 20 bar" \
  --output AvCarb_FLEX_20bar.nxs
```

The TIFF width becomes X, ascending file number becomes Y, and TIFF height
becomes Z. Coordinates use the isotropic voxel size from the metadata and are
centered around zero. See the [architecture and operation guide](docs/architecture.md)
for the data flow, file responsibilities, assumptions, NOMAD setup, and tests.

## Supported conversion interfaces

The production interfaces are:

- `pynx-xrm convert` for local or scripted conversion;
- `XRMDataConverter` for conversion inside a NOMAD Oasis.

Standard `pynx convert --reader xrm` is intentionally not supported. The core
pynxtools writer expects the complete volume in the reader template, which
would defeat bounded-memory TIFF streaming. The `xrm` reader entry point is
retained for pynxtools discovery and supplies the metadata phase to the
dedicated writer; unsupported calls fail with guidance instead of creating an
incomplete NXtomoproc file.

for the latest released version.

## Docs

More information about this pynxtools plugin is available in the [documentation](https://fairmat-nfdi.github.io/pynxtools-xrm/). You will find information about getting started, how-to guides, the supported file formats, how to get involved, and much more there.

## Contact person in FAIRmat for this reader

The NOMAD Authors

<!-- ## How to cite this work -->
