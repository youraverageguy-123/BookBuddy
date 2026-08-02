# BookBuddy pre-v1 architecture decisions

These decisions are compatibility constraints for the stabilization release.

## Reader settings authority

`reader_settings.json` schema version 5 owns presentation and exact resume CFI. Global settings are inherited unless a book has `override=true`. Backend reader progress is derived library/analysis state and cannot replace a valid local CFI. The previous settings value is retained as a verified backup before every desktop write; legacy `reader-state.json` remains untouched after migration.

## Reader plugin ABI

Pre-v1 plugins are compile-time adapters using `reader-plugin-v1`. The manager owns capability checks, ordering, cancellation, normalized errors, theme, and accessibility. Dynamic or unsigned plugin loading is prohibited.

## Persistent background tasks

`tasks.db` is separate from canonical book databases. Stable task records carry leases, retries, safe user messages, and cancellation state. Heavy work uses staged/copy-on-write data and only promotes verified results atomically. Reader navigation never waits on background analysis.

## Search indexes

Reader text uses rebuildable, per-book FTS5 indexes keyed by the EPUB identity and tokenizer/schema version. Graph entity/event indexes remain canonical and are exposed through adapters. Reached text is the default search boundary; whole-book search requires explicit per-book confirmation.

## Cache identity and ownership

Derived resources use content hashes plus pipeline versions. Covers, images, dictionary results, web data, and search indexes are bounded caches; EPUBs, graph evidence, reader state, annotations, and settings are not. The component that acquires an EPUB instance, iframe, object URL, or decoded image also releases it.

## Database recovery

Operational databases use quick checks, bounded busy timeouts, WAL where compatible, verified rotating backups, passive checkpoints, and conservative optimization. Migration occurs transactionally after backup. Canonical graph truth is never guessed or auto-repaired; deterministic replay from stored evidence is the only repair path.
