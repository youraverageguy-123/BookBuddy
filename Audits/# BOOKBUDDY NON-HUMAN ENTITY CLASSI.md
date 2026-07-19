# BOOKBUDDY NON-HUMAN ENTITY CLASSIFICATION AUDIT
## Stop the graph from flattening aliens, animals, sentient objects, and imagined voices into one useless bucket

## HARD RULE
Do **not** hardcode book-specific examples.

These are **classification and ontology** problems, not special cases.

The system must keep the following distinct:
- human characters
- non-human sentient beings
- animals
- pets
- non-living named objects
- imagined / hallucinated entities
- symbolic entities
- locations with agency
- reference-only mentions

The current ontology draft already points in this direction, but this audit makes the separation stricter and more explicit. :contentReference[oaicite:0]{index=0}

---

## 1. “NON-HUMAN ENTITY” IS TOO BROAD

### Problem
If all non-human beings are lumped into one bucket, the graph becomes messy and low value.

### Failure Mode
The system cannot distinguish:
- alien species
- trolls
- orcs
- cyclops
- demons
- talking swords
- talking plants
- sentient walls
- living statues
- AI minds

### Why It Hurts
Different kinds of non-human entities behave differently in narrative structure.

### What to Prevent
Use a layered classification:
- entity_category
- entity_kind
- sentience
- narrative_role
- active_status

---

## 2. ANIMALS SHOULD BE A SEPARATE BRANCH

### Problem
Animals are not the same as generic non-human sentient entities.

### Failure Mode
A pet, a feral beast, a hunted creature, and a symbolic animal all get treated the same way.

### Why It Hurts
Animals have distinct narrative behavior:
- named companions
- working animals
- wild animals
- symbolic animals
- recurring animal characters

### What to Prevent
Create an `ANIMAL` branch separate from generic non-human sentient beings.

---

## 3. PET VS FERAL VS WILD VS DOMESTICATED

### Problem
Not every animal has the same social role.

### Failure Mode
The graph treats all animals as equivalent.

### Why It Hurts
A named pet is often a character.
A wild animal is often an event participant or environmental entity.
A feral animal may fall somewhere in between.

### What to Prevent
Track:
- pet
- domesticated
- feral
- wild
- working animal
- symbolic animal

---

## 4. NAMED ANIMALS CAN BE CHARACTERS

### Problem
A named animal may recur across chapters and matter deeply to the reader.

### Failure Mode
The graph ignores the animal or demotes it to background noise.

### Why It Hurts
Important animal companions become invisible.

### What to Prevent
Allow named animals to have:
- aliases
- relationships
- event participation
- importance score
- recurring status

---

## 5. ANIMALS CAN BE BOTH CHARACTERS AND SYMBOLS

### Problem
An animal may be narratively important in two ways:
- as an actual participant
- as a symbolic object of emotion or memory

### Failure Mode
The system forces one interpretation and loses the other.

### Why It Hurts
Symbolic and literal roles often coexist.

### What to Prevent
Store both:
- literal active role
- symbolic/affective role

---

## 6. SENTIENT OBJECTS MUST BE DISTINCT FROM INANIMATE OBJECTS

### Problem
Some objects speak, think, remember, or act.

### Failure Mode
The graph stores them as ordinary objects and loses agency.

### Why It Hurts
A talking sword is not a table.
A cursed artifact with memory is not a chair.

### What to Prevent
Support:
- sentient object
- non-sentient object
- object with memory
- object with agency

---

## 7. NAMED NON-LIVING OBJECTS NEED THEIR OWN CLASS

### Problem
A named object can matter emotionally even if it is not alive.

### Failure Mode
The graph treats named objects as meaningless props.

### Why It Hurts
Objects can be gifts, relics, memorials, anchors, or plot devices.

### What to Prevent
Track:
- named object
- owner/attachment relation
- emotional significance
- active use in plot
- reference-only status

---

## 8. OBJECTS THAT ARE MENTALLY IMPORTANT TO A CHARACTER

### Problem
A character may emotionally attach to an object and refer to it as if it matters deeply.

### Failure Mode
The graph ignores the object because it is not living.

### Why It Hurts
The object may be central to memory, grief, identity, or motivation.

### What to Prevent
Allow named objects to accumulate:
- emotional attachment
- ownership
- inheritance
- gift relation
- memorial relation

---

## 9. HALLUCINATED OR IMAGINED VOICES SHOULD NOT BECOME REAL ENTITIES

### Problem
A broken or hallucinating character may imagine voices or dialogue from objects.

### Failure Mode
The graph creates real characters from hallucinated speech.

### Why It Hurts
It confuses perception with reality.

### What to Prevent
Store:
- imagined entity mention
- hallucinated voice
- dream entity
- perceived agency
- narrative source type

Never promote purely hallucinated content as real narrative entities unless later text confirms it.

---

## 10. DREAM / IMAGINATION / HALLUCINATION LAYER

### Problem
Narrative events may occur only in a character’s mind.

### Failure Mode
The system stores imagined content as external fact.

### Why It Hurts
The graph becomes unreliable and spoiler-prone.

### What to Prevent
Add source layers:
- observed
- dreamed
- imagined
- hallucinated
- recalled
- reported

Only some of these should influence active identity and relationship scores.

---

## 11. NON-HUMAN SENTIENCE SHOULD BE EXPLICIT

### Problem
Some entities are non-human but still fully sentient.

### Failure Mode
The system treats them as animals or objects only.

### Why It Hurts
Agency, dialogue, and relationships are lost.

### What to Prevent
Track:
- sentience = true
- entity_kind = alien / construct / AI / spirit / object / animal / etc.
- narrative role = character

---

## 12. ALIEN SPECIES SHOULD NOT BE INDIVIDUAL HARD-CODED TYPES

### Problem
A huge taxonomy of species can clutter the graph.

### Failure Mode
Each non-human species becomes a one-off special case.

### Why It Hurts
The ontology explodes into brittle categories.

### What to Prevent
Use:
- broad non-human category
- species_or_kind
- subtype
- sentience
- social role

Let the species field carry the specific label, not the top-level ontology.

---

## 13. ORC / TROLL / CYCLOPS / DEMON / CONSTRUCT / AI SHOULD BE KIND VALUES, NOT SPECIAL CASES

### Problem
Fantasy and sci-fi species should fit a generic system.

### Failure Mode
Each species gets hardcoded handling.

### Why It Hurts
The codebase becomes a zoo of exceptions.

### What to Prevent
Use generic `kind` or `species` fields with evidence-based classification.

---

## 14. ROLE-BASED ENTITY PROMOTION SHOULD APPLY TO NON-HUMANS TOO

### Problem
Non-human entities can speak, act, lead, protect, betray, or travel.

### Failure Mode
Only humans get promoted into active entities.

### Why It Hurts
The story world becomes human-only even when the text is not.

### What to Prevent
Promotion should depend on:
- action
- speech
- presence
- event participation
- relationship evidence

Not on being human.

---

## 15. ANIMALS CAN BE PETS, COMPANIONS, MESSENGERS, GUARDS, OR THREATS

### Problem
The same animal class can occupy very different narrative roles.

### Failure Mode
The graph flattens them into a single animal bucket.

### Why It Hurts
A companion animal and a background herd are not the same.

### What to Prevent
Track role:
- pet
- companion
- working animal
- wild threat
- symbolic animal
- recurring named animal

---

## 16. NON-LIVING OBJECTS CAN BE NAMED AFTER PEOPLE

### Problem
A sword, ship, law, treaty, building, memorial, or artifact can be a namesake reference.

### Failure Mode
The graph turns the namesake object into the human honoree.

### Why It Hurts
This causes homonym and eponym confusion.

### What to Prevent
Use separate:
- active object entity
- namesake relation
- external attribution
- reference mention

---

## 17. NON-LIVING OBJECTS CAN ALSO BE HALUCINATED OR PERSONIFIED

### Problem
A narrator may imagine an object speaking.

### Failure Mode
The graph creates an active sentient object incorrectly.

### Why It Hurts
The object is only sentient within the perception layer.

### What to Prevent
Differentiate:
- real sentient object
- imagined sentient object
- symbolic object
- ordinary object

---

## 18. LIVING PLACES / AGENTIVE SETTINGS

### Problem
Some settings behave like living or aware entities.

### Failure Mode
They are only treated as locations.

### Why It Hurts
Their agency gets lost.

### What to Prevent
Allow:
- location
- agentive location
- sentient location
- symbolic location

Only promote to character-like behavior if the text supports it.

---

## 19. NAMED OBJECTS SHOULD NOT COLLIDE WITH NAMED CHARACTERS

### Problem
A character and a named object can share the same surface form.

### Failure Mode
They are merged because the spelling is identical.

### Why It Hurts
This is a core identity bug.

### What to Prevent
Require type compatibility plus context compatibility before merge.

---

## 20. ACTIVE ENTITY VS REFERENCE ENTITY VS SYMBOLIC ENTITY

### Problem
A mention can be:
- an active participant
- a reference to something external
- a symbolic or metaphorical mention

### Failure Mode
They all get stored as the same kind of entity.

### Why It Hurts
The graph loses narrative meaning.

### What to Prevent
Maintain a strict three-way distinction:
- active entity
- reference entity
- symbolic entity

---

## 21. SENTIENT OBJECTS CAN HAVE RELATIONSHIPS, BUT NON-SENTIENT OBJECTS SHOULD NOT GET SOCIAL EDGES

### Problem
A named non-living object can be important, but not every object is social.

### Failure Mode
All named objects start acquiring character-like relationship edges.

### Why It Hurts
The social graph becomes absurd.

### What to Prevent
Only create social edges when:
- the object is sentient
- or the text explicitly assigns interaction-like agency

Otherwise keep it in object/reference logic.

---

## 22. ATTACHMENT RELATIONSHIP IS NOT A SOCIAL RELATIONSHIP

### Problem
A character can be emotionally attached to an object.

### Failure Mode
The graph treats attachment as if the object were a person.

### Why It Hurts
Emotional importance is not the same as social interaction.

### What to Prevent
Use a distinct relation type:
- attachment
- ownership
- inheritance
- memorial significance
- gift relation

Do not reuse friendship/relationship edges for objects.

---

## 23. NARRATIVE IMPORTANCE SHOULD BE SEPARATE FROM SENTIENCE

### Problem
An object can be central to the plot without being alive or sentient.

### Failure Mode
The graph only promotes living entities.

### Why It Hurts
Important objects disappear from memory.

### What to Prevent
Track:
- narrative importance
- sentience
- active status
- participation status

---

## 24. SPOILERS MUST NOT PROMOTE FUTURE CLASSIFICATION

### Problem
A later chapter may reveal that a thing is actually sentient, a pet, a spirit, or an alien.

### Failure Mode
The graph uses future knowledge in early chapters.

### Why It Hurts
Spoilers and impossible certainty.

### What to Prevent
Use chapter-bound promotion:
- current read state only
- local evidence only
- future reclassification only after the reader reaches it

---

## 25. MIXED MEDIA / META TEXT / HALLUCINATED TEXT

### Problem
Books may include:
- letters
- logs
- recordings
- dreams
- art
- hallucinated dialogue
- symbolic chapters

### Failure Mode
Everything gets read as regular narrative prose.

### Why It Hurts
The entity classifier loses source context.

### What to Prevent
Store source section type and source confidence before promoting entities.

---

## 26. TRANSFORMED OR ALTERED NON-HUMANS

### Problem
A non-human entity may change form, intelligence, or agency over time.

### Failure Mode
The graph treats the changed state as a brand-new entity.

### Why It Hurts
Identity lineage breaks.

### What to Prevent
Track state transitions:
- base kind
- transformed form
- altered sentience
- altered body

---

## 27. NAMED OBJECTS MAY BECOME ACTIVE ONLY LATER

### Problem
A dormant object may later reveal agency.

### Failure Mode
If first seen as an object, it can never become a character.

### Why It Hurts
Late narrative reveals are common.

### What to Prevent
Allow promotion from:
- object
- reference object
- active sentient object

with provenance and evidence.

---

## 28. ANIMAL AND OBJECT NAMES MAY BE USED AS METAPHORS

### Problem
A word that looks like an animal or object may just be metaphorical prose.

### Failure Mode
The graph creates an entity from figurative language.

### Why It Hurts
Poetry becomes corrupted into ontology.

### What to Prevent
Use evidence source, context window, and participation score before creating the entity.

---

## 29. THINGS WITH VOICES ARE NOT NECESSARILY PEOPLE

### Problem
A voice may come from:
- a machine
- a wall
- a memory
- a hallucination
- a broadcast
- a narrator's mind

### Failure Mode
The graph creates a human-like entity too quickly.

### Why It Hurts
Voice does not imply personhood.

### What to Prevent
Track:
- voice source
- voice authenticity
- voice embodiment
- voice reality status

---

## 30. THINGS WITH NAMES ARE NOT NECESSARILY CHARACTERS

### Problem
The presence of a name is not enough.

### Failure Mode
Named objects, pets, ships, laws, and hallucinations all become people.

### Why It Hurts
This is the root of many ontology bugs.

### What to Prevent
Require:
- narrative participation
- entity type compatibility
- source context
- active status

before entity promotion.

---

## 31. FUTURE TEST BOOKS SHOULD TARGET THIS AUDIT EXPLICITLY

### Problem
These bugs do not show up clearly in simple books.

### Failure Mode
The system looks fine in Gatsby-style tests and collapses later.

### Why It Hurts
Non-human and object-heavy books are the real stress tests.

### What to Prevent
Test on books that include:
- animals
- aliens
- AI
- talking objects
- symbolic entities
- hallucinations
- mythic beings
- living places

---

## FINAL PRINCIPLE

BookBuddy should never collapse all of the following into one bucket:
- human
- animal
- alien
- AI
- sentient object
- non-sentient object
- imagined entity
- symbolic entity
- reference-only mention

If the system cannot separate those, then it is not building a knowledge graph.

It is building a junk drawer with ambitions.