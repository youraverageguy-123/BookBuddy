# What Should Be Done Before Moving to Data Retention
## BookBuddy Backend Stabilization Checklist

Before building the data-retention layer, the backend needs to become a **stable source of truth**.  
Data retention should not be built on top of moving sand, because then all it retains is confusion in a prettier format.

The goal of this phase is to make sure BookBuddy can reliably produce **versioned, reader-safe chapter snapshots** from append-only evidence, without hardcoding story-specific rules.

---

## 1. Freeze the Core Resolver Architecture

The major resolvers should be stable enough that they stop changing shape every few days.

That means the core systems should already exist and be reasonably fixed in behavior:

- identity resolution
- ontology resolution
- life/death resolution
- landmark resolution
- relationship resolution
- reference quarantine
- language observation / translation hooks

### Why this matters
If these systems are still changing every time a new edge case appears, then the retention layer will inherit instability and become useless for reliable reader progress, snapshot history, or UI state.

### Principle
Do not invent a new special-case rule every time a book gets weird.  
Add evidence, update the resolver, and keep the architecture generic.

---

## 2. Make Chapter Output Canonical and Versioned

Each chapter should produce one canonical output object that represents:

- visible entities
- visible relationships
- visible life/death state
- visible landmarks
- unresolved mentions
- reference-only mentions
- background analysis status
- translator/dictionary status
- ontology changes
- legacy signals
- timeline-relevant changes

### Why this matters
Data retention needs a stable snapshot to store, compare, and restore.

If every chapter produces a slightly different shape, the retention layer becomes a compatibility nightmare.

### Principle
The chapter output should be a **versioned contract**, not a blob of random JSON that changes whenever the parser sneezes.

---

## 3. Make Chapter Processing Idempotent and Rerunnable

Chapter analysis should be safe to rerun.

If chapter 37 changes something earlier in the story, the system should know:

- what changed
- what must be invalidated
- what must be recomputed
- what can remain cached

### Why this matters
Without idempotency and rerun logic, you cannot safely support:
- background analysis
- progress tracking
- partial failures
- graph rebuilds
- incremental reading

### Principle
Never depend on “we already ran it once, so it must be fine.”  
That is how databases become haunted.

---

## 4. Add Checkpointing and Invalidation Rules

The backend should know how to checkpoint each chapter and how to invalidate derived state.

That includes:
- chapter analysis completion
- resolver snapshots
- event/relationship outputs
- life-status outputs
- landmark outputs
- translation/dictionary outputs

### Why this matters
Retaining state without invalidation is just a slow way to store bad history.

### Principle
Append-only evidence is good.  
Append-only garbage is still garbage.

---

## 5. Build a Small Regression Torture Suite

Before moving to data retention, add a fixed regression suite for the most dangerous classes of bugs:

- identity corruption
- same-surface different-referent bugs
- life/death flips
- retrospective event naming
- reference-only mentions
- non-human ontology
- landmark fragmentation
- cross-book contamination
- narrator belief vs reality
- hallucination vs literal status

### Why this matters
If these regressions are not locked down now, data retention will just preserve the bugs more efficiently.

### Principle
No hardcoded book-specific tests.  
Use generic synthetic examples and a few real torture books only as integration checks.

---

## 6. Stabilize the “Reader-Visible Snapshot” Contract

Before data retention, define clearly what a reader-facing snapshot contains.

It should be filtered and safe, not raw engine output.

A snapshot should answer:
- what the reader currently knows
- what is visible
- what is hidden
- what is unresolved
- what is confirmed
- what is only believed
- what is still background analysis

### Why this matters
Data retention is supposed to support user-facing state, not expose the whole internal graph directly.

### Principle
Separate engine truth from reader-visible truth.  
The graph may know many things. The reader does not.

---

## 7. Keep the Architecture Evidence-First

Every new feature before retention should reinforce the same pattern:

```text
mention -> interpretation -> evidence -> candidate -> resolver -> identity/snapshot -> explanation