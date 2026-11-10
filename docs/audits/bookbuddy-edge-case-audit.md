# BOOKBUDDY EDGE-CASE AUDIT
## Additional Problems to Solve Early Before They Become New Architecture Bugs

---

# HARD RULE

## NO HARDCODING EXAMPLES

Examples below are only there to explain failure classes.

Do **not** write code that special-cases any specific:

- character
- book
- title
- faction
- house
- family
- religion
- author style

If a fix needs named exceptions, the fix is wrong.

---

# 1. KINSHIP TERMS ARE NOT ALIASES

## Problem

Words like:

- father
- mother
- sister
- brother
- uncle
- aunt
- son
- daughter
- husband
- wife

can be:

- literal kinship
- religious title
- generic role
- scene reference
- POV-relative reference

---

## Why This Becomes a Bug

A kinship word is not a person.

If treated as alias or canonical identity, the graph will corrupt itself.

---

## Industry Solution

Create a dedicated **kinship resolution layer**.

Resolution order:

1. Is this a title?
2. Is this a kinship mention?
3. Is this a POV-relative reference?
4. Is this a named alias?
5. Is this a normal entity mention?

Kinship terms should resolve through relationship context, not alias matching.

---

# 2. RELATIONSHIPS ARE DIRECTIONAL

## Problem

Two entities can have different relationship values in opposite directions.

Examples of a relationship type only:

- student → teacher
- teacher → student
- friend → friend
- lover → lover
- enemy → enemy
- subordinate → leader

---

## Why This Becomes a Bug

A single symmetric score hides important narrative asymmetry.

One person may trust another while the other is plotting betrayal.

---

## Industry Solution

Store relationships as directional facts.

For each edge, keep:

- source entity
- target entity
- relation type
- trust score
- hostility score
- respect score
- fear score
- confidence
- chapter evidence

Do not collapse both directions into one score.

---

# 3. POV CONTEXT MUST RESOLVE FAMILY REFERENCES

## Problem

A statement like:

- “Father”
- “Mother”
- “Brother”
- “Sister”

may mean different people depending on who is speaking or being narrated.

---

## Why This Becomes a Bug

The same surface form can map to different entities in different POVs or different scenes.

---

## Industry Solution

Add POV-relative kinship resolution.

Use:

- speaker identity
- narrator identity
- scene participants
- recent mention history
- relationship graph

Example logic:

1. Determine POV or speaker.
2. Find the speaker’s known kinship graph.
3. Resolve family term against that graph.
4. If multiple candidates exist, mark ambiguous.
5. Do not create a new entity unless no plausible candidate exists.

---

# 4. TITLE WORDS ARE NOT PERSON NAMES

## Problem

Words like:

- father
- mother
- brother
- sister
- father superior
- mother superior
- priest
- pope
- archbishop

can be titles, roles, or kinship terms.

---

## Why This Becomes a Bug

Role-based mentions become mistaken for canonical names.

---

## Industry Solution

Separate:

- title resolution
- kinship resolution
- entity resolution

Do not use one shared alias rule for all of them.

---

# 5. SENTENCE-INITIAL CAPITALIZATION IS A WEAK SIGNAL

## Problem

A word capitalized only because it starts a sentence is not necessarily a proper noun.

---

## Why This Becomes a Bug

Sentence-initial capitalization causes false positives.

---

## Industry Solution

Treat capitalization as a weak feature only.

Use additional context:

- token neighborhood
- speaker
- dialogue marks
- nearby named entities
- entity type compatibility

Capitalization alone should never determine identity.

---

# 6. DIALOGUE REFERENCES NEED SPEAKER CONTEXT

## Problem

A term inside quoted speech can refer to:

- a parent
- a priest
- a title
- a nearby listener
- a scene participant

---

## Why This Becomes a Bug

Dialogue is not narratorial truth. It is often a fragment of conversation with ambiguous reference.

---

## Industry Solution

Track dialogue metadata:

- speaker
- addressee
- paragraph context
- previous mention window

Use dialogue-grounded resolution instead of raw string matching.

---

# 7. ROLE WORDS SHOULD NOT BECOME CANONICAL ENTITIES

## Problem

Role words like:

- father
- sister
- teacher
- student
- captain
- doctor
- brother

should not automatically become entities.

---

## Why This Becomes a Bug

Role mentions can be mistaken for people.

---

## Industry Solution

Classify mentions before resolution:

- role mention
- kinship mention
- title mention
- alias mention
- entity mention
- location mention
- group mention

Only entity mentions should enter normal entity resolution.

---

# 8. MULTI-POV BOOKS REQUIRE POV-SCOPED FACTS

## Problem

Different POVs can interpret the same relationship differently.

Examples:

- one character believes someone is a friend
- another character is secretly hostile
- one narrator knows a family tie
- another does not

---

## Why This Becomes a Bug

A single global relationship score erases narrative perspective.

---

## Industry Solution

Store relationships with scope:

- source POV
- source speaker
- scene scope
- confidence
- evidence excerpt

Allow per-POV relationship views.

---

# 9. UNRELIABLE OR LIMITED NARRATION EXISTS

## Problem

A narrator may not know the truth.

A narrator may lie, assume, or misunderstand.

---

## Why This Becomes a Bug

The graph may ingest narration as fact.

---

## Industry Solution

Add evidence source typing:

- observed fact
- spoken claim
- inferred claim
- narrator belief
- uncertain inference

Do not merge or hard-commit on weak narrator claims.

---

# 10. RELATIONSHIP POLARITY CAN DIFFER BY OBSERVER

## Problem

One character may see another as a friend.
That other character may see them as an obstacle.

---

## Why This Becomes a Bug

A single undirected relationship score cannot express narrative asymmetry.

---

## Industry Solution

Use two directed relationship records or a directed edge with separate per-direction attributes.

Example fields:

- trust_from_source_to_target
- trust_from_target_to_source
- respect
- hostility
- dependency
- betrayal_risk

---

# 11. FAMILY NAMES ARE NOT ALWAYS SAFE RESOLUTION ANCHORS

## Problem

Shared surnames can belong to:

- family members
- spouses
- unrelated people with same surname
- house names
- noble houses
- region names

---

## Why This Becomes a Bug

Surname-only matching causes false merges or false confidence.

---

## Industry Solution

Surname can be a candidate feature only.

Always require one or more of:

- full-name overlap
- kinship context
- relationship evidence
- scene co-occurrence
- title consistency
- POV consistency

Never merge on surname alone.

---

# 12. RELIGIOUS TITLES REQUIRE SEPARATE HANDLING

## Problem

Words like:

- father
- mother
- sister
- brother
- sister superior
- father superior

can be religious offices, not family roles.

---

## Why This Becomes a Bug

Kinship heuristics will misclassify clergy and similar roles.

---

## Industry Solution

Add title-category classification.

Categories:

- kinship
- religious title
- noble title
- occupational title
- alias
- descriptor

This prevents false family resolution.

---

# 13. CHARACTER TITLE EVOLUTION IS NORMAL

## Problem

A character may appear as:

- first name
- full name
- rank
- title
- epithet
- codename

across the story.

---

## Why This Becomes a Bug

The system may create duplicates for each form.

---

## Industry Solution

Temporal alias registry.

Track:

- first_seen
- last_seen
- support_count
- confidence
- type of alias
- evidence history

Allow aliases to graduate gradually.

---

# 14. AMBIGUOUS SHORT FORMS MUST STAY AMBIGUOUS

## Problem

Short forms like:

- father
- brother
- teacher
- captain
- Augustus
- Wilson
- Mustang
- Jackal

can be ambiguous.

---

## Why This Becomes a Bug

The resolver may guess too early.

---

## Industry Solution

Use explicit ambiguous state.

If multiple valid candidates exist:

- do not resolve
- do not merge
- do not create a canonical entity
- store an unresolved mention

Ambiguity is acceptable.
False certainty is not.

---

# 15. TIME-SKIP REINTRODUCTIONS WILL BREAK NAIVE RESOLUTION

## Problem

A character may disappear for a long time and reappear later.

---

## Why This Becomes a Bug

The system may treat the reintroduced entity as new.

---

## Industry Solution

Dormant entity reactivation.

Before creating a new entity, check:

- historical aliases
- old relationships
- past chapters
- location patterns
- house/faction history

Prefer reactivation over duplication.

---

# 16. LARGE CASTS REQUIRE BLOCKING, NOT BRUTE FORCE SEARCH

## Problem

Books with large casts will explode candidate counts.

---

## Why This Becomes a Bug

Every mention compares against too many entities.

Performance and precision both degrade.

---

## Industry Solution

Candidate blocking.

Only consider candidates that share:

- first token
- alias key
- surname key
- type
- title structure
- strong contextual overlap

Never search the whole graph blindly.

---

# 17. OMNIBUS FILES NEED BOUNDARY-AWARE MEMORY

## Problem

A single file may contain multiple titles or sub-books.

---

## Why This Becomes a Bug

Knowledge from one title bleeds into another too aggressively.

---

## Industry Solution

Track book boundaries explicitly:

- library-level id
- title id
- volume id
- chapter id
- session id

Inheritance should be weighted.
Local title evidence should override inherited evidence.

---

# 18. LOCATION LOGIC MUST STAY SEPARATE FROM PERSON LOGIC

## Problem

Location names and person names can overlap in surface structure.

---

## Why This Becomes a Bug

Person heuristics leaking into location heuristics causes nonsense merges.

---

## Industry Solution

Separate pipelines:

- person resolver
- group resolver
- location resolver
- title resolver
- kinship resolver

Shared utilities are fine.
Shared merge rules are not.

---

# 19. GROUPS AND HOUSES ARE NOT PEOPLE

## Problem

Groups, houses, factions, and organizations can share naming patterns with people.

---

## Why This Becomes a Bug

House names can look like surnames.
Faction names can look like titles.
Organizations can look like named persons.

---

## Industry Solution

Entity type is a hard constraint.

Never merge across:

- person ↔ group
- person ↔ location
- person ↔ event
- person ↔ object

If type is wrong, reject before scoring.

---

# 20. RELATIONSHIP EXTRACTION SHOULD NOT CREATE IDENTITY BY ITSELF

## Problem

Having a relationship like “father of” or “friend of” does not prove identity.

---

## Why This Becomes a Bug

Relationship similarity can overfit and create false identity merges.

---

## Industry Solution

Use relationship similarity as secondary evidence only.

Primary evidence:

- name structure
- alias evidence
- title evidence
- canonical form consistency

Secondary evidence:

- relationship overlap
- event overlap
- location overlap
- chapter proximity

---

# 21. EVENT EXTRACTION CAN GENERATE DUPLICATES

## Problem

The same event can be paraphrased differently across extractions.

---

## Why This Becomes a Bug

You get duplicate events, inflated counts, and repeated participants.

---

## Industry Solution

Event identity layer.

Use:

- participant overlap
- normalized summary
- location overlap
- chapter proximity
- evidence similarity

---

# 22. CONTEXT WINDOWS CAN CAUSE OLD KNOWLEDGE TO DOMINATE

## Problem

Known characters, memory cards, and prior events are useful, but can bias extraction too hard.

---

## Why This Becomes a Bug

The model may ignore genuine new mentions or over-map them to old entities.

---

## Industry Solution

Keep prompt context filtered and capped.

Use:

- relevance ranking
- chapter windowing
- deduplication
- confidence decay
- evidence prioritization

Do not dump the whole graph into the prompt.

---

# 23. SESSION DELETION IS A FIRST-CLASS NEED

## Problem

Old test sessions will pile up fast.

---

## Why This Becomes a Bug

Testing becomes messy.
Garbage sessions hide real results.
Disk usage balloons.

---

## Industry Solution

Implement:

- list sessions
- rename session
- soft delete
- hard delete
- restore
- purge deleted sessions

Expose through:

- CLI
- FastAPI

---

# 24. BROKEN SESSIONS SHOULD BE DETECTABLE

## Problem

A session can be partially missing or corrupted.

Examples:

- metadata exists, graph missing
- graph exists, cache missing
- EPUB missing, session folder exists

---

## Why This Becomes a Bug

The UI will lie about what is actually available.

---

## Industry Solution

Session integrity checks.

Validate:

- metadata
- graph.db
- chapter caches
- EPUB file
- continuity file

Mark broken sessions clearly.

---

# 25. CANONICAL NAME AND DISPLAY NAME SHOULD BE SEPARATE

## Problem

The internal best identity name may not be the best user-facing display name.

---

## Why This Becomes a Bug

A canonical form may be too long, too formal, or a variant spelling.

---

## Industry Solution

Store both:

- canonical_name
- display_name

Canonical is for graph identity.
Display is for UI.

---

# 26. RESOLUTION EVIDENCE SHOULD BE USER-REVIEWABLE

## Problem

Without explanation, debugging is guesswork.

---

## Why This Becomes a Bug

When something is wrong, you cannot tell why it happened.

---

## Industry Solution

Keep resolver evidence records.

Store:

- mention text
- candidate scores
- winner
- margin
- ambiguity reason
- evidence excerpt
- resolver version

This is necessary for debugging and trust.

---

# 27. GRAPH SANITY CHECKS SHOULD GROW OVER TIME

## Problem

Basic sanity checks are not enough for mature systems.

---

## Why This Becomes a Bug

A graph can pass simple checks and still be subtly corrupted.

---

## Industry Solution

Add invariants such as:

- no duplicate canonical names
- no self-alias
- no orphan alias
- no orphan event participant
- no person-location merge
- no person-group merge
- no spouse-to-spouse merge without strong evidence
- no role-only canonical names
- no unresolved mention promoted too early

---

# 28. PERFORMANCE METRICS SHOULD BE TRACKED EARLY

## Problem

Large books will stress resolution, indexing, and prompt context.

---

## Why This Becomes a Bug

A system that is logically correct can still become too slow to use.

---

## Industry Solution

Track:

- chapter processing time
- entity count
- alias count
- relationship count
- event count
- candidate count
- merge count
- resolver ambiguity count
- prompt size
- context size

Use these numbers to find regressions early.

---

# 29. THE RESOLVER SHOULD PREFER FALSE NEGATIVES OVER FALSE POSITIVES

## Problem

A conservative system can leave some mentions unresolved.

---

## Why This Becomes a Bug

Developers often overcorrect when they see unresolved items.

---

## Industry Solution

Keep unresolved mentions if needed.
Do not merge aggressively just to reduce ambiguity.
False negatives are recoverable.
False positives corrupt the graph.

---

# 30. FUTURE FEATURE WORK SHOULD WAIT UNTIL THESE ARE STABLE

## Do Not Rush Into

- frontend polish
- character cards
- relationship explorer
- timeline explorer
- maps
- fictional language tools
- OCR
- extra visualizations

These are valuable, but they sit on top of the identity layer.

If the identity layer is unstable, the UI only makes wrong data look pretty.

---

# FINAL VALIDATION TARGET

The system is ready for feature-first work when:

- kinship mentions resolve by POV and context
- titles are separated from identities
- directional relationships are stored cleanly
- ambiguous short forms do not corrupt the graph
- multi-POV books work without cross-contamination
- long time skips do not create duplicates
- omnibus boundaries are respected
- large casts stay performant
- sessions can be deleted cleanly
- resolver decisions are explainable
- new bugs become minor heuristic fixes, not architecture rewrites

