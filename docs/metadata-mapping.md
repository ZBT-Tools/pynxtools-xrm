# Metadata mapping and validation

Binary conversion uses OLE streams from exactly one ZEISS image file.

| Input | Required metadata | Mapping |
|---|---|---|
| TXRM | Sample name, measured angle per frame, and frame role | Read the sample from the `Sample:` line of `AcquisitionSettings/StatusString`. Use `ImageInfo/Angles`. A primary bundle explicitly marked `Tomography` supplies projection keys. A frame explicitly marked unavailable gets the invalid key. |
| TXM | Sample, source, title, original acquisition, reconstruction program/version/date and calibrated axes | Use embedded file references for title and source file. Read the source name from the active source configuration. Use local axes from `PixelSize` and `YPosition`. Report any missing required field before writing. |
| XRM | One image with a supported pixel type | Write an `NXdata` image linked to its detector dataset. Add local row and column axes when object-side pixel calibration is available. |

The audited TXM files do not identify an explicit reconstruction program and
process timestamp. The OLE software version and layer timestamps are preserved
with their original meanings. The numeric source type code remains a vendor
value pending verification. Output volume attributes describe the unchanged
stored grey values and do not assert a conversion to a physical quantity.

Camera name, serial number, exposure, objective, filter and X-ray source
settings go into the relevant instrument groups when present and applicable.
The sensor pitch remains distinct from object-side pixel size. Native stage
readbacks are kept in their recorded coordinates. Local time strings preserve
the original timezone-free values. Undecoded streams remain recoverable through
the path, offset and byte datasets documented in the [output reference](reference/outputs.md).

## TIFF stack metadata

TIFF stacks use the separate TIFF adapter. Supply an eLabFTW JSON and explicit
supplements for missing values. Reconstruction TIFFs require verified
orientation, volume origin, voxel calibration and reconstruction metadata.
Projection TIFFs require measured angles and an explicit frame role array.
See [additional metadata](howto/additional-metadata.md) for examples.

The eLabFTW field registry is maintained in elabftw.py. Standard NXsample,
NXsource, NXdetector, NXfilter, NXuser, NXentry and NXprocess fields are used where
their semantics match. Additional fields live in named domain NXcollections,
which are optional base-class extensions rather than required application fields.
Instrument item identifiers are resolved to names only through an exact linked
record match. Multiselect text fields remain native UTF-8 arrays. Form settings,
access control, history and UI fields have no verified domain destination and
are listed individually in metadata_provenance/elabftw_mapping (source_path,
target_path, status, reason). Empty fields are reported separately. Unknown
populated extra fields retain their native value/unit under unmapped_metadata.
The original eLabFTW JSON is not embedded, including in the provenance group.
Lower-priority conflicting values and selected field origins are native datasets.
