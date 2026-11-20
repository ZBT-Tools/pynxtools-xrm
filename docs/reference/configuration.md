# Configuration reference

## NOMAD archive YAML

Use UTF-8 files named `*.archive.yaml` with a `data:` object and:

```yaml
data:
  m_def: pynxtools_xrm.nomad.schema_packages.schema.XRMDataConverter
```

| `data` field | Type / default | Meaning |
|---|---|---|
| `input_file` | string; absent | Binary TXRM/TXM/XRM path relative to upload root; selects binary ownership |
| `tiff_directory` | string; absent | TIFF slice directory relative to upload root; use when no `input_file` |
| `metadata_file` | string; absent | TIFF only: eLabFTW-style JSON path relative to upload root |
| `recipe_file` | legacy field | Accepted for existing archive YAMLs but no longer read during conversion |
| `target_definition` | enum | TIFF target, defaults to `NXtomoproc`. Binary targets are fixed by the input type. |
| `metadata_supplements` | JSON object; absent | TIFF only: resolver keys for missing values; see [metadata guide](../howto/additional-metadata.md) |
| `output` | string | Binary default `_nexus/<relative source>.nxs`; TIFF fallback `xrm_volume.nxs` |
| `gzip_level` | integer; `4` | gzip compression level, 0..9 |
| `target_chunk_mib` | number; `1.0` | Target uncompressed chunk size in MiB; must give a positive valid configuration |
| `export` | boolean; `true` | Enables YAML normalizer conversion/request; generated binary sections set it to `false` internally |
| `assumptions` | legacy list of strings | Retained schema field; does not fabricate missing required values |
| `conversion_status` | generated string | `requested`, `converted`, `reused` or the message listing missing binary metadata |
| `nexus_view` | generated archive reference | Link to generated NeXus entry; not user input |

`export: false` stops the YAML normalizer. It does **not** disable the independent
binary matching parser or make it ignore a matching YAML's options. Use the
deployment's processing controls when disabling a parser is intended.

TXRM uses `NXtomo`, TXM uses `NXtomoproc`, and XRM uses base classes. TIFF
supports `NXtomo` and `NXtomoproc`.

## CLI

```text
pynx-xrm inspect INPUT
pynx-xrm definitions --output DIRECTORY
pynx-xrm convert (--input IMAGE | --tiffs DIRECTORY) --output FILE.nxs [OPTIONS]
```

| Convert option | Meaning |
|---|---|
| `--metadata FILE` | TIFF only: one eLabFTW-style JSON |
| `--supplements FILE` | TIFF only: plain JSON object containing resolver keys |
| `--target NAME` | `NXtomo` or `NXtomoproc`. Omit for automatic binary mapping. |
| `--gzip-level N` | Default `4` |
| `--chunk-mib SIZE` | Default `1.0` |
| `--overwrite` | Allow validated replacement/reuse of an existing output |

TIFF sidecars are explicit. `inspect` reports image dimensions, frame count, datatype and
auxiliary block names, or recipe information for RCP. It does not print every
decoded image metadata field and does not replace full conversion validation.

## Environment

`NEXUS_DEF_PATH` selects the complete NeXus definitions root and must be set
before Python imports. Read the [deployment guide](../howto/oasis-deployment.md)
for persistent Compose/systemd examples and verification commands.
