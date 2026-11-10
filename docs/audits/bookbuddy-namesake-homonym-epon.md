# BOOKBUDDY NAMESAKE / HOMONYM / EPONYM AUDIT
## Stop the graph from confusing “named after”, “same name”, and “same thing”

## HARD RULE
Do **not** hardcode book-specific names, ships, laws, treaties, planets, or characters.

This audit is about **name semantics**, not trivia.

The system must distinguish:
- active story entities
- named references
- namesakes
- homonyms
- renamed objects
- same-surface different-referent cases

---

## 1. NAMESAKE IS NOT ENTITY IDENTITY

### Problem
A ship, law, treaty, institution, memorial, or place can be named after a person.

### Failure Mode
The graph treats the namesake object as the person itself.

### Why It Hurts
A commemorative object is not a living participant in the plot.

### What to Prevent
Store:
- reference mention
- namesake relation
- external attribution
- active entity: false
- promotion only if narrative participation exists

---

## 2. LIVING HONOREE VS DEAD HONOREE

### Problem
Some namesakes refer to living people, some to dead people, and the status can matter in story context.

### Failure Mode
The system assumes all namesakes imply the same kind of referent.

### Why It Hurts
A living named person can still be a story participant, while a dead honoree is only a reference source.

### What to Prevent
Track:
- honoree status if available from narrative evidence
- reference time vs story time
- whether the mention is honorific, commemorative, or active

---

## 3. SAME SURFACE, DIFFERENT REFERENT

### Problem
A single surface string can refer to multiple different things.

### Failure Mode
The graph merges them because the text looks identical.

### Why It Hurts
This is how you get absurd collisions like:
- person vs ship
- person vs treaty
- person vs place
- person vs object
- person vs title

### What to Prevent
Use context-aware disambiguation with:
- entity type
- scene role
- local syntax
- surrounding nouns
- narrative participation
- source section type

---

## 4. PERSON NAME VS SHIP NAME VS LAW NAME VS PLACE NAME

### Problem
The same string can be a person, a ship, a law, a treaty, a planet, a memorial, or a title.

### Failure Mode
The graph assumes all capitalized name-like strings are people.

### Why It Hurts
This destroys ontology.

### What to Prevent
Never resolve by surface form alone.
Require:
- context class
- mention source
- participation score
- entity type compatibility
- boundary-aware evidence

---

## 5. “NAMED AFTER” IS A REFERENCE RELATION, NOT AN ACTIVE PARTICIPATION SIGNAL

### Problem
Phrases like “named after X” or “X’s law” are attribution, not character action.

### Failure Mode
The reference source becomes an active entity because it appears in the text.

### Why It Hurts
The graph starts inventing participants from etymology.

### What to Prevent
Classify these as:
- namesake reference
- attribution reference
- commemorative reference
- institutional reference
- scientific reference

Not as active people by default.

---

## 6. A CHARACTER CAN SHARE A NAME WITH A REFERENCE OBJECT

### Problem
A character can have the same surface name as a ship, law, treaty, or place.

### Failure Mode
The system merges them because they look identical.

### Why It Hurts
Homonyms are not aliases.

### What to Prevent
Separate:
- canonical identity
- surface name
- subtype
- narrative role
- scene participation
- source quote evidence

---

## 7. HOMONYM VS ALIAS

### Problem
Two different entities may share the same surface form.

### Failure Mode
The system assumes same name means same entity.

### Why It Hurts
Alias logic and homonym logic are opposites.

### What to Prevent
An alias must have:
- direct evidence
- continuity evidence
- identity evidence

A homonym only has:
- same spelling
- different referent
- context-dependent role

---

## 8. REFERENCE ENTITY SHOULD STAY QUARANTINED UNTIL PROMOTED

### Problem
Reference-like phrases appear often in books.

### Failure Mode
They are promoted into the active graph too early.

### Why It Hurts
The graph becomes polluted with non-participants.

### What to Prevent
Keep them in:
- reference_mentions
- unresolved_mentions
- namesake relations

Promote only with:
- speaking
- acting
- being present
- participating in events
- having relationships

---

## 9. RENAMED OBJECTS ARE NOT NEW CHARACTERS

### Problem
An object, ship, memorial, law, or treaty may be renamed later.

### Failure Mode
The graph creates a fresh entity for each renamed surface.

### Why It Hurts
The same object fragments into multiple nodes.

### What to Prevent
Track:
- original object identity
- rename history
- alias history
- external attribution history

---

## 10. ALIVE-IN-STORY VS DEAD-IN-STORY VS HISTORICAL PERSON

### Problem
Some names refer to characters alive in the timeline, some to dead people, some to historical figures.

### Failure Mode
The graph collapses them into one generalized “person” node.

### Why It Hurts
Timeline and narrative state disappear.

### What to Prevent
Store:
- in-story alive/dead state
- historical reference state
- namesake reference state
- narrator knowledge of status

---

## 11. TIMELINE-SENSITIVE REFERENCES

### Problem
A name can mean different things depending on when in the story it appears.

### Failure Mode
The resolver uses later-book knowledge too early.

### Why It Hurts
Spoilers and false identity merges.

### What to Prevent
Resolve using:
- chapter boundary
- story time
- current reader knowledge
- inherited graph state with confidence penalty

---

## 12. SPOUSE / CHILD / FAMILY-NAME COLLISIONS

### Problem
Family names often collide with other entities.

### Failure Mode
The system assumes “same surname” or “same shared name token” implies identity.

### Why It Hurts
Entire family lines and named objects get welded together.

### What to Prevent
Require:
- same-boundary evidence
- participation evidence
- contextual role compatibility
- strong direct identity evidence

---

## 13. “OF” AND APOSTROPHE CONSTRUCTIONS

### Problem
Surface forms like:
- X’s law
- X of Y
- X’s memorial
- X of House Y
- Y’s ship

often encode reference, ownership, namesake, or institution rather than character identity.

### Failure Mode
The graph promotes the head noun or the possessor incorrectly.

### Why It Hurts
Grammar becomes identity logic.

### What to Prevent
Treat possessive and attribution constructions as:
- relation evidence
- reference evidence
- ownership evidence
- namesake evidence

Not automatic entity creation.

---

## 14. INSTITUTION / ORDER / HOUSE / ACADEMY AMBIGUITY

### Problem
Some named things are institutions, some are families, some are organizations, some are locations.

### Failure Mode
They all become the same kind of group or a random person.

### Why It Hurts
Ontology gets flattened.

### What to Prevent
Track subtype differences:
- family group
- institution
- military order
- school
- religious order
- noble house
- faction
- settlement
- compound location

---

## 15. LAW / TREATY / DOCTRINE / THEORY NAMES

### Problem
Treaties, laws, theories, doctrines, and doctrines named after people are not the people themselves.

### Failure Mode
The eponym source becomes a character node.

### Why It Hurts
Scientific and political references pollute the social graph.

### What to Prevent
Classify as:
- scientific reference
- legal reference
- political reference
- doctrinal reference
- memorialized reference

---

## 16. LIVING PERSON AS NAMESAKE AND CHARACTER

### Problem
A living person can be both:
- a real active character in the story
- a namesake reference for another object

### Failure Mode
The system merges the reference object with the active person.

### Why It Hurts
One node stops meaning anything.

### What to Prevent
Maintain separate nodes:
- active person entity
- namesake reference mention
- namesake relation between them

---

## 17. DEAD PERSON AS NAMESAKE AND HISTORICAL ENTITY

### Problem
A dead person may appear only as an eponym source.

### Failure Mode
The system promotes them to active story participant.

### Why It Hurts
Dead people start behaving like scene actors.

### What to Prevent
Keep them as:
- reference entity
- historical referent
- no active participation unless the text explicitly includes them in a flashback, vision, memory, or archival scene

---

## 18. FICTIONAL NAMES THAT LOOK LIKE REAL NAMES

### Problem
Books invent names that resemble real-world names.

### Failure Mode
The resolver uses real-world intuitions too aggressively.

### Why It Hurts
The system becomes brittle and overconfident.

### What to Prevent
Resolve from the book’s own local evidence first:
- mention history
- co-occurrence
- scene behavior
- participation role
- boundary consistency

---

## 19. THE SAME NAME CAN BE A TITLE, A PERSON, AND A REFERENCE

### Problem
One surface form can act as:
- title
- name
- object name
- honorific
- location name

### Failure Mode
The graph stores a single interpretation and loses the rest.

### Why It Hurts
Multi-function names are common in fiction.

### What to Prevent
Store role-dependent interpretations with provenance.

---

## 20. OBJECT NAMES THAT CONTAIN PERSONAL NAMES

### Problem
An object name may include a person name inside a larger phrase.

### Failure Mode
The system extracts the inner personal name as a standalone character.

### Why It Hurts
Token-level extraction breaks namesake objects.

### What to Prevent
Respect phrase-level context before entity splitting.

---

## 21. PARTIAL MATCH IS NOT IDENTITY

### Problem
Phrases may share a substring with an entity.

### Failure Mode
Any overlap creates a merge candidate.

### Why It Hurts
Same-token overlap is not enough.

### What to Prevent
Require stronger evidence than shared tokens:
- exact contextual role
- participation evidence
- boundary evidence
- disambiguating surrounding nouns

---

## 22. REFERENCE CHAINING

### Problem
A named object can refer to another reference, which refers to a person, which refers to a historical event.

### Failure Mode
The graph stops at the first name and mislabels the whole chain.

### Why It Hurts
Nested attribution is common in lore-heavy books.

### What to Prevent
Allow chained relations:
- object -> namesake
- namesake -> historical person
- person -> historical role
- reference -> source mention

---

## 23. CANONICAL NAME VS DISPLAY NAME VS REFERENCE LABEL

### Problem
One node may need different labels depending on context.

### Failure Mode
The system stores a single label and loses the distinction.

### Why It Hurts
Named objects and active people get conflated.

### What to Prevent
Separate:
- canonical_name
- display_name
- reference_label
- external_attribution_label

---

## 24. IN-STORY RENAMING OF THE SAME OBJECT

### Problem
An object may be renamed in different eras or by different groups.

### Failure Mode
Every name becomes a new node.

### Why It Hurts
The same object fractures across time.

### What to Prevent
Track rename lineage:
- original identity
- rename event
- source of rename
- current display label

---

## 25. DIFFERENT PEOPLE WITH THE SAME FIRST NAME OR NICKNAME

### Problem
The same surface can refer to different people in different places or books.

### Failure Mode
The graph merges them because the name is familiar.

### Why It Hurts
This is how cross-book contamination happens.

### What to Prevent
Use boundary-aware identity:
- book boundary
- volume boundary
- session boundary
- local relationship neighborhood
- active participation evidence

---

## 26. DIFFERENT PEOPLE WITH THE SAME FULL NAME ACROSS BOUNDARIES

### Problem
A full name can recur across books or timelines.

### Failure Mode
The resolver reuses the wrong identity.

### Why It Hurts
Series inheritance becomes toxic.

### What to Prevent
Penalize inherited candidates and require local evidence to override.

---

## 27. NAMESAKE OBJECTS SHOULD NOT CREATE SOCIAL EDGES BY DEFAULT

### Problem
A law or ship named after a person should not automatically imply a relationship edge to the living cast.

### Failure Mode
The graph makes fake social links.

### Why It Hurts
The relationship web gets polluted by reference noise.

### What to Prevent
Only create social edges when there is actual narrative participation.

---

## 28. SHIP / LAW / TREATY AS ACTIVE SETTING VS REFERENCE

### Problem
Some named references can also act as a setting or institutional space.

### Failure Mode
The system treats every such reference as either purely inactive or purely active.

### Why It Hurts
Some named things are both references and settings.

### What to Prevent
Allow dual tagging:
- reference mention
- setting mention
- active participation only if the text supports it

---

## 29. LORE TERMS VS ACTIVE PEOPLE

### Problem
Names from history, myth, literature, or science can appear in-world as background references.

### Failure Mode
The graph tries to socialize all lore.

### Why It Hurts
Mythology and reference material are not the same as the story cast.

### What to Prevent
Quarantine lore terms until they show narrative presence.

---

## 30. READER-KNOWLEDGE BOUNDARY

### Problem
The system must not use knowledge from later chapters to resolve an earlier ambiguous reference.

### Failure Mode
The graph cheats.

### Why It Hurts
Spoilers and impossible certainty.

### What to Prevent
Only use:
- text already read
- local context
- inherited graph with decay and lower confidence
- boundary-aware candidate scoring

---

## 31. PROMOTION SHOULD BE EVIDENCE-BASED, NOT NAME-BASED

### Problem
A name looking important should not matter.

### Failure Mode
The system promotes a name because it is famous in the real world or feels prominent.

### Why It Hurts
BookBuddy becomes a trivia engine.

### What to Prevent
Promotion requires:
- action
- speech
- presence
- interaction
- event participation
- story relevance

---

## 32. REFERENCE QUARANTINE SHOULD FEED BACK INTO RESOLUTION

### Problem
A quarantined reference can later become active if the book explicitly turns it into a participant.

### Failure Mode
The quarantine is a dead end.

### Why It Hurts
Valid later promotions get lost.

### What to Prevent
Store reference history and allow later promotion with provenance.

---

## 33. INFERENCE SHOULD BE CONSERVATIVE, NOT BLIND

### Problem
Surface overlap, capitalization, or fame should never dominate the decision.

### Failure Mode
The resolver becomes overconfident and brittle.

### Why It Hurts
The graph starts hallucinating.

### What to Prevent
Prefer:
- local evidence
- context
- participation
- boundary consistency
- graph neighborhood support

---

## 34. FINAL PRINCIPLE

BookBuddy should be able to tell the difference between:

- a living character
- a dead historical person
- a ship named after a person
- a law named after a person
- a treaty named after a place
- a place named after a dead person
- a later character with the same name as an earlier reference
- an object with the same surface name as a person
- a namesake reference that should never be promoted

If it cannot do that, then the graph is not understanding the book.

It is just repeating capital letters with confidence.