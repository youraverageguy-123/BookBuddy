# 1. End-to-End Pipeline Audit (CRITICAL)

**Goal:** Verify that the entire pipeline functions as a single deterministic system.

## Procedure

Use a medium-sized EPUB (150-300 chapters if possible).

Run:

```
Import EPUB

↓

Extract text/images

↓

Image classification

↓

OCR

↓

Evidence generation

↓

AI extraction

↓

Evidence storage

↓

Replay

↓

Resolvers

↓

Graph

↓

Snapshots

↓

Dictionary

↓

API
```

Record:

* Total runtime
* Number of API calls
* Failed API calls
* Retry count
* Number of evidence objects
* Number of graph entities
* Number of relationships
* Number of events
* Number of snapshots

Verify:

* No crashes
* No silent skips
* No duplicate entities
* Replay completes
* API returns expected objects

---

# 2. Deterministic Replay Audit (CRITICAL)

Your architecture is built around replay.

It must be provably deterministic.

## Procedure

### Pass 1

```
Parse Book

↓

Graph A
```

Export:

* entities
* aliases
* relationships
* events
* snapshots

Delete:

```
graph.db
```

Replay from evidence.

```
Evidence

↓

Replay

↓

Graph B
```

Compare:

* entity count
* relationship count
* alias count
* event count
* snapshot count

Then compare every table row.

Verify:

* IDs stable (if intended)
* values identical
* timestamps excluded if expected

Run this multiple times.

Expected:

```
Graph A == Graph B
```

Every run.

---

# 3. Database Integrity Audit

## Verify every table

For every table:

Check

Primary keys

Foreign keys

NOT NULL

Indexes

Cascade rules

Uniqueness

Run

```
PRAGMA integrity_check;
```

Should return

```
ok
```

Run

```
PRAGMA foreign_key_check;
```

Should return zero rows.

---

# 4. Performance Audit

Never optimize blindly.

Measure.

Collect:

## EPUB extraction

Average chapter extraction

Maximum chapter extraction

Average image extraction

Maximum image extraction

---

## AI

Average API latency

Median latency

95th percentile

Retries

Timeouts

Tokens per chapter

Cost estimate

---

## Replay

Average replay per chapter

Total replay

Slowest resolver

---

## Database

Entity lookup

Relationship lookup

Alias lookup

Dictionary lookup

Snapshot lookup

Chapter lookup

Measure

```
average

median

max
```

---

## Memory

Peak RAM

Idle RAM

Memory after replay

Memory after parsing

Memory after snapshots

---

# 5. SQLite Query Audit

Take every query used by the reader.

Run

```
EXPLAIN QUERY PLAN
```

Verify

No table scans unless expected.

Indexes actually used.

Look for

```
SCAN TABLE
```

Replace with

```
SEARCH TABLE USING INDEX
```

if appropriate.

---

# 6. API Audit

Pretend backend and frontend are different teams.

Review every endpoint.

Questions

Does endpoint expose domain model?

or

Database schema?

Bad

```
GET aliases

GET relationships

GET events

GET trust

GET entity
```

Good

```
GET entity/{id}
```

returns

```
entity

aliases

relationships

events

status

importance

portrait

dictionary
```

Measure

Average response time.

Payload size.

---

# 7. Crash Recovery Audit

Simulate failures.

Interrupt after

Chapter 3

Chapter 50

Chapter 120

During replay

During snapshot generation

During OCR

During image parsing

During AI extraction

Restart.

Verify

No corruption.

No duplicate evidence.

No duplicate graph objects.

Resume works correctly.

---

# 8. Evidence Audit

Randomly sample

50 evidence records.

Check

source chapter

entity ids

timestamps

confidence

provenance

diagnostics

image references

OCR

Ensure

No mutable information.

No canonical truth.

Evidence remains purely observational.

---

# 9. Resolver Audit

Replay each resolver independently.

Verify

Identity

Location

Life status

Relationships

Titles

Aliases

Conflict resolution

Questions

Does replay order matter?

Shouldn't.

Can resolver be rerun?

Should.

Does resolver mutate evidence?

Never.

---

# 10. Snapshot Audit

Choose

Chapter

5

20

70

150

Last

For every snapshot verify

Characters known

Relationships known

Events known

Locations known

Dictionary entries

Images

No future information.

No spoiler leakage.

---

# 11. Image Pipeline Audit

Create books containing

Portraits

Maps

Decorations

Family trees

Glyphs

Symbols

Illustrations

Verify

Classification accuracy

OCR success

Fallback usage

Cache hits

Evidence generation

No graph mutation inside parser.

---

# 12. Cache Audit

Measure

Cache hit rate

Cache miss rate

Fingerprint invalidation

Parser version changes

Hash collisions

Verify

Parser changes invalidate cache.

Identical images reuse cache.

---

# 13. Dictionary Audit

Verify

Unknown term

↓

Reader lookup

↓

Context

↓

Terminology

↓

Fallback

↓

General dictionary

Ensure

No future chapters referenced.

No hallucinated definitions.

---

# 14. Logging Audit

Every major stage should log

Start

Finish

Duration

Errors

Recovery

Inputs

Outputs

Example

```
[Replay]
Chapter=24

Start

Duration=312ms

Entities=12

Relationships=8

Warnings=0
```

No meaningless logs.

---

# 15. Configuration Audit

Test

No Gemini key

Wrong Gemini key

Missing OCR

Missing OpenCV

Missing Pillow

Read-only directory

Invalid EPUB

Corrupted EPUB

Verify

Graceful degradation.

Useful messages.

No crashes.

---

# 16. Large Scale Stress Audit

Run

Several books.

Thousands of chapters.

Thousands of entities.

Thousands of aliases.

Thousands of relationships.

Monitor

Runtime

RAM

SQLite growth

Replay scaling

API scaling

---

# 17. Code Health Audit

Search for

```
TODO

FIXME

HACK

XXX

pass

print(

except:
```

Every occurrence should have justification or be removed.

---

# 18. Dependency Audit

Freeze versions.

Verify optional dependencies behave correctly.

Test with

Only mandatory packages installed.

Then

Everything installed.

Behavior should remain valid.

---

# 19. Security Audit

Verify

No arbitrary file writes.

No path traversal.

Safe EPUB extraction.

No SQL injection.

Parameterized queries only.

No unsafe deserialization.

---

# 20. Release Readiness Checklist

Before beginning the reader, all of these should be true:

* ✅ End-to-end pipeline succeeds without manual intervention.
* ✅ Replay is deterministic across repeated runs.
* ✅ Database integrity checks pass.
* ✅ All critical queries are indexed and benchmarked.
* ✅ API contracts are stable and frontend-oriented.
* ✅ Crash recovery resumes cleanly from interruptions.
* ✅ Evidence remains immutable and observational.
* ✅ Resolvers are idempotent and replay-safe.
* ✅ Snapshots are verified to be spoiler-free.
* ✅ Image pipeline behaves correctly across supported image types.
* ✅ Cache invalidation is verified.
* ✅ Dictionary never leaks future knowledge.
* ✅ Logs provide actionable diagnostics.
* ✅ Missing optional dependencies degrade gracefully.
* ✅ Large-book stress tests complete without instability.
* ✅ Codebase contains no unresolved development markers (`TODO`, `FIXME`, etc.) that affect correctness.
* ✅ Dependency versions are pinned for reproducibility.
* ✅ Basic security checks (file handling, SQL usage, input validation) pass.


