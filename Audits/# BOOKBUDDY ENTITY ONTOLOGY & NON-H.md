# BOOKBUDDY ENTITY ONTOLOGY & NON-HUMAN EDGE CASE AUDIT
## Problems to Solve Early Before They Become Graph Corruption

---

# HARD RULE

## NO HARDCODING EXAMPLES

Examples below are only there to explain failure classes.

Do **not** write code that special-cases any specific:
- character
- book
- title
- species
- alien race
- AI name
- god
- pet
- object
- location
- author style

If the code needs named exceptions, the code is wrong.

---

# 1. ENTITY TYPE IS NOT ENOUGH

## Problem

A simple entity type list such as:
- person
- group
- location
- object

is not enough for real books.

---

## Why This Becomes a Bug

Books contain:
- sentient animals
- AI
- gods
- spirits
- undead
- constructs
- talking objects
- talking plants
- non-human species
- living places
- symbolic entities
- dream entities
- alternate selves

---

## Industry Solution

Use layered ontology instead of one flat type field.

Recommended layers:
- entity_category
- species_or_kind
- sentience
- narrative_role
- canonical_identity
- active_status

---

# 2. SENTIENT OBJECTS MUST NOT BE TREATED AS NORMAL OBJECTS

## Problem

Some objects are characters.

Examples of the class:
- talking weapons
- talking walls
- talking houses
- magical artifacts with memory
- AI ships
- cursed items with agency

---

## Why This Becomes a Bug

If treated as plain objects, they cannot:
- speak
- remember
- form relationships
- persist across chapters
- participate in events

---

## Industry Solution

Add a sentient-object class.

Treat them as:
- entity_category = character
- species_or_kind = object
- sentience = true

---

# 3. SENTIENT PLANTS ARE A REAL THING

## Problem

Books may contain:
- talking plants
- emotionally important plants
- magical trees
- conscious vines
- symbolic flora with agency

---

## Why This Becomes a Bug

A plant may be:
- a character
- a companion
- a witness
- an emotional anchor
- a location marker

---

## Industry Solution

Do not force plants into normal person logic.

Use:
- category
- kind/species
- sentience
- narrative importance

---

# 4. PETS AND ANIMALS ARE NOT OPTIONAL

## Problem

Animals can be:
- named recurring characters
- emotionally important companions
- plot participants
- narratively central

---

## Why This Becomes a Bug

If animals are ignored, key relationships disappear.

If animals are shoved into person logic, the graph becomes nonsense.

---

## Industry Solution

Add animal-aware entity handling.

Animals should support:
- names
- aliases
- species
- relationships
- event participation
- narrative importance

---

# 5. NON-HUMAN SPECIES NEED SEPARATE IDENTITY AND SPECIES

## Problem

A character can be:
- a person-like protagonist
- a non-human species member
- an AI
- a construct
- a hybrid being

---

## Why This Becomes a Bug

If species and identity are mixed, you cannot represent:
- humans
- aliens
- animals
- machines
- hybrids
- transformed beings

---

## Industry Solution

Separate:
- entity identity
- species or kind
- sentience
- body form
- narrative role

This allows a character to be:
- category = character
- species = non-human
- sentience = true

---

# 6. AI CHARACTERS REQUIRE A FIRST-CLASS CATEGORY

## Problem

Artificial intelligence can be:
- a voice
- a system
- a location
- a character
- an antagonist
- a helper
- a distributed mind

---

## Why This Becomes a Bug

AI may be treated as:
- a machine only
- a person only
- a location only

which is wrong in different ways.

---

## Industry Solution

Add:
- entity_category = character
- species_or_kind = AI
- sentience = true/false
- embodiment = none/distributed/physical/systemic

---

# 7. ALIEN LANGUAGE IS NOT ALWAYS TRANSLATABLE

## Problem

Books may include:
- alien speech
- coded speech
- fictional languages
- partial ciphers
- untranslated phrases
- invented scripts

---

## Why This Becomes a Bug

The system may hallucinate meanings or treat unknown phrases as normal text.

---

## Industry Solution

Store unknown-language text as:
- raw surface form
- language status
- translation status
- evidence source
- later learned meaning if available

Never guess a translation unless the book provides one or the graph learns it later.

---

# 8. CIPHER AND DECODER LOGIC SHOULD BE OPTIONAL

## Problem

Some books explicitly provide a cipher, glossary, translation key, or decoding rule.
Others do not.

---

## Why This Becomes a Bug

The tool may assume every foreign text is meant to be translated.

---

## Industry Solution

Separate:
- known cipher
- unknown language
- user-invented translation layer
- book-provided glossary

No translation without evidence.

---

# 9. GODS, SPIRITS, AND MYTHIC ENTITIES REQUIRE THEIR OWN LOGIC

## Problem

Books may contain:
- gods
- spirits
- demons
- angels
- metaphysical entities
- manifestations
- personified concepts

---

## Why This Becomes a Bug

These are not always ordinary characters.
They may be:
- real entities
- symbolic entities
- belief constructs
- unreliable narration artifacts

---

## Industry Solution

Add entity subclassing:
- character
- divine entity
- spirit
- construct
- concept-personification

Use evidence source typing to distinguish belief from fact.

---

# 10. UNDDEAD, CLONES, SPLIT SELVES, AND COPIES

## Problem

Stories often include:
- undead
- clones
- backups
- reconstructed bodies
- copied minds
- split personalities
- duplicates
- alternate selves

---

## Why This Becomes a Bug

Identity is not always one body = one person.

---

## Industry Solution

Introduce identity lineage:
- original identity
- derivative identity
- copy relation
- resurrection relation
- host relation
- alternate-self relation

Do not force all copies into one canonical node unless the narrative explicitly supports it.

---

# 11. BODY SWAPS AND POSSESSION

## Problem

A mind may occupy:
- another body
- a vessel
- a host
- an avatar
- a possessed form

---

## Why This Becomes a Bug

The visible speaker/body is not always the true identity.

---

## Industry Solution

Separate:
- mind identity
- body identity
- active host
- possession state
- narration identity

This must be explicit, not inferred from name alone.

---

# 12. AVATARS AND FORMS

## Problem

A character may appear as:
- avatar
- mask
- projection
- false body
- illusion
- transformed form

---

## Why This Becomes a Bug

The graph may confuse temporary form with true identity.

---

## Industry Solution

Track:
- true identity
- current form
- transformation state
- disguise state
- avatar relation

---

# 13. RECURRING MASKS, STAGE NAMES, PEN NAMES, ALIASES

## Problem

Characters may use:
- pen names
- stage names
- online handles
- secret identities
- codenames
- battlefield names

---

## Why This Becomes a Bug

Every form becomes a separate entity if the alias system is too literal.

---

## Industry Solution

Alias classification must distinguish:
- stable alias
- temporary alias
- disguise
- role name
- title
- codename

Support accumulation should differ by class.

---

# 14. RANKS AND OFFICES CHANGE IDENTITY SURFACE

## Problem

Characters often become known by:
- rank
- office
- title
- job
- role
- faction position

---

## Why This Becomes a Bug

Rank can look like a name, and names can look like rank.

---

## Industry Solution

Store titles separately from identity.
Titles may be attached to identity, but never replace identity.

---

# 15. LIVING LOCATIONS

## Problem

Some settings contain:
- sentient houses
- living planets
- talking cities
- aware forests
- magical rooms

---

## Why This Becomes a Bug

Location logic alone cannot represent agency.

---

## Industry Solution

Allow:
- location category
- sentience flag
- character-like participation
- place identity
- active relationship participation

---

# 16. SYMBOLIC OR METAPHORIC ENTITIES

## Problem

Some mentions are not literal entities:
- death
- fate
- time
- war
- justice
- memory
- prophecy

---

## Why This Becomes a Bug

The graph may turn abstract concepts into characters.

---

## Industry Solution

Add concept entities distinct from characters.

Use:
- concept category
- narrative use
- literal vs metaphorical evidence

---

# 17. BOOK-WITHIN-A-BOOK REFERENCES

## Problem

Books may mention:
- fictional books
- stories
- songs
- poems
- myths
- in-world laws
- in-world histories

---

## Why This Becomes a Bug

The parser may treat titles of works as persons or places.

---

## Industry Solution

Use reference entity types:
- work of art
- law
- theorem
- myth
- historical reference
- scientific reference

These should not automatically become active story characters.

---

# 18. HISTORICAL AND SCIENTIFIC REFERENCE LEAKAGE

## Problem

Named references may appear in-story without being participants.

Examples of the class:
- scientists
- philosophers
- laws
- theorems
- wars
- historical figures
- inventions

---

## Why This Becomes a Bug

The system may create active entities from references that are only mentioned conceptually.

---

## Industry Solution

Separate:
- active narrative entity
- referenced entity
- symbolic reference
- historical reference

Only active narrative entities participate in relationships and event graphs.

---

# 19. MENTIONED ENTITY VS ACTIVE ENTITY

## Problem

A thing can be mentioned without being present in the narrative.

---

## Why This Becomes a Bug

Reference-only mentions become characters in the graph.

---

## Industry Solution

Add an active-status dimension:
- active participant
- referenced only
- historical only
- symbolic only
- uncertain

This is critical for books with lectures, myths, and citations.

---

# 20. DREAMS, HALLUCINATIONS, AND VISION SCENES

## Problem

Dream content may include:
- fake entities
- imagined conversations
- symbolic figures
- distorted relationships

---

## Why This Becomes a Bug

Imagined content gets stored as narrative fact.

---

## Industry Solution

Tag evidence source:
- observed
- dreamed
- imagined
- hallucinated
- recalled
- reported

Only some evidence should influence entity confidence strongly.

---

# 21. FLASHBACKS AND NONLINEAR TIMELINES

## Problem

Narrative order and story order are not always the same.

---

## Why This Becomes a Bug

The graph may interpret old events as current state.

---

## Industry Solution

Track:
- narrative order
- story-time order if discoverable
- chapter order
- event order
- flashback marker

---

# 22. RELIABLE VS UNRELIABLE NARRATORS

## Problem

Narrators can lie, be confused, or be incomplete.

---

## Why This Becomes a Bug

The system may treat belief as fact.

---

## Industry Solution

Store evidence type:
- fact
- belief
- claim
- rumor
- speculation
- memory
- lie
- uncertain inference

---

# 23. DIALOGUE ATTRIBUTION

## Problem

Who said what is not always obvious.

---

## Why This Becomes a Bug

Relationships, kinship, and intentions get assigned to the wrong person.

---

## Industry Solution

Resolve:
- speaker
- addressee
- dialogue context
- recent mention window
- scene participants

Dialogue should not be treated as anonymous text.

---

# 24. CROSS-CHAPTER CONTEXT BLEED

## Problem

Old entities and old assumptions may over-influence later chapters.

---

## Why This Becomes a Bug

The graph may keep resolving things through outdated context.

---

## Industry Solution

Use:
- confidence decay
- recency weighting
- chapter windowing
- dormant entity reactivation
- local evidence dominance

---

# 25. MULTI-POV RELATIONSHIP ASYMMETRY

## Problem

Two POVs can describe the same relationship very differently.

---

## Why This Becomes a Bug

A global score hides perspective and narrative tension.

---

## Industry Solution

Store per-POV relationship views:
- source POV
- source belief
- target belief
- trust from source
- trust from target
- confidence

---

# 26. SPECIES VS ROLE VS CATEGORY CONFUSION

## Problem

One entity may have:
- category = character
- species = animal/alien/AI
- role = captain/teacher/antagonist
- social status = noble/commoner

---

## Why This Becomes a Bug

Flattening everything into one field causes repeated type bugs.

---

## Industry Solution

Use a multi-field ontology:
- category
- species/kind
- sentience
- role
- status
- alias set

---

# 27. ANIMALS WITH HUMAN-LIKE AGENCY

## Problem

Animals can be:
- protagonists
- companions
- narrators
- thinkers
- named characters

---

## Why This Becomes a Bug

They are not humans, but they are also not disposable background objects.

---

## Industry Solution

Animal entities should support:
- character participation
- relationships
- event attachment
- alias tracking
- species tags

---

# 28. TALKING PLANTS, TALKING WALLS, TALKING STATUES

## Problem

Non-living things can be narrative participants.

---

## Why This Becomes a Bug

They are not people, but they are also not inert objects.

---

## Industry Solution

Allow object entities with sentience or agency.

These should be able to:
- speak
- act
- remember
- relate to others

---

# 29. SENTIMENTAL NON-LIVING OBJECTS

## Problem

A character may care deeply about:
- a cactus
- a toy
- a sword
- a mask
- a relic
- a letter
- a ship

---

## Why This Becomes a Bug

Important objects may be ignored because they are not characters.

---

## Industry Solution

Use importance and narrative significance fields for non-living entities.

Not all important entities are characters.

---

# 30. ENTITY INTERPRETATION DEPENDS ON GENRE

## Problem

The same surface form can behave differently in:
- fantasy
- sci-fi
- literary fiction
- mythology
- horror
- children's books
- non-fiction

---

## Why This Becomes a Bug

Generic heuristics may not generalize across genre.

---

## Industry Solution

Use genre-agnostic logic by default, but allow confidence from context and evidence, not hardcoded genre assumptions.

---

# 31. LANGUAGE STYLE CAN BREAK EXTRACTOR CONFIDENCE

## Problem

Books with:
- broken spelling
- weird punctuation
- experimental prose
- stream of consciousness
- dialect
- childlike narration
- regression in language ability

can all distort extraction.

---

## Why This Becomes a Bug

The same entity can appear in many malformed forms.

---

## Industry Solution

Normalize cautiously.
Preserve raw text.
Use spelling variants as weak evidence, not truth.

---

# 32. SPELLING VARIANTS AND TRANSLITERATION

## Problem

Names can vary across:
- editions
- translations
- accents
- transliteration systems
- OCR noise

---

## Why This Becomes a Bug

Same identity appears as several strings.

---

## Industry Solution

Canonical + alias + normalized key.
Do not require identical spelling.

---

# 33. SECTION TYPES MATTER

## Problem

Not every extracted chunk is narrative prose.

There may be:
- epigraphs
- footnotes
- appendices
- glossary entries
- chapter headings
- citations
- poems
- maps
- letters
- lists

---

## Why This Becomes a Bug

Non-narrative material pollutes the graph.

---

## Industry Solution

Classify section type before extraction.

Do not treat all text blocks as narrative chapters.

---

# 34. CHARACTER LINEAGE AND ALTERED STATES

## Problem

A character may have:
- reincarnation
- transformation
- partial memory loss
- altered state
- restored body
- merged consciousness

---

## Why This Becomes a Bug

Identity continuity becomes non-trivial.

---

## Industry Solution

Add lineage / state history:
- original identity
- derived identity
- altered state
- restored state
- memory continuity confidence

---

# 35. SHAPESHIFTERS AND DISGUISES

## Problem

A character may appear as another form or species.

---

## Why This Becomes a Bug

The visible form becomes mistaken for the true identity.

---

## Industry Solution

Separate:
- true identity
- visible form
- disguise state
- transformation state

---

# 36. GROUPS THAT ACT LIKE INDIVIDUALS

## Problem

Some factions, ships, collectives, or corporations behave like single agents.

---

## Why This Becomes a Bug

They need identity, history, and relationships like characters.

---

## Industry Solution

Allow group entities to have:
- relationships
- events
- aliases
- narrative role
- active status

---

# 37. BOOKS WITH IN-UNIVERSE GLOSSARIES OR CIPHERS

## Problem

Books may provide:
- language keys
- term lists
- codebooks
- lore appendices
- glossary entries

---

## Why This Becomes a Bug

The parser may ignore valuable translation evidence or overuse it.

---

## Industry Solution

Glossary/cipher entries should be first-class evidence sources, not forced into normal dialogue logic.

---

# 38. NON-ASCII AND SYMBOL-HEAVY NAMES

## Problem

Names may include:
- apostrophes
- hyphens
- accents
- special characters
- unusual punctuation

---

## Why This Becomes a Bug

Normalization can over-strip and collapse distinct identities.

---

## Industry Solution

Normalize carefully.
Keep both:
- raw form
- normalized key

---

# 39. REPEATED OR NESTED METADATA TERMS

## Problem

Some names resemble:
- chapter labels
- chapter numbers
- book numbers
- section headers
- page notes

---

## Why This Becomes a Bug

Metadata becomes mistaken for entities.

---

## Industry Solution

Clean metadata before extraction and tag metadata-derived lines separately.

---

# 40. FUTURE RED RISING / MULTI-POV / ALIEN TESTS WILL EXPOSE THE REST

## Problem

The current system may pass simpler books but fail on:
- multi-POV series
- omnibuses
- alien species
- AI characters
- sentient objects
- non-human narrators
- experimental prose
- unreliable narration

---

## Why This Becomes a Bug

These are the books that expose missing ontology layers.

---

## Industry Solution

Use them as planned torture tests:
- identity stability
- POV stability
- species stability
- sentience stability
- reference classification
- location/person separation
- session boundary isolation

---

# FINAL PRINCIPLE

BookBuddy should not only answer:
- Who is this?

It must also answer:
- What kind of entity is this?
- Is it active or referenced?
- Is it sentient?
- Is it a character, object, species, or concept?
- Does it belong to the current POV or only to the lore?
- Is it a real participant or just a mention?

If these distinctions are not explicit, the graph will eventually collapse under its own cleverness.