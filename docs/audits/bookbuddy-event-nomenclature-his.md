# BOOKBUDDY EVENT NOMENCLATURE / HISTORICAL LANDMARK AUDIT
## Stop the graph from treating every named event, arc, revolt, war, or political turning point as just another generic event

## HARD RULE
Do **not** hardcode book-specific names or examples.

This audit is about **event naming, landmark identity, event scope, political framing, retrospective naming, aliases, and event hierarchy**.

The system must distinguish:
- unnamed events
- named events
- landmark events
- event arcs
- campaigns
- wars
- revolts
- ceremonies
- massacres
- reforms
- policy shifts
- recurring annual events
- propaganda labels
- retrospective labels
- reader-known names vs character-known names

---

## 1. NOT EVERY EVENT SHOULD GET A NAME

### Problem
Many events are important but unnamed in the text.

### Failure Mode
The system forces a name too early.

### Why It Hurts
Unnamed events are still useful as anchors, especially before the official name appears later.

### What to Prevent
Allow event identity to exist without a named label.

Track:
- event_identity
- event_aliases
- event_name_status

---

## 2. NAMED LANDMARKS ARE NOT JUST EVENTS

### Problem
Some named things are larger than one event.

Examples of the class:
- revolts
- conquests
- wars
- civil wars
- campaigns
- uprisings
- eras
- reigns
- revolutions
- collapses

### Failure Mode
The graph stores them as one flat event.

### Why It Hurts
A major landmark contains multiple sub-events.

### What to Prevent
Use layered hierarchy:
- landmark
- arc
- major event
- sub-event

---

## 3. EVENT ARC VS SINGLE EVENT

### Problem
A named historical moment may span many chapters or many plot beats.

### Failure Mode
The system compresses a multi-stage arc into one event row.

### Why It Hurts
You lose internal structure.

### What to Prevent
Support:
- landmark event
- event cluster
- arc container
- subevent chain

---

## 4. OFFICIAL NAME MAY APPEAR LATE

### Problem
The reader may see the event before the event is named.

### Failure Mode
The system creates two separate things:
- unnamed earlier event
- named later event

### Why It Hurts
The same landmark fragments.

### What to Prevent
Allow retrospective renaming:
- early references link to unnamed landmark
- later official name aliases the same landmark
- reader-first-known-name preserved separately

---

## 5. POLITICAL FRAMING CHANGES THE NAME

### Problem
Different factions use different labels for the same event.

Examples of the class:
- liberation vs occupation
- conquest vs genocide
- uprising vs rebellion
- massacre vs purge

### Failure Mode
The graph creates separate landmarks for political variants.

### Why It Hurts
Same event, different ideology.

### What to Prevent
Store:
- canonical landmark
- faction-specific names
- speaker-specific naming
- framing polarity

---

## 6. PROPAGANDA LABELS ARE NOT CANONICAL NAMES

### Problem
A faction may rename an event to serve propaganda.

### Failure Mode
The propaganda label becomes the canonical label.

### Why It Hurts
Narrative truth and political framing collapse.

### What to Prevent
Tag event name source:
- canonical
- factional
- sarcastic
- pejorative
- commemorative
- historical
- rumor-based

---

## 7. EVENT ALIASES SHOULD WORK LIKE ENTITY ALIASES

### Problem
An event can be referred to by multiple names.

### Failure Mode
Each label becomes a separate event.

### Why It Hurts
Readers recognize the same landmark under different names.

### What to Prevent
Maintain:
- event canonical name
- event alias list
- alias confidence
- alias provenance

---

## 8. SAME EVENT, DIFFERENT SCOPE

### Problem
Some events are personal, some local, some regional, some global.

### Failure Mode
The graph treats all events equally.

### Why It Hurts
Scope strongly affects importance.

### What to Prevent
Store event scope:
- personal
- local
- regional
- planetary
- global
- cosmic

---

## 9. EVENT SCOPE SHOULD AFFECT IMPORTANCE

### Problem
A wedding and a civil war are not equal.

### Failure Mode
Both get the same weight.

### Why It Hurts
Landmarks and background events blur together.

### What to Prevent
Use scope as a ranking feature in summaries and memory cards.

---

## 10. EVENT DURATION MATTERS

### Problem
Some events are instantaneous.
Some span days.
Some span years.

### Failure Mode
Everything gets stored as one-point-in-time.

### Why It Hurts
Chronology and consequences get misread.

### What to Prevent
Track:
- start chapter
- end chapter
- duration
- narrative span
- story-time span

---

## 11. EVENT START AND EVENT NAME ARE NOT THE SAME THING

### Problem
An event can begin long before it gets its official name.

### Failure Mode
The graph anchors everything to the naming chapter.

### Why It Hurts
Reader knowledge and story chronology diverge.

### What to Prevent
Separate:
- event occurrence
- event naming
- reader first learns name
- narrator first uses name

---

## 12. SUB-EVENTS SHOULD REMAIN ATTACHED TO THEIR LANDMARK

### Problem
Major events contain smaller events.

### Failure Mode
Sub-events float away as unrelated rows.

### Why It Hurts
The landmark loses internal structure.

### What to Prevent
Track:
- parent landmark
- child event
- causal chain
- event grouping

---

## 13. EVENT NAMING CAN BE RETROSPECTIVE

### Problem
A later chapter may reveal the official name of a past event.

### Failure Mode
The graph creates duplicate landmark identities.

### Why It Hurts
The same event is represented twice.

### What to Prevent
When a canonical name appears later, merge it into the preexisting landmark with alias/provenance history.

---

## 14. A LANDMARK CAN HAVE MULTIPLE CANONICAL-LIKE NAMES

### Problem
Different books, cultures, or factions may each use a near-canonical label.

### Failure Mode
The resolver picks one and deletes the rest.

### Why It Hurts
Historical memory is plural.

### What to Prevent
Allow:
- one internal landmark identity
- multiple widely used public names

---

## 15. ANNIVERSARY AND REFERENCE-LATER PHRASES NEED LANDMARK MEMORY

### Problem
Phrases like “since then,” “after the war,” or “on that day” refer back to landmarks.

### Failure Mode
The graph fails to resolve the reference.

### Why It Hurts
Landmark memory is how narrative history works.

### What to Prevent
Store landmark reference chains and temporal anchors.

---

## 16. EVENT NAMES MAY BECOME IN-WORLD PROPER NOUNS

### Problem
An event name can later be used like a noun phrase:
- “after the Conquest”
- “post-Rising”
- “during the Revolt”

### Failure Mode
The system treats those as unrelated text.

### Why It Hurts
The event’s cultural footprint is lost.

### What To Prevent
Support event-derived adjectival or temporal references.

---

## 17. SOME EVENTS ARE REALLY POLITICAL RECLASSIFICATIONS

### Problem
A new government may rename a previous event.

### Failure Mode
The graph thinks it is a different event.

### Why It Hurts
Regime change often rewrites history.

### What To Prevent
Store political reclassification separately from event identity.

---

## 18. CELEBRATIONS AND MEMORIALS ARE EVENT-ADJACENT, NOT THE SAME THING

### Problem
A memorial ceremony references a prior landmark but is not that landmark.

### Failure Mode
The memorial becomes merged with the original event.

### Why It Hurts
A commemoration is not the original historical event.

### What To Prevent
Link:
- commemorative event
- memorial landmark
- source landmark

---

## 19. EVENTS CAN BE USED AS RELATIONSHIP SHOCKS

### Problem
Major landmarks cause lasting changes in relationships.

### Failure Mode
The graph stores the event but not the aftermath.

### Why It Hurts
Relationship arcs become disconnected from history.

### What To Prevent
Attach:
- aftermath relations
- grief shifts
- revenge shifts
- loyalty shifts
- faction changes
- legacy shifts

---

## 20. SOME EVENTS ARE REALLY PERIODS

### Problem
A named period may not be one event at all.

Examples of the class:
- age
- era
- reign
- occupation
- occupation period
- dark age
- golden age

### Failure Mode
The graph stores them as one event.

### Why It Hurts
Periods have internal structure and multiple constituent events.

### What To Prevent
Use:
- period landmark
- period start
- period end
- internal events
- narrative summary

---

## 21. SOME EVENTS ARE REALLY CAMPAIGNS OR CONFLICT ZONES

### Problem
A campaign may contain dozens of battles and political moves.

### Failure Mode
The system flattens the whole thing.

### Why It Hurts
Campaigns are collections of events, not a single beat.

### What To Prevent
Add:
- campaign container
- battle sub-events
- campaign participants
- campaign outcome

---

## 22. RITUALS, CEREMONIES, AND TRADITIONS NEED EVENT NAMING TOO

### Problem
Some named things are recurring rituals, not unique historical landmarks.

### Failure Mode
The graph treats them as one-off events.

### Why It Hurts
Recurring rituals are important narrative structures.

### What To Prevent
Track:
- recurring event template
- occurrence instances
- ceremonial alias
- calendar relation

---

## 23. RECURRING ANNUAL EVENTS SHOULD NOT MERGE ACROSS YEARS

### Problem
A yearly ceremony or festival can recur with the same name.

### Failure Mode
All occurrences collapse into one event.

### Why It Hurts
Temporal specificity is lost.

### What To Prevent
Each recurrence gets:
- occurrence id
- recurring template id
- year / chapter span
- local context

---

## 24. SOME EVENTS ARE KNOWN BY DIFFERENT NAMES IN DIFFERENT KNOWLEDGE LEVELS

### Problem
Readers may know one label, characters another, historians another.

### Failure Mode
The graph uses one global label.

### Why It Hurts
Spoiler-safe and perspective-aware naming breaks.

### What To Prevent
Store:
- reader-facing name
- narrator-facing name
- character-facing name
- canonical historical name

---

## 25. EVENT NAME VS CAUSAL EVENT VS AFTERMATH

### Problem
One event name may refer to the initiating act, the chain reaction, or the aftermath.

### Failure Mode
The system mixes them together.

### Why It Hurts
Causality becomes unclear.

### What To Prevent
Track:
- trigger event
- main landmark
- aftermath chain

---

## 26. A SINGLE LANDMARK MAY HAVE MULTIPLE PERSPECTIVE SUMMARIES

### Problem
Different factions summarize the same landmark differently.

### Failure Mode
One summary replaces all others.

### Why It Hurts
Bias matters.

### What To Prevent
Store:
- neutral summary
- faction summary
- narrator summary
- reader summary
- speaker summary

---

## 27. NAME-FREQUENCY SHOULD NOT CREATE A LANDMARK

### Problem
Repeating a phrase does not always mean it is a named event.

### Failure Mode
The system hallucinates significance from repetition.

### Why It Hurts
The graph gets noisy.

### What To Prevent
Require:
- structural event evidence
- contextual event language
- temporal anchoring
- participant involvement

---

## 28. AN EVENT CAN BE A NAME ROOT FOR MANY LATER REFERENCES

### Problem
Later chapters may use shorthand references derived from the landmark.

### Failure Mode
The resolver fails to connect the shorthand.

### Why It Hurts
Readers understand it immediately, the graph does not.

### What To Prevent
Support:
- event stems
- aliases
- shorthand variants
- abbreviation-like references

---

## 29. LANDMARKS CAN HAVE PUBLIC AND PRIVATE NAMES

### Problem
An event may be called one thing in public and another privately.

### Failure Mode
The graph stores only one label.

### Why It Hurts
Power dynamics are lost.

### What To Prevent
Track:
- public name
- private code name
- faction name
- historical name

---

## 30. EVENT NAMES MAY BE METAPHORICAL

### Problem
A speaker may use a metaphorical name for an event.

### Failure Mode
The metaphor becomes canonical.

### Why It Hurts
Rhetorical speech becomes ontology again.

### What To Prevent
Tag name source as:
- literal
- metaphorical
- ironic
- sarcastic
- propagandistic
- commemorative

---

## 31. EVENT NAME RECOGNITION SHOULD FEED SOCIAL GRAPH AND LIFE STATUS GRAPH

### Problem
Major landmarks often affect:
- deaths
- revivals
- alliances
- betrayals
- status changes

### Failure Mode
The landmark stays isolated.

### Why It Hurts
Landmarks and graph state should reinforce each other.

### What To Prevent
Link event names to:
- life-status transitions
- relationship transitions
- ontology transitions
- legacy signals

---

## 32. HISTORICAL LANDMARKS SHOULD HAVE THEIR OWN RESOLVER LATER

### Problem
Once event naming gets complex enough, a resolver will be useful.

### Failure Mode
The system keeps doing this in ad hoc rules forever.

### Why It Hurts
You will eventually want:
- alias merging
- naming provenance
- scope-aware grouping
- retrospective naming

### What To Prevent
Plan for a dedicated `LandmarkResolver` later.

---

## 33. EVALUATION SHOULD CHECK FOR LANDMARK FRAGMENTATION

### Problem
The same landmark can appear under multiple labels.

### Failure Mode
Evaluation only checks entities, not events.

### Why It Hurts
Event identity bugs will hide in plain sight.

### What To Prevent
Track:
- duplicate landmark candidates
- alias clusters
- reference-only event mentions
- retrospective merge opportunities

---

## FINAL PRINCIPLE

BookBuddy should be able to tell the difference between:
- a one-off event
- a named landmark
- a campaign
- a war
- an era
- a commemorative event
- a propaganda label
- a retrospective label
- a recurring event
- an unnamed but important historical turning point

If it cannot do that, then it is not understanding the story’s history.

It is just filing chaos under “something happened.”