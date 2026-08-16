# PuFF — Forensic Image Search

A local tool that indexes a folder of images and makes them searchable two ways:

- **Semantic search** — "find images containing a laptop" (SigLIP embeddings)
- **Text search** — "find images where the text 'INVOICE' appears" (OCR)

Everything runs locally. No cloud APIs. No image data leaves the machine.

## Status

v0 — walking a folder, detecting real images, hashing, metadata, SQLite. In progress.

## Design constraints

- Never write to the source folder. It is treated as read-only evidence.
- Must be resumable after a crash.
- File extensions are not trusted. Format is determined from file contents.

## Known gaps

### HEIC / HEIF not supported

Pillow does not read HEIC/HEIF out of the box, so `is_image()` currently reports
every HEIC file as "not an image".

This matters: HEIC is the default capture format on modern iPhones. On a real
seized device a large fraction of the photo library could be silently skipped,
and the tool would report a clean scan while missing most of the evidence. A
false negative in a forensic tool is the worst failure mode there is.

Fix is `pip install pillow-heif` plus registering the opener at startup.
Deferred — revisit before the v3 evaluation, and measure how many files it
recovers on a realistic corpus.

### Broad exception handling

`is_image()` catches `Exception` and reports any failure as "not an image". This
conflates genuinely-not-an-image with permission errors, I/O errors, and
truncated files. Those are different problems and a forensic tool should
distinguish them. Revisit when logging is added.
