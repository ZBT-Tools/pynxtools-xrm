# Metadata mapping and strict validation

Effective precedence is image > associated RCP > eLabFTW > explicit missing values.
Conflicting lower-priority values remain in provenance. Explicit configuration
cannot change an existing value. Invalid high-priority metadata are not replaced.
RCP settings are preserved as recipe settings; nominal angle limits are never
used to fabricate measured angle arrays. All RCP streams remain recoverable from
entry/recipe/data (JSON with raw_streams_base64).

| Required content | NXtomo | NXtomoproc | NXxrm_image | ZEISS source |
|---|---|---|---|---|
| Sample name | yes | yes | yes | assigned RCP SampleName or ELN/config |
| Image pixels / dimensions / datatype | yes | yes | yes | ImageInfo and ImageData blocks |
| Theta and stage X/Y/Z | profile | profile | profile | Angles, X/Y/ZPosition; TXM MeanSampleX/Y/Z |
| Rotation angle array / image_key | yes | no | no | measured Angles; primary TXRM projections key=0 |
| Cubic object pixel/voxel size | optional | yes | yes | ImageInfo/PixelSize (um) |
| Source name / type | optional | yes | optional | explicit proven source; numeric SourceType not decoded |
| Reconstruction program/version/date | no | yes | no | missing in inspected TXM; no exeVersion/date fallback |
| Raw acquisition file | no | yes | no | ReconSettings/InputFileName or assigned RCP |
| Physical image orientation | local axes | yes | local axes | explicit calibrated row/column axes and signs |
| Volume origin | no | TIFF required | no | explicit TIFF origin; measured TXM Y plus local X/Z offsets |

The NXDL validator is authoritative for the pinned application contract. Profile
requirements add geometry and provenance checks. Missing fields are reported
together by MissingRequiredMetadata before output creation where possible.

| Optional metadata | Destination / handling |
|---|---|
| XrayVoltage, XrayCurrent, ExpTimes | NXsource voltage/current, detector count_time |
| Acquisition ImageInfo/StoRADistance, DtoRADistance | Signed X transformations in mm; never sample-center distance |
| TXM ReconInputTomoParams/StoRADistance, DtoRADistance | Positive magnitudes in um, converted to mm and placed on the confirmed global axis: source -X, detector +X. TXM ImageInfo distances are not decoded using the acquisition convention. |
| CameraName, CameraSerialNumberString | Detector description and serial_number |
| ObjectiveName, SourceFilterName | instrument/optics/objective and instrument/filter/description; manufacturer bytes retained |
| ImageInfo/Date | Berlin frame_times in provenance; first projection timestamp as start_time |
| TXM ImageInfo/Date | Layer timestamps retained; never asserted as reconstruction process time |
| CamPixelSize | Sensor pitch retained distinctly from object voxel/pixel calibration |
| IsFlatPanel and unknown vendor fields | Raw stream bytes with original OLE paths |
| eLabFTW identity/project/sample/users/notes | NXentry, NXsample, NXuser and NXnote |
| Additional acquisition/reconstruction/storage fields | Native scalar/array datasets in optional domain NXcollections; no serialized eLabFTW JSON |

All full local timestamps use Europe/Berlin, with real UTC conversion for aware
values. Full timestamp fields reject date-only strings, DST gaps and ambiguous
local times. The optional acquisition/measurement_date preserves a calendar date
without inventing a time. Original ZEISS bytes and the RCP recipe remain as
provenance notes. Conversion time is the
actual new conversion time and is distinct from acquisition/reconstruction time.

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

The single-image profile is a local application named NXxrm_image using generic
NXimage and NXdata; it does not mislabel X-ray microscopy as electron microscopy
through NXem. Its NXDL is packaged and added to an explicit definitions overlay.
