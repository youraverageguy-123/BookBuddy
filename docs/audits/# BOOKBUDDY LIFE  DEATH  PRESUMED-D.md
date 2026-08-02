# BOOKBUDDY LIFE / DEATH / PRESUMED-DEAD / REVIVAL AUDIT
## Stop the graph from treating every mention of a dead character as resurrection

## HARD RULE
Do **not** hardcode book-specific names or examples.

This audit is about **status over time**, **narrator knowledge**, **posthumous mention**, **presumed death**, **confirmed death**, and **revival/reappearance**.

The system must distinguish:
- alive
- dead
- presumed dead
- missing
- unconfirmed
- revived
- fake death
- offscreen status
- narrator belief
- reader knowledge
- current story-time reality

---

## 1. DEATH IS A STATE, NOT A PERMANENT MERGE RESULT

### Problem
A character is reported dead, then later shown alive.

### Failure Mode
The graph permanently stores dead status and never updates it.

### Why It Hurts
Big series constantly lie, mislead, and delay confirmation.

### What to Prevent
Store death as a time-based state with confidence and provenance.

---

## 2. MENTIONING A DEAD CHARACTER DOES NOT MAKE THEM ALIVE

### Problem
Dead characters are often mentioned many times after death.

### Failure Mode
The graph treats the repeated mention as evidence of life.

### Why It Hurts
Posthumous mentions are not resurrection.

### What to Prevent
A mention of a dead character should usually update:
- memory relevance
- emotional significance
- narrative importance

not life status.

---

## 3. PRESUMED DEAD IS NOT CONFIRMED DEAD

### Problem
A character may be believed dead by some characters but not all.

### Failure Mode
The graph converts rumor into fact too early.

### Why It Hurts
Different characters have different knowledge.

### What to Prevent
Use distinct statuses:
- presumed_dead
- unconfirmed_missing
- confirmed_dead
- alive
- revived

---

## 4. DIFFERENT CHARACTERS MAY HAVE DIFFERENT BELIEFS ABOUT THE SAME PERSON

### Problem
One character thinks someone is dead.
Another says they are alive.
The reader may know more than either of them.

### Failure Mode
The graph stores one global truth too early.

### Why It Hurts
Perspective matters.

### What to Prevent
Store:
- speaker belief
- narrator belief
- reader-visible truth
- story-time truth
- confidence

---

## 5. LATER CONFIRMATION SHOULD UPDATE STATUS APPEND-ONLY

### Problem
A later chapter confirms that a presumed-dead character is alive.

### Failure Mode
The system overwrites the earlier dead belief and loses history.

### Why It Hurts
The false-death arc matters.

### What to Prevent
Append a new status event:
- chapter X: presumed dead
- chapter Y: confirmed alive

Never delete earlier belief history.

---

## 6. CONFIRMED DEAD SHOULD NOT AUTO-REVERT BECAUSE OF MENTION FREQUENCY

### Problem
Some dead characters are mentioned repeatedly because they matter.

### Failure Mode
The graph starts treating them as alive again.

### Why It Hurts
This creates status thrashing.

### What to Prevent
Life status should only change on explicit evidence:
- direct appearance
- direct statement
- reliable confirmation
- explicit resurrection / survival scene

---

## 7. OFFSCREEN DEATH AND OFFSCREEN SURVIVAL ARE DIFFERENT

### Problem
A character is reported dead offscreen, then later appears alive.

### Failure Mode
The graph assumes offscreen report is final.

### Why It Hurts
Books love deception.

### What to Prevent
Mark offscreen reports as:
- reported_dead
- likely_dead
- confirmed_dead

not just dead.

---

## 8. REVIVAL / RESURRECTION / RECOVERY NEED THEIR OWN STATE

### Problem
A character may die, then later return.
Or appear dead, then survive.
Or be repaired / restored / resurrected.

### Failure Mode
The system loses the transition.

### Why It Hurts
The narrative arc becomes invisible.

### What to Prevent
Track:
- death event
- revival event
- restored event
- reincarnated event
- repaired event
- cloned return
- body recovery

---

## 9. SOME CHARACTERS STAY DEAD FOREVER

### Problem
A character may remain dead across many books.

### Failure Mode
The graph keeps re-evaluating them as potentially alive every time they are mentioned.

### Why It Hurts
Dead characters should not reopen unless evidence supports it.

### What to Prevent
Use a strong dead status with low reactivation probability unless explicit evidence appears.

---

## 10. DEATH CONFIDENCE SHOULD BE SEPARATE FROM DEATH STATUS

### Problem
Some deaths are certain.
Some are rumors.
Some are battlefield assumptions.

### Failure Mode
Everything becomes the same dead flag.

### Why It Hurts
The graph cannot represent uncertainty.

### What to Prevent
Track:
- life_status
- life_confidence
- status_source
- chapter_of_status

---

## 11. A DEAD CHARACTER MAY STILL HAVE ACTIVE RELATIONSHIPS IN MEMORY

### Problem
Other characters may grieve, hate, honor, or remember them.

### Failure Mode
The graph deletes relational impact when the person dies.

### Why It Hurts
Dead characters still shape the story.

### What to Prevent
Preserve:
- grief relation
- memorial relation
- revenge relation
- legacy relation
- memory relation

---

## 12. POSTHUMOUS MENTIONS SHOULD INCREASE LEGACY, NOT LIFE STATUS

### Problem
A dead person can remain important because people keep talking about them.

### Failure Mode
The system confuses narrative relevance with biological life.

### Why It Hurts
Legacy is not survival.

### What to Prevent
Use separate scores:
- life_status
- narrative_importance
- legacy_importance
- memory_strength

---

## 13. MAYBE-DEAD CHARACTERS SHOULD NOT BE MERGED AWAY

### Problem
A “dead” entity might later return.

### Failure Mode
The resolver prunes or finalizes them too aggressively.

### Why It Hurts
The graph loses continuity.

### What to Prevent
Keep unresolved or presumed-dead entities alive in the graph until strong confirmation.

---

## 14. MULTIPLE NARRATORS MAY REPORT DIFFERENT DEATH STATES

### Problem
One POV says the person died.
Another POV later says they survived.

### Failure Mode
The graph picks one narrator and treats them as omniscient.

### Why It Hurts
Narrative perspective is part of the truth model.

### What to Prevent
Store source-specific death evidence:
- narrator
- speaker
- witness
- rumor
- confirmed observation

---

## 15. BATTLEFIELD ASSUMPTIONS ARE NOT CONFIRMATION

### Problem
Characters often assume someone died because the situation looked fatal.

### Failure Mode
The graph treats assumption as fact.

### Why It Hurts
Battle reports are often wrong.

### What to Prevent
Mark as:
- presumed_dead
- highly_probable_dead
- not_confirmed

until explicit confirmation exists.

---

## 16. CORPSE VISUALS ARE NOT ALWAYS FINAL

### Problem
A character may appear dead, wounded, lost, or destroyed, but later survive.

### Failure Mode
Visual evidence becomes permanent death.

### Why It Hurts
The narrative may intentionally mislead.

### What to Prevent
Track physical evidence separately from confirmed death.

---

## 17. DEATH SHOULD BE TIMELINE-AWARE

### Problem
A character may be dead in one book and alive in a prequel, flashback, memory, or earlier timeline.

### Failure Mode
The graph applies later status backwards.

### Why It Hurts
Timeline confusion.

### What to Prevent
Store status by:
- story chapter
- chronological window
- narrative order
- timeline context

---

## 18. FLASHBACKS OF DEAD CHARACTERS ARE NOT REVIVAL

### Problem
A dead character appears in a memory or flashback.

### Failure Mode
The graph thinks the character is alive again.

### Why It Hurts
Flashbacks are not resurrection.

### What to Prevent
Tag as:
- flashback presence
- memory presence
- archive presence
- dead_at_time_of_scene = true/false

---

## 19. DREAMS AND GHOSTS SHOULD NOT AUTO-CONFIRM LIFE

### Problem
A dream or vision may feature a dead character.

### Failure Mode
The graph interprets a dream appearance as survival.

### Why It Hurts
Dreams are not evidence of life.

### What to Prevent
Treat dream appearances as:
- dreamed presence
- symbolic presence
- hallucinated presence

not actual life status.

---

## 20. LOOKS ALIVE IS NOT THE SAME AS CONFIRMED ALIVE

### Problem
A character may appear in text before status is explicitly confirmed.

### Failure Mode
The graph updates to alive too early.

### Why It Hurts
Ambiguous reappearances are common.

### What to Prevent
Use a transition state:
- presumed_alive
- seen_unconfirmed
- confirmed_alive

---

## 21. STORY KNOWLEDGE AND READER KNOWLEDGE MUST DIFFER

### Problem
The reader may know a character is alive, while some characters in the book do not.

### Failure Mode
The graph flattens knowledge levels.

### Why It Hurts
Spoiler-safe reasoning breaks.

### What to Prevent
Track:
- reader_visible_status
- narrator_visible_status
- character_belief_status
- global_story_status

---

## 22. CHARACTER MEMORY OF THE DEAD SHOULD PERSIST

### Problem
A dead character may remain central to another character’s arc.

### Failure Mode
The system discards them from social logic entirely.

### Why It Hurts
Grief, revenge, and guilt arcs depend on the dead.

### What to Prevent
Keep dead characters in:
- memorial networks
- emotional networks
- revenge chains
- lineage networks

---

## 23. SOME CHARACTERS ARE “DEAD TO ONE PERSON” BUT NOT DEAD IN THE STORY

### Problem
Characters may think someone is dead, disowned, erased, or spiritually gone.

### Failure Mode
The graph converts social severance into literal death.

### Why It Hurts
Metaphor becomes ontology again.

### What to Prevent
Separate:
- literal death
- presumed death
- social death
- symbolic death
- emotional death

---

## 24. FAKE DEATH / STAGED DEATH / DISGUISED SURVIVAL

### Problem
A character may fake their death.

### Failure Mode
The system can’t distinguish deception from real death.

### Why It Hurts
This is a classic plot mechanism.

### What to Prevent
Add event labels:
- fake death
- staged death
- survival concealment
- false report
- identity concealment

---

## 25. CLONES, COPIES, RESURRECTIONS, AND RECONSTRUCTED IDENTITIES

### Problem
A character may return as:
- clone
- copy
- restored body
- reconstructed mind
- backup
- reincarnation

### Failure Mode
The graph treats all returns as the same kind of survival.

### Why It Hurts
Identity continuity becomes unclear.

### What to Prevent
Add transition types:
- same_identity_return
- copy_return
- reconstructed_return
- revived_return
- alternate_self_return

---

## 26. DEATH MENTION VS DEATH EVENT

### Problem
A book may mention a dead person’s name without re-narrating the death.

### Failure Mode
The system creates a fresh death event every time they are mentioned.

### Why It Hurts
Event history becomes noisy.

### What to Prevent
Only create a death event when the text actually describes death or confirms it.

---

## 27. MENTION FREQUENCY IS NOT LIFE EVIDENCE

### Problem
Dead characters can be mentioned constantly because of legacy, grief, or political significance.

### Failure Mode
The graph increases life confidence from name frequency.

### Why It Hurts
The wrong signal is rewarded.

### What to Prevent
Treat mention frequency as:
- relevance
- memory
- legacy
- emotional salience

not direct life evidence.

---

## 28. CROSS-BOOK CONTINUITY NEEDS DEAD-STATUS INHERITANCE WITH PENALTY

### Problem
A series may carry forward older status into later books.

### Failure Mode
Old death assumptions remain permanently frozen.

### Why It Hurts
Later books can override earlier belief.

### What to Prevent
Inherited dead status should be:
- lower confidence
- boundary-scoped
- re-evaluable with local evidence

---

## 29. DEAD BUT STILL ACTIVE IN THE GENEALOGICAL OR POLITICAL GRAPH

### Problem
A dead character may still matter because of lineage, claims, titles, or institutions.

### Failure Mode
The system removes them entirely from graph reasoning.

### Why It Hurts
Dead people still have consequences.

### What to Prevent
Keep dead entities in:
- family graph
- title inheritance
- political claims
- memorial relations
- historical references

---

## 30. STATUS MUST BE APPEND-ONLY

### Problem
Life status can change across the series.

### Failure Mode
Overwriting destroys narrative evidence.

### Why It Hurts
You lose the story of uncertainty and confirmation.

### What to Prevent
Use:
- entity_state_history
- chapter-bound status events
- confidence trail
- source provenance

---

## 31. THE SYSTEM SHOULD SUPPORT:
- dead
- presumed dead
- missing
- alive
- confirmed alive
- revived
- fake-dead
- historical-only
- remembered-only

without collapsing them into one flag.

---

## FINAL PRINCIPLE

BookBuddy should not treat every mention of a dead person as a resurrection.
It should track:
- what the narrator believes
- what the characters believe
- what the reader knows
- what the text confirms
- what the status was at that chapter
- what later chapters overturn

If it cannot do that, then it is not modeling the story.
It is just getting emotionally attached to corpses and pretending that’s ontology.