# BOOKBUDDY ADDITIONAL RISK REVIEW

## Extra Problems to Solve Early Before They Become New Architecture Bugs

---

# HARD RULE

## NO HARDCODING EXAMPLES

Examples below are only there to explain the category of failure.

Do **not** write code that special-cases:

* Tom Buchanan
* Wilson
* Augustus
* Mustang
* Jackal
* Gatsby
* Red Rising
* Gatsby-style surnames
* any specific book, title, or character

If a fix requires named exceptions, the fix is wrong.

---

# 1. SESSION LIFECYCLE IS INCOMPLETE

## Problem

Sessions can be created and loaded, but old sessions remain forever unless manually cleaned.

This causes:

* cluttered library folders
* stale graphs
* stale chapter caches
* confusion during testing
* accidental reuse of bad test sessions

---

## Why This Becomes a Bug

Once you start testing many books and many iterations, session sprawl becomes its own kind of technical debt.

Old bad sessions hide good results.

---

## Industry Solution

Add proper session lifecycle management.

Must include:

* list sessions
* rename session
* soft delete session
* hard delete session
* restore session
* purge deleted sessions

Prefer soft delete first, then purge later.

---

# 2. SESSION METADATA AND FILE SYSTEM CAN DRIFT APART

## Problem

A session may exist in metadata but not on disk, or vice versa.

Examples:

* session_state.json says session exists
* folder is gone
* graph.db is missing
* chapter cache is incomplete

---

## Why This Becomes a Bug

The CLI and API may show phantom sessions.

Users think data exists when it does not.

---

## Industry Solution

Add session integrity checks.

Validate:

* metadata
* database file
* chapter cache
* EPUB file
* continuity file

Mark broken sessions clearly.

Never silently assume the session is valid.

---

# 3. INHERITED SERIES GRAPH CAN CONTAMINATE NEW BOOKS

## Problem

Cross-book inheritance is useful, but dangerous.

If inherited too aggressively, old entity state leaks into the new book.

---

## Why This Becomes a Bug

A new title may reuse the same token patterns but refer to completely different identities.

Cross-book contamination is especially dangerous in series and omnibus workflows.

---

## Industry Solution

Use boundary-aware inheritance.

Track:

* title_id
* book_id
* volume_id
* source session
* inherited confidence

Allow inherited knowledge, but penalize it relative to local evidence.

Local evidence should always win.

---

# 4. PARTIAL NAME RESOLUTION STILL NEEDS AMBIGUITY CONTROL

## Problem

Short names are dangerous.

Examples:

* surname only
* first name only
* title only
* role only

These can refer to multiple entities.

---

## Why This Becomes a Bug

If the resolver guesses too early, it creates duplicates.
If it guesses too aggressively, it merges wrong identities.

---

## Industry Solution

Use ambiguity-aware resolution.

Logic:

* one strong candidate: resolve
* multiple plausible candidates: ambiguous
* no strong candidate: create unresolved mention, not entity

Never force a guess just because the mention is short.

---

# 5. NARRATOR / POV ENTITY SHOULD BE A FIRST-CLASS CONCEPT

## Problem

Different books use:

* first-person narrator
* unnamed narrator
* limited third-person narrator
* rotating POV
* multi-POV chapter structure

---

## Why This Becomes a Bug

Without explicit narrator handling:

* thoughts get attached to wrong entity
* chapter context leaks across POV boundaries
* narrator may be mistaken for a regular character
* unnamed POV promotions become inconsistent

---

## Industry Solution

Track narrator state per chapter.

Store:

* narrator entity
* narrator confidence
* narrator type
* POV source evidence

Treat narrator resolution separately from normal character resolution.

---

# 6. THIRD-PERSON LIMITED CAN STILL LEAK CONTEXT

## Problem

Even without first-person narration, a chapter may only know the world through one character.

---

## Why This Becomes a Bug

The system may wrongly treat all mentions in the chapter as equally visible to all characters.

That corrupts relationship inference and memory cards.

---

## Industry Solution

Add chapter visibility scope.

Entities and events should record:

* observed_by
* narrator_scope
* scene_scope

This lets the graph know what was actually knowable in the chapter.

---

# 7. RELATIONSHIP EXTRACTION NEEDS ROLE NORMALIZATION

## Problem

Relationship labels like:

* husband
* wife
* brother
* friend
* enemy
* leader
* subordinate

are useful, but messy.

---

## Why This Becomes a Bug

A role mention is not an identity mention.

If a role phrase gets treated like a person or alias, the graph corrupts itself.

---

## Industry Solution

Normalize relationships separately from identities.

Use:

* subject
* object
* relation type
* evidence
* chapter
* confidence

Do not allow role labels to become canonical names.

---

# 8. EVENT EXTRACTION CAN CREATE DUPLICATE EVENTS

## Problem

The same event can be extracted in slightly different wording.

---

## Why This Becomes a Bug

You get:

* duplicate events
* inflated event counts
* duplicated participants
* repeated causal chains

---

## Industry Solution

Add event identity resolution.

Use:

* normalized summary
* participants
* chapter proximity
* location overlap
* evidence overlap

Event deduplication should be as formal as entity deduplication.

---

# 9. ENTITY TYPE DRIFT IS A FUTURE RISK

## Problem

An entity may shift from one type to another over time.

Examples:

* person becomes title-holder
* group becomes institution
* role becomes individual reference
* location becomes settlement, then building, then region

---

## Why This Becomes a Bug

Type changes can break resolver assumptions and graph queries.

---

## Industry Solution

Allow controlled type voting and type drift only with evidence.

Keep:

* current type
* type history
* type confidence

Never overwrite type silently.

---

# 10. CANONICAL NAME VS DISPLAY NAME SHOULD BE SEPARATE

## Problem

The best canonical identity name is not always the best display name.

---

## Why This Becomes a Bug

A canonical form may be:

* too formal
* too long
* slightly incorrect spelling variant
* not user-friendly

---

## Industry Solution

Store both:

* canonical_name
* display_name

Canonical name should be stable for internal identity.
Display name should be optimized for UI.

---

# 11. LOCATION RESOLUTION CAN BREAK IF PERSON LOGIC LEAKS INTO IT

## Problem

Location names and person names behave differently.

---

## Why This Becomes a Bug

If person-style heuristics influence location merging, or vice versa, the graph starts making nonsense merges.

---

## Industry Solution

Keep separate pipelines for:

* people
* groups
* locations

Shared utilities are fine.
Shared merge logic is not.

---

# 12. SEARCH TERM INDEXING NEEDS CAREFUL GROWTH CONTROL

## Problem

Search terms grow rapidly with:

* aliases
* titles
* n-grams
* canonical forms
* event search terms

---

## Why This Becomes a Bug

Huge books produce massive search-term tables.
Candidate retrieval can slow down.
Memory can balloon.

---

## Industry Solution

Use blocking and indexing carefully.

Keep:

* alias_key index
* canonical_name index
* entity_type index
* status index

Avoid full graph scans.
Limit search-term explosion with controlled n-grams.

---

# 13. AMBIGUOUS MENTIONS SHOULD BE STORED, NOT FORCED INTO ENTITIES

## Problem

A surface form may be real but unresolved.

---

## Why This Becomes a Bug

If unresolved mentions are immediately converted into entities, fragmentation returns.

---

## Industry Solution

Add an unresolved mention state.

Store:

* mention_text
* chapter
* candidate entities
* confidence
* ambiguous flag

Only create a new entity when no plausible existing candidate exists.

---

# 14. MERGE AUDIT SHOULD SUPPORT ROLLBACK THINKING

## Problem

A bad merge can still happen in edge cases.

---

## Why This Becomes a Bug

Without recoverability, one bad merge ruins the graph.

---

## Industry Solution

Keep merge audit rich enough to replay or inspect decisions.

Store:

* surviving entity
* losing entity
* score
* evidence
* resolver version
* reason

If possible, keep rollback support for debugging builds.

---

# 15. CONFLICT RECORDS NEED CLEAR PRIORITY

## Problem

Conflicts can accumulate quickly:

* alias collisions
* merge conflicts
* type conflicts
* title conflicts
* relationship contradictions

---

## Why This Becomes a Bug

If everything is treated equally, the review queue becomes noise.

---

## Industry Solution

Prioritize conflicts by severity:

1. identity corruption
2. false merge
3. type conflict
4. alias collision
5. relationship contradiction
6. low-risk review items

---

# 16. CHAPTER-LEVEL CACHE CAN STALE OUT

## Problem

Cached chapter JSONs are immutable, which is good, but if the graph logic changes, cached extracted data may still replay older assumptions.

---

## Why This Becomes a Bug

You can rebuild the graph with better logic, but stale extraction assumptions might still be hiding upstream.

---

## Industry Solution

Version the cache properly.

Track:

* cache_version
* prompt_version
* model_name
* normalization_version
* graph_schema_version

If those change materially, expect different replay results.

---

# 17. CONTEXT BUILDING CAN ACCIDENTALLY OVER-FAVOR OLD KNOWLEDGE

## Problem

Prompt context pulls in:

* known characters
* memory cards
* relationships
* prior event context

That is useful, but can bias extraction too hard.

---

## Why This Becomes a Bug

The model may overfit to old context and miss genuine new identities.

---

## Industry Solution

Balance context blocks carefully.

Prefer:

* filtered context
* deduplicated lines
* relevance-ranked entity cards
* limited history windows

Do not dump the entire graph into prompt context.

---

# 18. SESSION NAME QUALITY MATTERS

## Problem

Long, chaotic session names are funny once and annoying forever.

They leak into paths, logs, folders, and debugging pain.

---

## Why This Becomes a Bug

Poor session naming creates unreadable folder structures and makes cleanup harder.

---

## Industry Solution

Sanitize names and optionally support:

* human-readable label
* internal session id
* timestamp
* test tag

Do not rely on raw user input as the only identifier.

---

# 19. FILE CLEANUP NEEDS TO MATCH DELETE SEMANTICS

## Problem

Deleting a session should not leave behind:

* stale EPUB copies
* orphan chapter caches
* old exports
* graph.db
* logs
* session metadata

---

## Why This Becomes a Bug

The system appears deleted, but disk usage keeps growing.

---

## Industry Solution

Delete sessions recursively and atomically.

Support dry-run first.
Then confirm.
Then remove all linked artifacts.

---

# 20. LARGE CAST TESTING SHOULD BECOME A PERFORMANCE TEST TOO

## Problem

Once the resolver works, the next issue is scale.

---

## Why This Becomes a Bug

Wheel of Time and Malazan are not just entity-resolution tests.
They are search, indexing, and candidate-generation stress tests.

---

## Industry Solution

Track performance metrics:

* resolution time per chapter
* merge time
* candidate count
* entity count
* alias count
* event count
* prompt context size

This becomes an early warning system for scale regression.

---

# 21. REDUCED FALSE MERGES ARE A FEATURE, NOT A BUG

## Problem

A conservative resolver may leave a few ambiguous mentions unresolved.

---

## Why This Becomes a Bug

Developers often panic and loosen thresholds too soon.

---

## Industry Solution

Treat unresolved ambiguity as acceptable if it avoids corruption.

It is better to have:

* one ambiguous surname mention

than:

* a person merged into their spouse
* a title merged into a human
* a location merged into a character

---

# 22. EXPORTS SHOULD BE OWNED BY THE GRAPH VERSION

## Problem

Exported JSON snapshots can drift from current schema and logic.

---

## Why This Becomes a Bug

Old exports can be misread as current truth.

---

## Industry Solution

Every export should include:

* graph schema version
* cache version
* prompt version
* model version
* export timestamp

Never treat exports as schema-free truth.

---

# 23. GRAPH SANITY SHOULD KEEP EXPANDING

## Problem

Current invariant checks are useful, but not enough for future books.

---

## Why This Becomes a Bug

A system can pass simple invariants and still have subtle identity corruption.

---

## Industry Solution

Add more invariants over time:

* no duplicate canonical names
* no self-alias
* no orphan alias
* no orphan event participant
* no person-location merge
* no person-group merge
* no spouse-to-spouse merge without evidence
* no role-only canonical names
* no ambiguous mention upgraded too early

---

# 24. FEATURE WORK SHOULD WAIT UNTIL THESE ARE STABLE

## Do Not Rush Into

* frontend polish
* fancy graphs
* relationship visualization
* map parsing
* fictional language tools
* OCR extras
* long-term memory UI

Those are valuable, but they sit on top of the identity layer.

If identity is unstable, the UI will only display confidence in wrong answers.

---

# RECOMMENDED NEXT TEST ORDER

1. Gatsby final validation
2. Wilson-style partial-name validation
3. Red Rising book 1
4. Red Rising omnibus
5. Multi-POV novel
6. Third-person limited novel
7. First-person unnamed narrator book
8. The Stranger
9. The Plague
10. Dungeon Crawler Carl
11. Wheel of Time
12. Malazan

The goal is not perfection.

The goal is to discover new bug classes one by one without needing major architecture rewrites.

---

# FINAL SUCCESS CONDITION

The system is ready for feature-first work when:

* major names resolve correctly
* partial names are handled safely
* ambiguous mentions do not corrupt the graph
* POV handling is reliable
* long time skips do not explode identity
* omnibus boundaries are respected
* old sessions can be deleted cleanly
* graph performance stays usable on large casts
* future bugs are minor heuristic tuning, not structural failure


