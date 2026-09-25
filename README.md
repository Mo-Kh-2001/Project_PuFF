# PuFF: Forensic Image Search


A local tool that indexes a folder of images and makes them searchable two ways:

- **Semantic search:** "find images containing a laptop" (SigLIP embeddings)
- **Text search:** "find images where the text 'INVOICE' appears" (OCR)

Everything runs locally. No cloud APIs. No image data leaves the machine.

## Status

**v0 (in progress).** No AI yet. Walk a folder, detect real images, hash them,
record metadata in SQLite.

Done:

- Recursive folder walk (`iter_files` in `puff/scan.py`)
- Image detection from file contents, not the extension (`is_image`, using Pillow)
- SHA-256 hashing, read in 8 KB chunks so large files never load fully into memory (`puff/hash.py`)
- Design settled and written up in `docs/DECISIONS.md`

Not done yet:

- Metadata extraction
- SQLite schema: a `pictures` table keyed by hash and a `files` table with one row per path (see D2)
- The `puff index` command and crash resumability

## Running it

From the project root:

```
pip install -r requirements.txt
python puff/scan.py
```

For every file under `data/`, this prints whether it is an image, the detected
format, the path, and the SHA-256 hash.

## Design constraints

- Never write to the source folder. It is treated as read-only evidence.
- Must be resumable after a crash.
- File extensions are not trusted. Format is determined from file contents.
- A picture is identified by its content hash, not its path. Five copies of one
  photo are one picture with five paths.

The reasoning behind each choice, and the alternatives rejected, is in
`docs/DECISIONS.md`. Diagrams are in `docs/architecture.mermaid` and
`docs/user_journey.mermaid`.

## Known gaps

### HEIC / HEIF not supported

Pillow does not read HEIC/HEIF out of the box, so `is_image()` currently reports
every HEIC file as "not an image".

This matters. HEIC is the default capture format on modern iPhones. On a real
seized device a large fraction of the photo library could be silently skipped,
and the tool would report a clean scan while missing most of the evidence. A
false negative in a forensic tool is the worst failure mode there is.

The fix is `pip install pillow-heif` plus registering the opener at startup.
Deferred until before the v3 evaluation, where I'll measure how many files it
recovers on a realistic corpus.

### Broad exception handling

`is_image()` catches `Exception` and reports any failure as "not an image". This
conflates genuinely-not-an-image with permission errors, I/O errors, and
truncated files. Those are different problems and a forensic tool should
distinguish them. Revisit when logging is added.

### Byte-identical duplicates only

SHA-256 only matches exact copies. A resized, re-compressed or screenshotted
version of the same photo gets a different hash and is treated as a different
picture. Perceptual hashing would fix this. Backlog.
