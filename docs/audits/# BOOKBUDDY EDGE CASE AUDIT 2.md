# BOOKBUDDY EDGE CASE AUDIT 2
## Extra Failure Modes That Can Break the System

## HARD RULE
Examples below are only illustrations of bug classes.

Do **not** hardcode fixes for any specific:
- character
- book
- title
- house
- family
- faction
- author style

If the code needs named exceptions, the code is wrong.

---

## 1. SAME NAME, DIFFERENT PEOPLE ACROSS BOOKS

### Problem
A name may exist in multiple books, volumes, or sessions.

Example:
- one book has a character with a common name
- another book has a different character with the same name

### Failure Mode
The graph merges across books or inherited sessions.

### Why It Hurts
Cross-book contamination poisons the entire library graph.

### What to Prevent
Resolution must respect:
- title boundary
- volume boundary
- session boundary
- inheritance confidence

---

## 2. SAME NAME, DIFFERENT PEOPLE IN THE SAME BOOK

### Problem
Multiple characters can share:
- first name
- surname
- title
- nickname
- honorific

### Failure Mode
Short forms merge into the wrong person.

### Why It Hurts
This creates silent corruption that is hard to notice.

### What to Prevent
Use ambiguity-aware partial resolution.
If multiple candidates exist, do not force a merge.

---

## 3. FAMILY TERMS THAT ARE NOT FAMILY TERMS

### Problem
Words like:
- father
- mother
- sister
- brother
- uncle
- aunt

can be:
- kinship
- religious title
- role
- generic address
- POV-relative reference

### Failure Mode
The system treats them as aliases or canonical names.

### Why It Hurts
Clergy, family members, and addressed persons get mixed together.

### What to Prevent
Create a kinship/title resolution layer separate from alias resolution.

---

## 4. POV-DEPENDENT FAMILY REFERENCES

### Problem
"Father" means different people depending on who is speaking or narrating.

### Failure Mode
The wrong father gets resolved.

### Why It Hurts
Family graph gets attached to the wrong person.

### What to Prevent
Use:
- speaker
- POV
- scene participants
- recent mentions
- kinship graph

---

## 5. DIRECTED RELATIONSHIPS ARE NOT SYMMETRIC

### Problem
A relationship can differ by direction.

Example class:
- student -> teacher
- teacher -> student
- friend -> friend
- enemy -> enemy
- admirer -> idol

### Failure Mode
A single symmetric score hides betrayal, hierarchy, and hidden hostility.

### Why It Hurts
Relationship graph becomes emotionally and narratively wrong.

### What to Prevent
Store relationship edges as directional facts.

---

## 6. HIDDEN BETRAYAL / FALSE TRUST

### Problem
One character may think another is a friend while the other is plotting betrayal.

### Failure Mode
The graph assigns one relationship score for both directions.

### Why It Hurts
Narrative tension gets destroyed.

### What to Prevent
Keep separate source-to-target and target-to-source relationship views.

---

## 7. TITLE WORDS THAT LOOK LIKE NAMES

### Problem
Words like:
- father
- mother
- doctor
- captain
- king
- queen
- sir
- lord

can be:
- titles
- roles
- kinship
- actual names in unusual contexts

### Failure Mode
Role mentions become canonical entities.

### Why It Hurts
Random roles become people.

### What to Prevent
Role/title classification before identity resolution.

---

## 8. CAPITALIZATION IS NOT ENOUGH

### Problem
Sentence-initial capitalization makes many non-names look like names.

### Failure Mode
The parser promotes common nouns into entities.

### Why It Hurts
False character creation explodes.

### What to Prevent
Treat capitalization as a weak feature only.

---

## 9. DIALOGUE AMBIGUITY

### Problem
In quoted speech, references can be:
- the speaker’s family member
- the listener
- a title
- a religious figure
- a nearby named entity

### Failure Mode
The system resolves dialogue references using raw string matching only.

### Why It Hurts
Dialogue is where coreference gets messy.

### What to Prevent
Use speaker and addressee context for dialogue resolution.

---

## 10. INDIRECT SPEECH

### Problem
A character may report what someone else said.

### Failure Mode
The system treats reported speech as direct speaker evidence.

### Why It Hurts
Wrong relationship and POV attribution.

### What to Prevent
Track reported speech separately from direct narration.

---

## 11. NAME CHANGES OVER TIME

### Problem
Characters may gain:
- title
- rank
- marriage name
- codename
- epithet
- office
- faction role

### Failure Mode
Each form becomes a separate entity.

### Why It Hurts
Fragmentation returns.

### What to Prevent
Temporal alias evolution with support counts.

---

## 12. LONG TIME SKIPS

### Problem
A character disappears for many chapters or books and returns later.

### Failure Mode
The resolver creates a new entity because the old one is not active in context.

### Why It Hurts
Long-form novels are full of reintroductions.

### What to Prevent
Dormant entity reactivation using historical evidence.

---

## 13. OMNIBUS / MULTI-TITLE FILES

### Problem
One uploaded file may contain multiple novels or volumes.

### Failure Mode
Identity leaks across title boundaries.

### Why It Hurts
A reused name in volume 2 can corrupt volume 1 state.

### What to Prevent
Track:
- title_id
- volume_id
- book_id
- session_id

Use boundary-aware inheritance.

---

## 14. MULTI-POV BOOKS

### Problem
Different chapters may follow different narrators or focal characters.

### Failure Mode
The graph attaches thoughts, kinship, and relationships to the wrong POV.

### Why It Hurts
POV errors poison everything downstream.

### What to Prevent
Store narrator identity and POV scope per chapter.

---

## 15. UNNAMED POV PROMOTION

### Problem
The narrator may start unnamed and later become known.

### Failure Mode
The unnamed placeholder stays forever or merges badly.

### Why It Hurts
The narrator graph becomes unstable.

### What to Prevent
Use explicit narrator promotion logic.

---

## 16. THIRD-PERSON LIMITED VS OMNISCIENT

### Problem
Narration style affects what is knowable.

### Failure Mode
The system treats all mentions as equally visible and known.

### Why It Hurts
Relationship and event inference become too confident.

### What to Prevent
Track narrative scope and visibility.

---

## 17. HALLUCINATED LITERARY REFERENCES

### Problem
## Historical / Scientific / Cultural Reference Layer

Problem:

Named references may appear in text but are not participants in the narrative.

Examples:

- Newton's Laws
- Einstein's Theory
- Achilles
- Zeus
- Napoleon
- Caesar
- Shakespeare
- The Great Gatsby
- World War II
- French Revolution
- Mozart

Risk:

Reference entities become active story characters.

Industry Solution:

Introduce distinction between:

1. Mentioned Entity
2. Active Narrative Entity

Only Active Narrative Entities may:

- participate in relationships
- participate in events
- become POV candidates
- enter merge pipeline

Mentioned Entities remain attached as contextual references only.
Books mention:
- Newton’s laws
- Einstein
- Caesar
- Achilles
- Shakespeare
- World War II
- other historical, scientific, or mythological references

### Failure Mode
The graph treats them as active story participants.

### Why It Hurts
Dead philosophers become cast members.

### What to Prevent
Separate:
- active narrative entities
- historical references
- conceptual references
- works of art
- scientific terms

---

## 18. WORKS OF ART INSIDE THE STORY

### Problem
Stories mention:
- books
- poems
- songs
- films
- paintings
- laws
- theorems
- equations

### Failure Mode
The title or named concept becomes a person.

### Why It Hurts
Entity typing gets polluted.

### What to Prevent
Add a reference/entity subtype layer.

---

## 19. PLACE NAMES THAT LOOK LIKE PEOPLE

### Problem
Some place names resemble person names.

### Failure Mode
Locations get treated as characters or vice versa.

### Why It Hurts
Person-location merges are catastrophic.

### What to Prevent
Hard type separation.
Never merge across person and location types.

---

## 20. PEOPLE NAMED AFTER PLACES OR IDEAS

### Problem
A person may be named after:
- a place
- a law
- a scientific figure
- a historical event

### Failure Mode
The system confuses the named referent with the story entity.

### Why It Hurts
Context leakage.

### What to Prevent
Use narrative participation to distinguish entity type.

---

## 21. RELIGIOUS TITLES AND CLERICAL ADDRESS

### Problem
Words like:
- Father
- Mother
- Sister
- Brother

can refer to clergy or religious roles.

### Failure Mode
Kinship resolution incorrectly assigns them as family members.

### Why It Hurts
Religious titles are not family trees.

### What to Prevent
Title-category classification before kinship resolution.

---

## 22. SPEAKER-DEPENDENT KINSHIP

### Problem
"Father" may refer to different entities depending on who says it.

### Failure Mode
The wrong family member is resolved.

### Why It Hurts
POV and relationship graphs diverge.

### What to Prevent
Kinship must be resolved relative to the speaker or POV.

---

## 23. RELATIONSHIP TERMS USED AS ADDRESS

### Problem
A character may say:
- father
- son
- sister
- brother
- captain
- doctor

as direct address, not identity.

### Failure Mode
Address terms become canonical entities.

### Why It Hurts
The graph creates fake people.

### What to Prevent
Distinguish:
- address term
- title
- kinship
- identity

---

## 24. PLURAL REFERENCES

### Problem
Mentions like:
- the brothers
- the sisters
- the guards
- the nobles
- the Augustuses

may refer to groups, not individuals.

### Failure Mode
Plural mentions get collapsed into one person.

### Why It Hurts
Group semantics are lost.

### What to Prevent
Plural/group resolution layer.

---

## 25. COLLECTIVE NOUNS

### Problem
Words like:
- family
- house
- faction
- clan
- order
- school
- team

can refer to a group, not a person.

### Failure Mode
Group becomes person or alias.

### Why It Hurts
Group graph and person graph merge.

### What to Prevent
Strict group typing and group alias logic.

---

## 26. HOUSE / DYNASTY NAMES

### Problem
A house name may act like:
- surname
- faction
- noble line
- organization

### Failure Mode
House identity is mistaken for a person identity.

### Why It Hurts
One-token references become dangerous.

### What to Prevent
House/dynasty classification separate from person resolution.

---

## 27. EPTIETS AND CODENAMES

### Problem
A character may be known by:
- a title
- a codename
- an epithet
- a nickname
- a battlefield name

### Failure Mode
Each epithet becomes a separate entity.

### Why It Hurts
Fragmentation returns in a new costume.

### What to Prevent
Alias discovery across epithets with gradual support accumulation.

---

## 28. QUOTED NAMES VS ACTUAL ENTITY MENTIONS

### Problem
A name can appear in:
- dialogue
- citation
- story title
- book title
- footnote
- example text

### Failure Mode
Non-story mentions become graph nodes.

### Why It Hurts
Metadata gets treated as narrative content.

### What to Prevent
Mention source typing:
- narration
- dialogue
- citation
- title
- footnote
- metadata

---

## 29. FOOTNOTES, EPISTLES, APPENDICES, AND NON-CHAPTER MATERIAL

### Problem
Books often contain non-standard text sections.

### Failure Mode
The parser treats them like normal narrative chapters.

### Why It Hurts
Characters from side material contaminate main graph state.

### What to Prevent
Section-type detection before analysis.

---

## 30. OCR / EPUB EXTRACTION NOISE

### Problem
Text extraction can introduce:
- broken hyphenation
- line wrap artifacts
- missing punctuation
- merged words
- duplicate lines
- headers/footers
- page numbers

### Failure Mode
Noise becomes named entities or relationships.

### Why It Hurts
The graph gets polluted at source.

### What to Prevent
Extraction cleanup before LLM input.

---

## 31. ABBREVIATIONS AND INITIALS

### Problem
Names with initials or abbreviated forms can collide with ordinary words.

### Failure Mode
The resolver treats abbreviations as new entities or wrong aliases.

### Why It Hurts
Initial-heavy naming systems break naive token matching.

### What to Prevent
Normalization that preserves identity but strips noise carefully.

---

## 32. NON-LATIN SCRIPTS AND TRANSLITERATION

### Problem
Some books use:
- transliterated names
- non-Latin scripts
- accented names
- alternate spellings across editions

### Failure Mode
Same entity appears as several unrelated strings.

### Why It Hurts
String similarity alone is not enough.

### What to Prevent
Unicode-aware normalization and spelling-variant support.

---

## 33. TRANSLATION VARIANTS

### Problem
Different editions or translations may render the same name differently.

### Failure Mode
Multiple canonical forms appear for the same identity.

### Why It Hurts
Cross-edition inconsistency.

### What to Prevent
Canonical/display separation plus alias support.

---

## 34. NARRATOR SELF-REFERENCE

### Problem
The narrator may refer to themselves indirectly.

### Failure Mode
The graph fails to link self-reference to narrator identity.

### Why It Hurts
Narrator memory becomes split.

### What to Prevent
Self-reference resolution tied to narrator state.

---

## 35. DREAMS, IMAGINED SCENES, AND FALSE VISIONS

### Problem
Characters may dream, hallucinate, imagine, or recall events.

### Failure Mode
Imagined content is treated as real event history.

### Why It Hurts
False events become graph truth.

### What to Prevent
Evidence source typing:
- observed
- imagined
- recalled
- dreamed
- reported

---

## 36. FLASHBACKS AND NONLINEAR TIMELINES

### Problem
Events may happen in the past but be narrated later.

### Failure Mode
Chronology becomes wrong.

### Why It Hurts
Relationships and event ordering drift.

### What to Prevent
Separate narrative order from story time when possible.

---

## 37. PARTIAL REFERENCES TO GROUPS OR LOCATIONS

### Problem
A mention can refer to:
- a district
- a house
- a school
- a city section
- a faction sub-group

### Failure Mode
Parent/child location or group nodes collapse.

### Why It Hurts
Location hierarchy and group hierarchy get lost.

### What to Prevent
Use hierarchical entity typing.

---

## 38. NEGATIVE OR SARCASTIC REFERENCES

### Problem
A character may mock someone by using a title or label.

### Failure Mode
The system treats sarcastic reference as a real alias or relationship.

### Why It Hurts
Irony is not identity.

### What to Prevent
Evidence confidence should be reduced for sarcastic or quoted mockery.

---

## 39. REPEATED GENERIC ROLES IN DIFFERENT SCENES

### Problem
Words like:
- guard
- doctor
- captain
- teacher
- father

can recur many times in different scenes.

### Failure Mode
The graph keeps creating or merging them.

### Why It Hurts
Generic role words are not stable identities.

### What to Prevent
Role mentions should be linked only when context makes them unique.

---

## 40. SESSION SPRAWL

### Problem
Testing many books creates many sessions.

### Failure Mode
Old test sessions hide the good ones.

### Why It Hurts
You waste time inspecting stale data.

### What to Prevent
CLI and FastAPI session deletion, rename, restore, and purge.

---

## 41. STALE GRAPH REUSE

### Problem
Old session graphs may be reused accidentally.

### Failure Mode
A new test inherits stale bugs.

### Why It Hurts
Debugging becomes impossible.

### What to Prevent
Clear session versioning and explicit deletion workflow.

---

## 42. PERFORMANCE DEGRADATION ON LARGE BOOKS

### Problem
Big novels will stress:
- entity search
- alias matching
- event matching
- prompt context assembly
- merge passes

### Failure Mode
The system slows to a crawl.

### Why It Hurts
Even a correct resolver becomes unusable.

### What to Prevent
Blocking, indexing, and capped context windows.

---

## 43. CONFIDENCE OVERFLOW FROM TOO MUCH HISTORY

### Problem
A lot of weak evidence can accumulate into an artificially strong confidence score.

### Failure Mode
Bad candidates become accepted just because they appeared often.

### Why It Hurts
Frequency is not truth.

### What to Prevent
Use weighted confidence and decay.

---

## 44. LOW-VALUE CONTEXT POLLUTION

### Problem
Some lines are not useful context:
- headers
- repeated labels
- expired review lines
- rejected candidates
- descriptor fragments

### Failure Mode
Prompt context becomes noisy and misleading.

### Why It Hurts
LLM extraction quality drops.

### What to Prevent
Context filtering before prompt construction.

---

## 45. MERGE AUDIT NEEDS TO REMAIN TRUSTWORTHY

### Problem
If merge audit becomes noisy or incomplete, debugging becomes guessing again.

### Failure Mode
You can no longer explain why a merge happened.

### Why It Hurts
Loss of trust in the graph.

### What to Prevent
Persist:
- evidence
- score
- margin
- reason
- resolver version
- source chapter

---

## 46. EVENT PARTICIPANT LINKING CAN OVER-ATTACH NAMES

### Problem
A chapter can mention many entities near an event summary.

### Failure Mode
Too many participants get attached to one event.

### Why It Hurts
Event semantics become noisy.

### What to Prevent
Participant attachment should be conservative and evidence-driven.

---

## 47. RELATIONSHIP HISTORY CAN GET DUPLICATED DURING MERGE

### Problem
When entities merge, old relationship rows may be copied or mirrored incorrectly.

### Failure Mode
Relationship history duplicates or loops.

### Why It Hurts
The graph becomes inflated and contradictory.

### What to Prevent
Deduplicate relationship history during merge migration.

---

## 48. LOOKALIKE NAMES WITH DIFFERENT ROLES

### Problem
A name can be both a person and a role-like label in another context.

Example class:
- a surname that is also a place
- a title that is also a personal nickname
- a role that is also a proper noun

### Failure Mode
Resolver assigns wrong entity type.

### Why It Hurts
Type confusion is harder to repair than alias confusion.

### What to Prevent
Type-specific blocking before scoring.

---

## 49. READING ORDER VS STORY ORDER

### Problem
Books do not always present events in chronological order.

### Failure Mode
The graph assumes reading order equals story order.

### Why It Hurts
Event and relationship timelines drift.

### What to Prevent
Track narrative order separately from inferred chronology when possible.

---

