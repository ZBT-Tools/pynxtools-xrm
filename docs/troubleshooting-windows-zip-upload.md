# Windows: ZIP upload requires a second processing run

## Summary

On a locally hosted NOMAD Oasis running on Windows, an uploaded ZIP archive can
be extracted successfully but still leave the upload workflow in the failed
state. Starting **Reprocess** a second time then succeeds.

This is not an error in `XRMDataConverter` or in the generated NXtomoproc file.
The failure happens earlier, while NOMAD imports and removes the temporary ZIP
archive. The observed exception is a Windows file-locking error:

```text
PermissionError: [WinError 32]
The process cannot access the file because it is being used by another process:
.../.volumes/fs/tmp/<upload-id>/<upload>.zip
```

The problem was reproduced with both a small synthetic XRM upload and the
complete `AvCarb_FLEX_20bar.zip` upload. It is relevant primarily to local
Windows development. A production Oasis running on Linux is normally not
blocked by this particular symptom because Linux permits unlinking an open
file. The underlying file handle should nevertheless be closed explicitly.

## Observable processing sequence

The first workflow proceeds as follows:

1. NOMAD receives the ZIP in its temporary upload directory.
2. `StagingUploadFiles.add_rawfiles()` recognizes and extracts the ZIP.
3. All JSON, TIFF, and `*.archive.yaml` files are copied into the staging raw
   directory.
4. NOMAD leaves the archive filesystem context.
5. NOMAD attempts to delete the temporary ZIP.
6. Windows rejects the deletion because the outer `fsspec` file handle is
   still open.
7. The `update_files_activity` and therefore the first upload workflow fail.

The extracted files remain in staging despite that failure. During the second
processing run NOMAD operates on these existing raw files, the archive parser
loads the XRM entry, and `XRMDataConverter.normalize()` can produce and register
the `.nxs` file successfully.

The important distinction is therefore:

```text
First run:  ZIP import -> extraction -> temporary ZIP deletion fails
Second run: existing raw files -> archive parser -> XRM normalizer succeeds
```

## Location of the failure

### 1. NOMAD opens the archive with fsspec

The relevant context manager is `FSUtility._open_archive_fs()` in:

```text
packages/nomad-FAIR/nomad/files.py
```

At NOMAD commit `2ddd7fb88711ab30b97b88a70c48e93be5b6ebd3`, the local
helper closes the archive filesystem after yielding it:

```python
def _wrap(_fs):
    yield _fs
    if hasattr(_fs, "close"):
        _fs.close()
```

Reference:
[nomad/files.py in NOMAD](https://gitlab.mpcdf.mpg.de/nomad-lab/nomad-FAIR/-/blob/2ddd7fb88711ab30b97b88a70c48e93be5b6ebd3/nomad/files.py)

There are two issues with this implementation:

- cleanup is not protected by `try/finally`, so an exception raised by the
  caller could bypass `_fs.close()`;
- `ZipFileSystem.close()` does not close the owning `fsspec.core.OpenFile`
  object that was opened when the ZIP filesystem was constructed from a path.

### 2. NOMAD extracts the ZIP

`StagingUploadFiles.add_rawfiles()` opens the ZIP through
`FSUtility.open_archive()` and copies all archive members:

```python
if archive_format == "zip":
    with FSUtility.open_archive(path, fs=target_fs) as _fs:
        yield "", "", _fs
```

Local reference:

```text
packages/nomad-FAIR/nomad/files.py:1766
```

### 3. NOMAD deletes the temporary source

After extraction, the same method removes the temporary upload file:

```python
finally:
    if cleanup_source_file_and_dir:
        self._fs.rm(path, recursive=True)
```

Local reference:

```text
packages/nomad-FAIR/nomad/files.py:1810
```

On Windows this removal raises `PermissionError` while the source ZIP still has
an open handle.

### 4. fsspec keeps a separate owner object

When `ZipFileSystem` receives a path, its constructor creates an
`fsspec.core.OpenFile`, enters that context, and stores both the owner and the
opened file:

```python
fo = fsspec.open(fo, mode=m, protocol=target_protocol, **target_options)
self.of = fo
self.fo = fo.__enter__()
self.zip = zipfile.ZipFile(self.fo, mode=mode, ...)
```

Its explicit `close()` method closes `self.zip`, while closing `self.of` is
handled separately by the destructor. Garbage collection is not guaranteed to
run before NOMAD tries to delete the temporary archive.

References:

- [fsspec `ZipFileSystem`](https://github.com/fsspec/filesystem_spec/blob/master/fsspec/implementations/zip.py)
- [fsspec `OpenFile`](https://github.com/fsspec/filesystem_spec/blob/master/fsspec/core.py)

## Why `XRMDataConverter` is not the cause

The XRM normalizer is invoked only after NOMAD has imported the upload and the
archive parser has parsed the `*.archive.yaml` mainfile. Its implementation is
located in:

```text
packages/pynxtools-xrm/src/pynxtools_xrm/nomad/schema_packages/schema.py
```

The converter starts at `XRMDataConverter.normalize()` and invokes
`convert_tomoproc()` before registering the finished output through
`process_updated_raw_file()`:

```python
report = convert_tomoproc(
    metadata,
    tiffs,
    output,
    compression=CompressionConfig(...),
    overwrite=True,
)

archive.m_context.process_updated_raw_file(self.output, allow_modify=True)
```

References:

- [`XRMDataConverter.normalize()`](../src/pynxtools_xrm/nomad/schema_packages/schema.py)
- [`convert_tomoproc()`](../src/pynxtools_xrm/streaming_writer.py)

The recorded failing Temporal activity was `update_files_activity`, and its
traceback ended in `StagingUploadFiles.add_rawfiles()` while deleting the
temporary source ZIP. It did not end in `XRMDataConverter.normalize()`.

## Workarounds

### Reprocess the upload

For local development, manually starting **Reprocess** again works because the
first attempt already copied the archive members into staging. This is useful
for testing but should not be treated as a production solution.

### Use TAR instead of ZIP on Windows

Uploading a `.tar` or `.tar.gz` archive avoids the affected ZIP filesystem
branch. NOMAD reads TAR input inside an explicit file context:

```python
with target_fs.open(location, "rb") as file:
    with tarfile.open(fileobj=file, mode="r|*") as tar:
        ...
```

The file context is closed before cleanup attempts to remove the temporary
archive.

### Run the development Oasis on Linux or WSL

The intended production environment is Linux. Running the development worker
inside Linux or WSL also avoids the immediate Windows unlink restriction.
Explicitly closing the resource remains preferable because it avoids leaking a
file descriptor.

## Proposed NOMAD-Core fix

The durable fix belongs in NOMAD Core's `FSUtility._open_archive_fs()`, not in
`pynxtools-xrm`. The wrapper should always execute cleanup and should also close
the owning `OpenFile` for a `ZipFileSystem`:

```python
def _wrap(_fs):
    owner = getattr(_fs, "of", None)
    try:
        yield _fs
    finally:
        if hasattr(_fs, "close"):
            _fs.close()

        # ZipFileSystem.close() closes the ZipFile but, when constructed from
        # a path, the owner returned by fsspec.open() must also be closed.
        if isinstance(_fs, ZipFileSystem) and owner is not None:
            close_owner = getattr(owner, "close", None)
            if callable(close_owner):
                close_owner()
```

Before submitting this upstream, the patch should also be checked for ZIP write
and append modes and for non-local filesystems. The fix must not prematurely
close a caller-owned file object.

An alternative implementation is to make the ownership explicit when creating
the `ZipFileSystem`: open the source file in an outer `with` block, construct
the ZIP filesystem from that file object, and close the ZIP filesystem before
leaving the outer block.

## Suggested regression test

A regression test should verify both the resource state and actual Windows
deletion behavior. The resource assertion also catches the problem on Linux,
where unlinking an open file would otherwise hide it.

```python
import zipfile

from nomad.files import FSUtility


def test_open_archive_releases_source_file(tmp_path):
    archive_path = tmp_path / "upload.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("metadata.json", "{}")

    with FSUtility.open_archive(str(archive_path)) as archive_fs:
        assert archive_fs.cat("metadata.json") == b"{}"
        source_file = archive_fs.fo

    # This assertion detects the leaked owner on every operating system.
    assert source_file.closed

    # On Windows this operation raised WinError 32 before the fix.
    archive_path.unlink()
    assert not archive_path.exists()
```

A second integration test can exercise `StagingUploadFiles.add_rawfiles()` with
`cleanup_source_file_and_dir=True`:

```python
def test_add_rawfiles_removes_temporary_zip(staging_upload_files, tmp_path):
    archive_path = tmp_path / "upload.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("metadata.json", "{}")

    staging_upload_files.add_rawfiles(
        str(archive_path),
        cleanup_source_file_and_dir=True,
        auto_decompress=True,
    )

    assert staging_upload_files.raw_path_exists("metadata.json")
    assert not archive_path.exists()
```

## Verification checklist

After applying a NOMAD-Core fix:

1. Start the local Oasis on Windows.
2. Upload a fresh ZIP containing an XRM `*.archive.yaml`, metadata JSON, and a
   small numbered TIFF stack.
3. Confirm that `update_files_activity` completes successfully.
4. Confirm that the temporary ZIP disappears from `.volumes/fs/tmp`.
5. Confirm that the archive entry and generated `.nxs` entry both reach
   `SUCCESS` during the first workflow.
6. Confirm that the `.nxs` volume retains its expected shape, dtype, chunks,
   and gzip compression.

## Scope decision for pynxtools-xrm

No workaround is currently added to `XRMDataConverter`, because:

- the error occurs before the converter is invoked;
- the target production Oasis runs on Linux;
- changing the converter cannot release a file handle owned by NOMAD's upload
  layer;
- the appropriate permanent correction is in NOMAD Core or fsspec resource
  handling.

This document records the issue so that it can be revisited if Windows becomes
a supported deployment target or if the same resource leak appears in another
environment.
