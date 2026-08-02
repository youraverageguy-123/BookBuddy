# What Should Be Done Before Data Retention
## Pre-Retention Stabilization and Operational Backbone

Before building the data-retention layer, BookBuddy needs one more round of **stabilization work** so the system is not just smart, but also explainable, measurable, replayable, and safe to extend.

The point is not to add more story features yet. The point is to make sure the existing evidence-first engine can survive repeated replays, version changes, and future UI layers without turning into a glorious garbage fire.

---

## 1. Freeze the Reader Contract

Define a single, explicit contract for what the reader is allowed to know at any chapter position.

This contract should clearly separate:

- known
- unknown
- believed
- disputed
- hidden
- future
- background analysis
- historical truth
- reader-visible truth

### Why this matters
Data retention will store reader-facing state. If the reader contract is vague, every downstream feature will leak hidden knowledge or re-invent visibility rules in a different way.

### Principle
The engine may know everything it has resolved. The reader may only see what is valid at the requested narrative position.

---

## 2. Standardize Resolver Explanations

Every resolver should expose a consistent explanation format.

Examples:

- IdentityResolver
- OntologyResolver
- ExistenceResolver
- LandmarkResolver
- RelationshipResolver
- Future Translator / Dictionary resolvers

Each should be able to answer:

- what it resolved
- why it resolved it
- what evidence supported it
- what evidence contradicted it
- what alternatives were rejected
- what confidence it assigned

### Why this matters
Once retention begins, users will want to ask “why did BookBuddy decide this?”  
If the system cannot explain itself, the retention layer becomes a pretty box around inscrutable output.

### Principle
No resolver should be a black box.

---

## 3. Add a Resolver Dependency Graph

Make explicit which resolvers depend on which others.

For example:

- identity may support ontology
- ontology may gate relationship eligibility
- life status may affect relationship visibility
- landmarks may depend on event identity
- snapshots depend on all resolved outputs

### Why this matters
When something changes, replay should know what must be invalidated and what can stay cached.

### Principle
Dependency should be explicit, not hidden in random call order.

---

## 4. Build Conflict Infrastructure as a Shared System

Stop treating conflicts as one-off bugs.

Create a generic conflict framework for:

- identity ambiguity
- ontology incompatibility
- life/death contradiction
- landmark fragmentation
- relationship contradiction
- reference-vs-entity collision

### Why this matters
Conflicts are not exceptions. They are part of the data model.

### Principle
A resolver should record uncertainty, not silently bury it.

---

## 5. Add Operational Metrics

The backend now needs to measure itself.

Track at least:

- extraction success rate
- resolver time
- replay time
- snapshot time
- checkpoint time
- unresolved ambiguity count
- merge rejection count
- conflict count
- cache hit rate
- rebuild frequency
- prompt/token cost
- evidence revision count

### Why this matters
Once the system becomes larger, manual debugging stops being enough.

### Principle
If you cannot measure it, you will eventually misread it.

---

## 6. Add Health Diagnostics

Create a single diagnostic command or endpoint that answers:

- is the graph sane?
- are there unresolved conflicts?
- are there checkpoint mismatches?
- did replay succeed?
- are resolver versions aligned?
- are snapshots current?
- are there orphan rows or stale revisions?

### Why this matters
Before data retention, you want a reliable “system health” view.

### Principle
Diagnostics should be boring, predictable, and brutally honest.

---

## 7. Freeze the Canonical Chapter Snapshot Contract

Before retention, define the canonical snapshot object per chapter.

It should be versioned and stable enough to include:

- visible entities
- visible relationships
- visible life status
- visible landmarks
- unresolved mentions
- reference-only mentions
- legacy signals
- language observations
- timeline state
- ontology state
- explanation references
- background-analysis status

### Why this matters
Retention is just storage if the snapshot shape is unstable.

### Principle
The snapshot is the public-facing compiled result, not a dump of internal tables.

---

## 8. Add Contract Tests, Not Just Smokes

You already have smoke tests. Good. Keep them.

But add a small set of **contract tests** that verify the long-lived architectural promises:

- strict as-of visibility
- evidence-first replay
- append-only history
- no hardcoded exceptions
- same-surface different-referent protection
- resolver version invalidation
- snapshot revision deduping
- hidden-state exclusion
- reader-safe filtering

### Why this matters
Smokes tell you the system runs.
Contract tests tell you the system still means what it is supposed to mean.

### Principle
Do not let “it compiles” become “it works.”

---

## 9. Add Version Manifests Everywhere Important

You already have versioning in several places. Keep extending that discipline.

Make sure these are tracked:

- prompt version
- cache version
- graph schema version
- normalization version
- resolver manifest version
- snapshot contract version
- replay version

### Why this matters
Retention will eventually need to know which data can be compared, reused, or rebuilt.

### Principle
Version changes should invalidate derived state explicitly.

---

## 10. Make Replay Modes Explicit

You already moved toward deterministic replay. Good. Make the modes explicit and boring.

Possible modes:

- normal replay
- full rebuild
- verify replay
- migrate replay
- debug replay

### Why this matters
Retention and background analysis both depend on knowing whether the system is replaying active evidence, rebuilding from scratch, or validating consistency.

### Principle
The system should never hide what kind of rerun it is doing.

---

## 11. Separate Engine Truth From Presentation Truth

This needs to remain a hard boundary.

- Engine truth = what the resolvers and evidence say
- Presentation truth = what the reader is allowed to see
- Retention truth = what gets stored as user-visible history

### Why this matters
If these get mixed, the UI will either spoil things or show stale nonsense.

### Principle
Resolvers think. Snapshots filter. Retention stores. UI presents.

---

## 12. Add Better Debug Visibility Before UI Work

Before building the retention UI, add a few debug views for yourself:

- explain entity
- explain landmark
- explain life status
- explain relationship
- explain snapshot
- show evidence revisions
- show invalidations
- show checkpoint history

### Why this matters
If you cannot inspect the logic, you will waste time guessing where the bug lives.

### Principle
Debugging tools are infrastructure, not luxury.

---

## 13. Keep Hardcoding Out of the Core

No book-specific names.
No character-specific rules.
No title-specific exceptions.
No one-off merge hacks.
No “just this one book” logic.

### Why this matters
Hardcoding is the fastest way to make a fix that works today and breaks three other books tomorrow.

### Principle
If the solution needs a named example, the solution is probably wrong.

---

## 14. Make Background Analysis a First-Class Workflow

Before retention, make sure background processing is truly stable.

It should support:

- append evidence first
- replay second
- invalidate derived state when needed
- recover from failed runs
- preserve checkpoints
- promote only on success

### Why this matters
Retention will rely on these outputs. If background processing is unstable, retention will just preserve the instability more elegantly.

### Principle
Background analysis should be resumable, repeatable, and deterministic.

---

## 15. Add a Backend Stability Milestone

Before retention, the project should reach a point where you can say:

- the resolvers are stable
- replay is deterministic
- snapshots are canonical
- diagnostics are reliable
- conflicts are visible
- versioning is enforced
- reader visibility is defined

### Why this matters
That is the real “go” signal for retention.

### Principle
Do not move to retention just because the code exists. Move when the contract is stable.

---

## Recommended Order Before Data Retention

1. Freeze reader contract
2. Standardize resolver explanations
3. Add dependency graph
4. Formalize conflicts
5. Add operational metrics
6. Add health diagnostics
7. Finalize chapter snapshot contract
8. Add contract tests
9. Lock version manifests
10. Make replay modes explicit
11. Separate engine truth from presentation truth
12. Add debug views
13. Keep hardcoding out of the core
14. Stabilize background analysis
15. Declare the backend stable enough for retention

---

## Final Principle

Before data retention, BookBuddy should be able to answer:

- What does the reader know?
- Why does the system believe it?
- Which resolver said so?
- What evidence supports it?
- What changed since the last replay?
- Is the output stable enough to retain?

If the answer to any of those is unclear, the retention layer is too early.

Build the contract first.  
Store history second.  
Do not preserve confusion just because it is versioned.