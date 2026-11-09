# Diagnose conversion failures

Open the failed entry's Logs and expand the exception. Record the processing
time and mainfile: an older failure or a generated NeXus entry can describe a
different stage from the binary conversion you are investigating.

| Error / symptom | Cause to check | Action |
|---|---|---|
| `The nxdl file, NXxrm_image, was not found` | Overlay missing or invisible in the worker; variable set after import | Prepare complete overlay; persist `NEXUS_DEF_PATH` in every app/worker; recreate/restart; verify inside worker |
| `MissingRequiredMetadata` | Unresolved profile fields | Read exact field list; assign correct JSON/RCP; supply genuine missing values |
| Same missing fields after adding YAML | YAML has no matching `input_file`, incorrect extension/name or reprocessing not run | Use `*.archive.yaml`, full upload-relative image path, one matching job; reprocess upload |
| `FileNotFoundError` for metadata/input | Nested YAML paths treated as YAML-relative; ZIP prefix or case differs | Compare against upload Files tree; use upload-root-relative paths |
| `Multiple YAML jobs refer to the same binary input` | Duplicate matching configuration | Keep one matching job per binary input |
| `Multiple eLabFTW files` | Two candidate JSONs in nearest metadata scope | Set `metadata_file` explicitly |
| RCP not unambiguously associated | Recipe declarations/context do not match image | Preserve vendor tree; select correct recipe; verify actual relationship |
| `MetadataConflict` / `Explicit ... cannot override ...` | Supplement differs from an existing source value | Remove redundant supplement; correct authoritative source if it is wrong |
| Full timestamp / DST error | Date-only or ambiguous local time | Supply actual full timestamp with explicit UTC offset |
| Orientation error | Missing or unsupported row/column convention | Confirm axes, use row=z, column=x and signs ±1; do not guess |
| Slice spacing conflicts with cubic calibration | TXM Y spacing disagrees with voxel size | Check original calibration/headers; do not force a replacement voxel size |
| TIFF numbering / dimensions / grayscale error | Gaps, duplicate indices, multipage/color images or inconsistent slices | Correct the input stack; see upload requirements |
| Existing destination has no overlay marker / base changed | Unsafe overlay reuse | Prepare a new directory from the current environment; switch processes together |
| Another conversion targets the same output | Concurrent jobs or a stale lock after termination | Ensure distinct output names; verify no active writer before administrator recovery |
| Conversion succeeds but `.nxs` entry fails | Generated-file parser/schema setup | Inspect that entry's logs, enabled NeXus parser and definition paths |
| Search app does not show converted entries | App uses legacy NeXus parser fields | Inspect generated archive and parser version; do not infer conversion failure from the app |
| Upload says completed but entries failed | Aggregate status differs from entry result | Check each conversion and generated NeXus entry |

Do not fix missing source type, version or orientation with arbitrary `Test`
values or zero coordinates. Successful conversion is not evidence of physical
correctness. Refer to [metadata examples](additional-metadata.md).

After changing metadata or definitions, restart services when required and
reprocess the upload. An older `.nxs` can remain after a failed replacement;
check the latest entry log and status. See [output lifecycle](../reference/outputs.md).

For Windows ZIP extraction locks before parsing begins, see the separate
[Windows import note](../troubleshooting-windows-zip-upload.md). It is not the
same problem as Linux NXDL lookup or missing measurement metadata.

## Information for a bug report

Use the [project issue tracker](https://github.com/jonasdfortmann/pynxtools-xrm/issues)
or [contact the maintainer](../contact.md). Include package revision, Python,
NOMAD and pynxtools versions; affected file type; complete relevant exception;
an anonymized directory tree and YAML/JSON example; and definition lookup output
from the actual worker. Describe expected and actual behavior. Share a minimal
reproducer when permitted; remove credentials and confidential experiment data.
