# pynxtools-xrm

`pynxtools-xrm` converts ZEISS X-ray microscopy data into NeXus and integrates
the conversion with NOMAD Oasis. ZBT – Zentrum für BrennstoffzellenTechnik GmbH
develops this community plugin through Jonas Fortmann
([j.formtann@zbt.de](mailto:j.formtann@zbt.de)). It is not authored or maintained
by “The NOMAD Authors”. NOMAD, pynxtools and the NeXus definitions are upstream
projects and retain their own authorship.

## Start here

1. [Install the package](tutorial/installation.md) in the intended environment.
2. For a server, complete [Oasis deployment](howto/oasis-deployment.md), including
   definition preparation and environment variables for all workers.
3. Follow [the upload guide](howto/nomad-upload.md) to preserve directory structure
   and make image-to-metadata associations unambiguous.
4. Supply genuine missing values using [additional metadata](howto/additional-metadata.md).
5. Check each image and generated NeXus entry; a completed upload does not imply
   that every entry succeeded. See [troubleshooting](howto/troubleshooting.md).

## Supported conversions

| Data | Application | Initiation |
|---|---|---|
| TXRM projections | `NXtomo` | Automatic ZEISS binary parser |
| TXM reconstruction | `NXtomoproc` | Automatic ZEISS binary parser |
| Single-image XRM | Local `NXxrm_image` | Automatic ZEISS binary parser |
| Numbered grayscale TIFF stack | `NXtomoproc` or `NXtomo` | YAML job or CLI |

Each binary image owns one output. RCP files provide associated recipe metadata;
they do not independently produce converted image entries. The local
`NXxrm_tomoproc` XML is not an active conversion target in this implementation.

## Documentation map

| Need | Guide |
|---|---|
| First installation / development | [Installation](tutorial/installation.md), [contributing](tutorial/contributing.md) |
| Exact service files and restart procedure | [Oasis deployment](howto/oasis-deployment.md) |
| Upload folders, ZIP layout and processing | [NOMAD uploads](howto/nomad-upload.md) |
| Missing fields and reproducible examples | [Additional metadata](howto/additional-metadata.md) |
| YAML fields and CLI flags | [Configuration reference](reference/configuration.md) |
| Output names, HDF5 paths and reuse | [Outputs](reference/outputs.md) |
| Metadata origins and strict validation | [Metadata mapping](metadata-mapping.md) |
| Streaming and coordinates | [Architecture](architecture.md) |
| Failures | [Troubleshooting](howto/troubleshooting.md), [Windows ZIP import](troubleshooting-windows-zip-upload.md) |
| Ownership, support and citation | [Contact](contact.md), [versioning](learn/versioning.md) |

The separation of tutorials, task guides, explanation and reference follows the
structure of the [NOMAD documentation](https://docs.nomad-lab.eu/). It does not
constitute certification or a claim that FAIRmat maintains this package.
