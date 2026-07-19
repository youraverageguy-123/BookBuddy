# Pre-Retention Core Contracts

BookBuddy processes narrative material through a durable evidence-first flow:

`mention -> interpretation -> evidence -> candidate -> resolver -> snapshot -> explanation`

## Canonical Objects

- **Evidence** is an immutable chapter extraction revision. It is the source of truth for replay.
- **Mention** is a source surface recorded before it is promoted into an entity or relationship.
- **Candidate** is a resolver option that remains reviewable until evidence supports a decision.
- **Resolver decision** is an append-only explanation record with a decision, confidence, evidence references, rejected alternatives, visibility, chapter, and resolver version.
- **Snapshot** is the compiled reader-safe result for one chapter. It is derived state, never evidence.
- **Revision** is a new immutable evidence or snapshot version. Revisions supersede active derived output without deleting history.
- **Checkpoint** records replay progress and hashes. It is operational metadata, not story truth.
- **Manifest** is the version contract for prompt, cache, schema, normalization, resolvers, snapshot format, and replay behavior.
- **Conflict** is an append-only unresolved or reviewed contradiction. It is evidence about uncertainty, not an exception to hide.

## Reader Contract

`reader_snapshot_v2` is the sole public reader contract. It is strictly scoped to its `as_of_chapter` and can expose only `known`, `believed`, `disputed`, or `unknown` reader state. Hidden, future, and engine-only information remains outside the snapshot. Raw chapter evidence remains a backward-compatible internal route and is not a UI contract.

Resolvers determine engine truth. Snapshot builders filter resolver output for visibility. Retention, when introduced, stores reader-visible snapshots. Presentation renders retained snapshots without re-inferring story facts.

## Replay Contract

- `normal` consumes open invalidations and refreshes derived state when required.
- `full` rebuilds all active evidence-derived state in staging and promotes only after invariants pass.
- `verify` compares staged derived state without replacing the live graph.

Legacy string caches, historical evidence revisions, and prior snapshot versions remain readable. New work never rewrites those source records.

## Invariants

1. Evidence and resolver decisions are append-only.
2. Resolvers do not mutate evidence revisions.
3. Snapshots are derived and versioned; checkpoints are not truth.
4. Reader snapshots never contain future, hidden, or raw engine evidence.
5. Resolver dependencies are declared and version changes invalidate downstream contracts explicitly.
6. Conflicts stay reviewable until resolved; ambiguity is not silently converted into certainty.
7. Landmarks require compatible evidence before identity linking or merging.
8. No resolver behavior depends on book, title, character, or species-specific names.
