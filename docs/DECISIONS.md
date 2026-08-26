# PuFF — Decision Log

Why the tool is built the way it is. Each entry records what was chosen, what was
rejected, and what the choice now forces or forbids.

**How to use this file.** Before changing something structural, find the decision that
covers it and read the *Rejected* section — the alternative you're about to reach for
is probably already in there with a reason. If the reason no longer holds, that's a
legitimate reversal: add a new entry that supersedes the old one rather than editing
history.

Diagrams that render these decisions: `docs/architecture.mermaid`,
`docs/user_journey.mermaid`.

| # | Decision | Status |
|---|---|---|
| D1 | Indexing is three separate passes | Settled — 2026-08-26 |
| D2 | Identity is the content hash, not the file path | Settled — 2026-08-26 |
| D3 | The index is one user-named file outside the source | Settled — 2026-08-26 |
| D4 | Vectors live as BLOBs inside that file | Settled — 2026-08-26 |
| D5 | The OCR gate rule | **Open** — v2 |
| D6 | Terminal output; computing and printing are separate | Settled — 2026-08-26 |

---

## D1 — Indexing is three separate passes, not one loop

**Context.** The obvious shape is one loop: for each file, hash it, embed it, OCR it,
write the row. It reads naturally and it is wrong for this tool.

**Decision.** Three commands, each a full pass over the database.

```
puff index   walk → sniff → sha256 → metadata      (v0)
puff embed   SigLIP over pictures with no vector    (v1)
puff ocr     Tesseract over pictures not yet done   (v2)
```

Each pass starts with a `SELECT ... WHERE <field> IS NULL`-shaped query, does its
work, writes back.

**Rejected — one per-image loop.** It cannot batch (SigLIP is far faster on batches of
~32 than one image at a time), it cannot re-run a single stage (changing OCR engine
would mean re-hashing every file), and it needs a hand-rolled checkpoint mechanism to
be resumable.

**Consequences.**

- Resumability is not a feature that was built; it is a side effect of the shape. The
  database *is* the checkpoint. There is no progress file, no log to replay, no
  "where was I" logic anywhere in the codebase.
- Every stage must be independently re-runnable and idempotent.
- The user needs to be told which passes have run — see D6 and `puff status`.

---

## D2 — A picture is identified by its content hash, not its path

**Context.** "An image" is two different things wearing one name: a **file** (a path,
a size, an mtime) and a **picture** (the bytes — what SigLIP looks at and Tesseract
reads). One picture can exist at many paths.

This is not hypothetical. Hashing the project's own `data/` folder:

```
b7413b7c…  340.webp
b7413b7c…  New folder/340.webp
b7413b7c…  spaces in name.png          ← same picture, wrong extension
208474ba…  café.jpg
208474ba…  darth-vader-1118454_640.webp
```

Five files. Two pictures.

**Decision.** Two tables. `pictures` keyed by SHA-256, one row per unique image,
carrying the embedding and the OCR text. `files`, one row per path on disk, pointing
at a picture.

**Rejected — one table, one row per file.** It pays SigLIP and Tesseract once per
*copy* rather than once per picture; on a phone dump the same photo routinely appears
in the camera roll, an app cache, and a thumbnail directory. It fills search results
with the same image repeatedly — the exact problem the tool exists to solve. And it
cannot answer "where else does this picture appear?", which is a forensic question,
not a convenience.

**Consequences.**

- There is no `is_duplicate` flag and no duplicate-handling code. A picture at one
  path and a picture at five are stored identically; duplication is simply what you
  see when you count the `files` rows pointing at a picture. The schema doesn't
  *handle* the duplicate problem, it makes the problem stop existing.
- Search results are deduplicated to one row per picture, **with the paths kept**.
  Where a file sits is evidence: `DCIM/Camera` means the device took it,
  `WhatsApp/Media/Sent` means someone sent it, a thumbnail cache may mean the
  original was deleted. Dropping the paths to dedupe would throw away the finding.
- This is the same instinct as `is_image()` refusing to trust the file extension —
  trust the bytes, not the filename — applied to the schema.

**Accepted limitation.** SHA-256 catches only *byte-identical* duplicates. Re-save a
photo at 90% quality, resize it, screenshot it, or let WhatsApp re-compress it on
send, and the hash changes — the tool will insist the two are unrelated pictures.
Perceptual hashing (pHash) is the fix. Backlog, not now. Belongs in the v3 failure
analysis.

---

## D3 — The index is a single file, named by the user, outside the source folder

**Context.** `puff index` has to write somewhere. The source folder is evidence and is
never written to, so the index lives elsewhere. The question was who chooses where.

**Decision.**

```
puff index /evidence/phone_dump --index case1.puff
```

Explicit path, no default the tool guesses, no generated filename. The index records
its own provenance in a `meta` table: `source_root`, `created_at`, `last_indexed`,
`puff_version`.

Collision safety comes from checking `source_root` on open:

| `case1.puff` … | behaviour |
|---|---|
| doesn't exist | create it, record provenance |
| exists, **same** source_root | **resume** — this is the crash-recovery path |
| exists, **different** source_root | **refuse**, exit, change nothing |

**Rejected — appending a timestamp to the filename** (`case1_20260826_1430.puff`) to
avoid clobbering an earlier case. It sounds safe and it breaks two things:

1. *Resumability.* Recovery means re-running the identical command. With generated
   names the second run doesn't reopen the first index — it creates a new empty one
   and re-hashes everything, leaving two half-finished indexes of the same evidence
   with no way to tell which is real. D1's entire payoff, gone.
2. *The multi-pass design.* `puff embed` must reopen the exact file `puff index`
   wrote. If the name is generated, the user has to look it up and paste it into
   every subsequent command — and two runs in the same minute collide anyway.

**Rejected — a `.puff/` directory inside the source folder.** Violates the read-only
evidence rule outright.

**Consequences.**

- Timestamps are data inside the index, queryable and printable in a report — not
  decoration in a filename.
- Establishes a rule that applies tool-wide: **when the tool is unsure, it stops and
  says so. It never guesses and continues.** A refusal is loud and instant; a
  silently-created new file is discovered an hour later.

---

## D4 — One file. Vectors stored as BLOBs, not in a separate `.npy`

**Context.** A SigLIP vector is 768 float32 values, about 3 KB per picture. Either
everything lives in one SQLite file, or the index becomes a directory holding
`index.db` plus `vectors.npy` (one grid, row *n* = picture *n*).

**Decision.** One file. The vector is a BLOB column on the picture's own row.

**Rejected — a folder with a separate `.npy`.** Storing one vector then becomes two
writes to two files: append to the grid, then record the row number in the database.
A crash between them leaves the grid with 4,001 rows and the database believing there
are 4,000. Every vector written afterwards sits one row off from where the database
says it is. Search still runs, still returns results, and the results are the **wrong
pictures** — with nothing anywhere reporting a problem.

That is the failure mode to design against. A crash-safe system is not one that never
crashes; it is one where a crash can only ever leave *less work done*, never *wrong
data*. One transaction cannot half-happen.

**Consequences.**

- Query time loads all vectors out of SQLite and stacks them into one numpy matrix.
  At the MVP target of ~300 pictures that is under a megabyte — instant. This
  decision is scale-dependent and would flip somewhere in the millions.
- Vector storage stays behind two functions (`store_vector`, `load_all_vectors`).
  Nothing else in the codebase knows how vectors are stored, so a future switch to
  `.npy` is a rewrite of two functions rather than a hunt through the project. That
  is the entire extent of the future-proofing; nothing more elaborate is warranted.
- Confirms the "no vector database" call from the original stack: brute-force cosine
  on a 300 × 768 matrix is a single matrix multiply, microseconds.

---

## D5 — The OCR gate — OPEN

Running Tesseract on every picture is wasteful; most photos contain no text. Some
cheap test decides which pictures are worth OCR'ing. The rule itself is undecided and
is a v2 problem.

What the schema must support today: `ocr_status` needs more than two states. A picture
can be *pending*, *done*, or *deliberately skipped by the gate* — and "skipped" must
be distinguishable from "not done yet", or pass 3 will re-examine skipped pictures on
every run.

---

## D6 — Terminal output, and computing is separated from printing

**Decision.** Terminal for now; Gradio stays a v3 concern. The load-bearing part is
the split:

```
search(index, query, k)  →  a list of results
print_table(results)     →  text on screen
```

Never one function that computes *and* prints.

**Rejected — a search function that formats its own output.** The v3 evaluation has to
run dozens of queries and compute precision and recall against a ground-truth set. If
`search()` prints a table, the evaluation script has to parse the tool's own terminal
output — splitting on column widths, stripping alignment. That friction lands exactly
in the time reserved for evaluation and write-up.

**Consequences.** `--json`, the Gradio gallery, and the evaluation harness are all
just additional formatters over the same returned list. None of them is a rewrite.

---

## Commands the user journey surfaced

Drawing the analyst's path (`docs/user_journey.mermaid`) exposed three commands the
data-flow design had no reason to invent:

**`puff status`** — D1 splits work across three passes that run at different times.
Without this, "has this index been embedded yet?" is answered by guessing. Counts per
stage; roughly ten lines of SQL. It is what makes the three-pass design *usable*
rather than merely correct.

**`puff show <sha>`** — where D2 pays off visibly. One picture, all its paths:
`DCIM/Camera` + `WhatsApp/Media/Sent` + `.thumbnails` reads as *taken on this device,
then sent*. Under one-row-per-file that would have been three unrelated search hits.

**`puff skipped`** — the indexer ignores files. A forensic tool that silently discards
200 files cannot be trusted; this makes the discards auditable, and separates "not an
image" from "permission denied" and "truncated file", which are different problems.

---

## Error-design rules

**A missing step must never look like an empty answer.** Searching an index with no
embeddings prints *"this index has no embeddings — run `puff embed`"*, not *"no
results found"*. The second answer makes an analyst conclude there is no laptop in the
evidence and move on. That is a false negative manufactured by the interface, and it
is the worst thing this tool can do.

**Show the near-miss.** When nothing clears the score floor, print the best score
anyway — *"no match above 0.15; best was 0.11, DCIM/IMG_0042.jpg"*. That tells the
analyst the tool worked and the folder is genuinely empty. Bare *"no results"* leaves
them unable to distinguish a working tool from a broken one.

**When unsure, stop.** From D3, but it generalises: refuse loudly rather than proceed
on a guess.

---

## Inherited from the project brief — not re-litigated

Python 3.11+ · SigLIP 2 via `transformers` · Tesseract first, PaddleOCR only if
accuracy demands it · numpy brute-force cosine, no vector database · SQLite + FTS5 ·
Typer for the CLI · Gradio last, not first.

Build order: v0 no AI → v1 semantic → v2 text → v3 interface and evaluation. Each
stage runs end to end before the next begins.

---

## Known gaps and accepted risks

**HEIC/HEIF is unreadable.** Pillow does not read it out of the box, so `is_image()`
reports every HEIC file as not-an-image. HEIC is the default capture format on modern
iPhones, so on a real seized device a large fraction of the photo library would be
silently skipped while the tool reported a clean scan. A false negative is the worst
failure mode a forensic tool has. Fix is `pillow-heif` plus registering the opener at
startup. Deferred to before the v3 evaluation; measure how many files it recovers.

**`is_image()` catches bare `Exception`.** Conflates genuinely-not-an-image with
permission errors, I/O errors, and truncated files. Different problems, and the tool
should distinguish them. `puff skipped` is where that distinction becomes visible.

**Byte-identical duplicates only** — see D2.

**300 images is too small to benchmark speed.** It is fine for precision and recall,
but "searched 300 images in 40 ms" is not a claim worth charting. A meaningful timing
benchmark needs a few thousand. Source that corpus before v3 begins, not during it.
