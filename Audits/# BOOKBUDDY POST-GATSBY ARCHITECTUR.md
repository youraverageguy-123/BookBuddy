# BOOKBUDDY POST-GATSBY ARCHITECTURE REVIEW

## Status After Entity Resolution Refactor + Gatsby Validation

---

# CRITICAL RULE

## DO NOT HARDCODE EXAMPLES

All examples in this document exist only to explain classes of problems.

Never write code specifically for:

* Tom Buchanan
* Wilson
* Augustus
* Mustang
* Jackal
* Darrow
* Gatsby

Solutions must generalize to any book, genre, language, naming convention, or cast size.

If a fix requires mentioning a specific character name in code, the fix is wrong.

---

# CURRENT STATUS

## RESOLVED

### Alias Resolution

Examples:

* Tom → Tom Buchanan
* Jordan → Miss Baker
* Mr. Carraway → Nick Carraway
* Mr. Wolfsheim → Meyer Wolfsheim

Result:

* Alias system functioning
* Merge pipeline functioning
* Evidence tracking functioning

Priority: COMPLETE

---

### False Positive Merge Protection

Examples:

* Husband ≠ Wife
* Family Member ≠ Family Member
* Relationship ≠ Identity

Result:

* Previous catastrophic merge bugs eliminated

Priority: COMPLETE

---

### Identity Resolution Architecture

Current State:

* Resolver-first architecture
* Evidence accumulation
* Ambiguity tracking
* Merge audit trail
* Reconciliation pipeline

Result:

Foundation appears stable.

Priority: COMPLETE

---

# HIGH PRIORITY REMAINING PROBLEMS

---

## 1. Partial Name Resolution

Current Example:

Wilson
George Wilson
Myrtle Wilson

Current Result:

System creates:

* Wilson
* George Wilson
* Myrtle Wilson

instead of resolving correctly.

---

### Why This Happens

System lacks robust partial-name resolution.

Single-token references are treated conservatively.

---

### Industry Solution

Build ambiguity-aware partial resolution.

Process:

Mention:

Wilson

↓

Find candidates:

George Wilson
Myrtle Wilson

↓

Cases:

Case A:

One candidate exists.

Resolve automatically.

Case B:

Multiple candidates exist.

Mark ambiguous.

Do NOT create entity.

Do NOT merge.

Store unresolved mention.

---

### Expected Impact

Eliminates:

* Wilson problem
* Augustus problem
* Family surname fragmentation

Priority: CRITICAL

---

## 2. Canonical Name Selection

Current Example:

Meyer Wolfshiem
Meyer Wolfsheim

Potentially choosing incorrect spelling.

---

### Why This Happens

Canonical selection based on frequency.

Frequency does not equal correctness.

---

### Industry Solution

Canonical name scoring.

Signals:

* Longest complete form
* Earliest complete form
* Most frequently repeated form
* Title-free form
* Full-name preference

Store:

canonical_name

and

display_name

separately.

---

### Expected Impact

Cleaner exports.
Cleaner UI.

Priority: HIGH

---

# FUTURE PROBLEMS LIKELY TO APPEAR

These should be anticipated now.

---

## 3. Multi-POV Books

Examples:

Different narrators.

POV switches.

---

### Failure Mode

Thoughts and observations attached to wrong narrator.

Character graph contamination.

---

### Industry Solution

Introduce:

POV Identity Layer

Every chapter stores:

* narrator_id
* narrator_confidence
* narrator_evidence

Relationships extracted from narrator context must inherit narrator identity.

---

### Validation Books

* Red Rising later books
* Wheel of Time
* Malazan

Priority: HIGH

---

## 4. Alias Evolution Over Time

Example Pattern:

Character gains:

* title
* rank
* nickname
* codename

during story progression.

---

### Failure Mode

Resolver creates new entities.

---

### Industry Solution

Temporal Alias Registry.

Alias table stores:

* first_seen
* last_seen
* support_count

Allow aliases to emerge gradually.

---

Priority: HIGH

---

## 5. Long Time Skip Reintroduction

Example Pattern:

Character disappears.

Returns hundreds of pages later.

---

### Failure Mode

Resolver creates duplicate entity.

---

### Industry Solution

Dormant Entity Resolution.

Consider:

* historical aliases
* historical relationships
* historical locations

before creating entity.

---

Priority: HIGH

---

## 6. Faction vs Character Ambiguity

Examples:

Group names.

Organizations.

Families.

Military units.

---

### Failure Mode

Faction becomes character.

Character becomes faction.

---

### Industry Solution

Explicit Entity Typing.

Types:

* Person
* Group
* Organization
* Location
* Object
* Event

Resolver never merges across types.

---

Priority: HIGH

---

## 7. Title-Based References

Example Pattern:

The title references multiple people.

---

### Failure Mode

Incorrect resolution.

---

### Industry Solution

Context-based title resolution.

Signals:

* current scene
* nearby mentions
* active participants

Require confidence threshold.

Otherwise ambiguous.

---

Priority: HIGH

---

# GRAPH QUALITY IMPROVEMENTS

---

## 8. Relationship Confidence

Current Risk

Single hallucinated extraction becomes relationship.

---

### Industry Solution

Relationship Evidence Accumulation.

Store:

* evidence count
* chapter count
* source excerpts

Relationship strength derived from evidence.

Not LLM confidence.

---

Priority: HIGH

---

## 9. Event Deduplication

Future Risk

Same event repeatedly extracted.

---

### Industry Solution

Event Identity Layer.

Event matching uses:

* participants
* location
* chapter proximity
* semantic similarity

---

Priority: HIGH

---

## 10. Location Deduplication

Future Risk

Multiple forms of same place.

---

### Industry Solution

Location Resolver.

Separate from entity resolver.

Never mix location and person pipelines.

---

Priority: HIGH

---

# SCALING RISKS

---

## 11. Large Cast Books

Examples:

* Malazan
* Wheel of Time

---

### Failure Mode

Candidate search explodes.

Resolver slows dramatically.

---

### Industry Solution

Candidate Blocking.

Only compare against:

* same surname
* same first token
* same alias key
* same entity type

Never compare against entire graph.

---

Priority: HIGH

---

## 12. Omnibus Books

Examples:

Multiple novels in one file.

---

### Failure Mode

Cross-book contamination.

---

### Industry Solution

Book Boundary Layer.

Track:

* title_id
* book_id
* chapter_id

Allow resolution to prefer local title context.

---

Priority: HIGH

---

## 13. Memory Growth

Future Risk

Huge databases.

---

### Industry Solution

Indexes on:

* aliases.alias_key
* entities.canonical_name
* relationships.source_id
* relationships.target_id
* events.event_key

Profile before optimization.

---

Priority: MEDIUM

---

# DATABASE IMPROVEMENTS

---

## 14. Soft Session Deletion

Current Risk

Accidental deletion.

---

### Industry Solution

Session Metadata Table.

Fields:

* is_deleted
* deleted_at

Periodic purge.

---

Priority: MEDIUM

---

## 15. Session Statistics

Store:

* entity_count
* relationship_count
* event_count
* chapter_count

Useful for debugging.

---

Priority: MEDIUM

---

## 16. Resolver Diagnostics

Current State

Good.

Can be improved.

---

Store:

* winning score
* second place score
* ambiguity reason
* resolution path

for every decision.

---

Priority: MEDIUM

---

# TESTING ROADMAP

After Wilson Fix

Run:

1. Gatsby (Final Validation)
2. Red Rising Book 1
3. Red Rising Omnibus
4. Third-Person Novel
5. The Stranger
6. The Plague
7. Dungeon Crawler Carl
8. Wheel of Time
9. Malazan

Goal:

Each new book should expose NEW bug classes.

No more architectural rewrites.

Only incremental resolver improvements.

---

# SUCCESS CRITERIA

Project can be considered architecturally stable when:

* No duplicate major characters
* No family-member merges
* No spouse merges
* No location/person merges
* Multi-POV handled correctly
* Long gaps handled correctly
* Omnibus boundaries handled correctly
* Large casts remain performant
* Resolver decisions explainable
* New bugs are heuristic bugs, not architecture bugs
