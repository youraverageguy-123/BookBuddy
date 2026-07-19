# BOOKBUDDY RELATIONSHIP WEB EDGE CASE AUDIT
## Problems to Solve Before the Graph Becomes a Protagonist Sun System

## HARD RULE
These are **bug classes**, not book-specific rules.

Do **not** hardcode any names, factions, books, houses, species, or title examples.

The system should learn relationship structure from evidence, not from a list of fandom trivia.

---

## 1. PROTAGONIST-CENTERED GRAPH BIAS

### Problem
The graph keeps creating relationships only around the POV character or protagonist.

### Failure Mode
The relationship web becomes a star topology:
- everyone connects to the protagonist
- side characters do not connect meaningfully to each other

### Why It Hurts
Real narratives have communities, factions, inner circles, rivals, and bridges.

### What to Prevent
Track and promote:
- shared scenes
- shared events
- dialogue co-occurrence
- repeated same-group presence
- non-protagonist relationship evidence

---

## 2. INDIRECT RELATIONSHIPS MATTER

### Problem
Two characters may never directly interact, but they are strongly connected through a mutual group, family, faction, or repeated co-presence.

### Failure Mode
The graph misses the connection entirely.

### Why It Hurts
Readers infer relationships through social structure, not just direct dialogue.

### What to Prevent
Support:
- indirect edge inference
- community membership
- bridge nodes
- group proximity
- repeated co-occurrence chains

---

## 3. COMMUNITY STRUCTURE IS NOT THE SAME AS CENTRALITY

### Problem
A character can be important because they are part of a dense cluster, not because they connect to many people directly.

### Failure Mode
The system only ranks high-degree nodes and misses factions.

### Why It Hurts
Inner groups, squads, family clusters, and conspiracies become invisible.

### What to Prevent
Add:
- community detection
- cluster strength
- faction cohesion
- bridge detection
- local neighborhood density

---

## 4. ONE-SIDED RELATIONSHIPS

### Problem
Character A may trust Character B while B dislikes A.

### Failure Mode
The graph stores a single symmetric relationship score.

### Why It Hurts
Betrayal, manipulation, and hidden hostility are destroyed.

### What to Prevent
Store directional relationship state:
- A -> B
- B -> A

Do not collapse them into one score.

---

## 5. RELATIONSHIP STATE CHANGES OVER TIME

### Problem
A relationship can evolve:
- enemy -> uneasy ally
- ally -> betrayed ally
- mentor -> rival
- friend -> dead enemy

### Failure Mode
The graph stores only the latest score and loses trajectory.

### Why It Hurts
Narrative arcs and betrayal history disappear.

### What to Prevent
Track:
- relationship history
- trust trajectory
- hostility trajectory
- event-linked changes
- timestamped relationship snapshots

---

## 6. TEMPORARY ALLIANCES ARE NOT PERMANENT FRIENDSHIPS

### Problem
Characters cooperate for a mission, then split.

### Failure Mode
A short alliance gets promoted into permanent friendship.

### Why It Hurts
The graph overstates bonds.

### What to Prevent
Separate:
- temporary cooperation
- stable alliance
- personal friendship
- shared faction membership

---

## 7. SHARED FACTION DOES NOT EQUAL PERSONAL FRIENDSHIP

### Problem
Two people may be in the same group but personally dislike each other.

### Failure Mode
Faction membership gets converted into friendship.

### Why It Hurts
Social nuance disappears.

### What to Prevent
Keep separate:
- faction membership
- personal relationship
- shared mission participation
- ideological alignment

---

## 8. FAMILY WEB SHOULD NOT COLLAPSE INTO GENERAL SOCIAL GRAPH

### Problem
Family, mentorship, marriage, and adoption all behave differently from ordinary friendship.

### Failure Mode
Everything becomes a generic positive relationship.

### Why It Hurts
Kinship is structural, not just emotional.

### What to Prevent
Different relationship subclasses for:
- parent/child
- sibling
- spouse
- mentor/mentee
- guardian/protected
- adopted relation

---

## 9. MENTORSHIP IS NOT FRIENDSHIP

### Problem
A mentor may care about a student, but that is not the same as friendship.

### Failure Mode
Mentor and friend collapse into one label.

### Why It Hurts
Training, hierarchy, and dependency are lost.

### What to Prevent
Track:
- mentorship
- authority
- dependence
- respect
- affection
- rivalry

---

## 10. RANK AND COMMAND RELATIONSHIPS

### Problem
Military, political, school, or religious hierarchy is often relational.

### Failure Mode
The graph treats rank as a name or treats command as friendship.

### Why It Hurts
Authority structures are central in many books.

### What to Prevent
Support:
- superior/subordinate
- commander/member
- teacher/student
- priest/congregant
- officer/soldier

---

## 11. RELATIONSHIPS CAN BE MIXED

### Problem
Two characters may simultaneously be:
- friends
- rivals
- family
- political allies
- romantic tension

### Failure Mode
The graph stores only one label and loses complexity.

### Why It Hurts
Narratives are messy. Humans are messier.

### What to Prevent
Allow multi-label or multi-dimensional relationships:
- trust
- respect
- fear
- affection
- hostility
- dependence
- obligation

---

## 12. PUBLIC RELATIONSHIP VS PRIVATE RELATIONSHIP

### Problem
Characters may appear friendly publicly while being hostile privately.

### Failure Mode
The graph trusts public behavior only.

### Why It Hurts
Politics, court intrigue, and deception get flattened.

### What to Prevent
Separate:
- public interaction
- private interaction
- inferred hidden intent
- observed action

---

## 13. SOCIAL CIRCLES / CREWS / INNER GROUPS

### Problem
Narratives often contain tight-knit crews whose members are socially linked to each other, not just to the protagonist.

### Failure Mode
Only protagonist edges are stored.

### Why It Hurts
The graph misses the internal structure of the team.

### What to Prevent
Infer:
- crew member adjacency
- intra-group closeness
- repeated co-presence
- shared event history

---

## 14. BRIDGE CHARACTERS

### Problem
Some characters connect two otherwise separate communities.

### Failure Mode
They are treated as just another ordinary node.

### Why It Hurts
They are structurally important.

### What to Prevent
Detect:
- bridge nodes
- cross-faction mediators
- double-aligned characters
- socially central connectors

---

## 15. SHADOW RELATIONSHIPS

### Problem
A character may be connected to another through indirect or hidden mechanisms:
- family
- faction
- debt
- blackmail
- shared secret
- past trauma

### Failure Mode
Only direct explicit text is stored.

### Why It Hurts
A lot of narrative meaning is implicit.

### What to Prevent
Add optional inferred relationship layers with lower confidence.

---

## 16. REPEATED CO-OCCURRENCE SHOULD MATTER

### Problem
Characters repeatedly appearing together in scenes is a signal even when no explicit relationship is stated.

### Failure Mode
The graph ignores scene-level co-presence.

### Why It Hurts
Social bonds emerge through repetition.

### What to Prevent
Track:
- shared scene count
- shared event count
- dialogue overlap
- chapter overlap
- proximity frequency

---

## 17. SHARED EVENT PARTICIPATION IS STRONGER THAN SHARED MENTION

### Problem
Being mentioned near another character is weaker than actually taking part in the same event.

### Failure Mode
Mentions and participation get treated equally.

### Why It Hurts
Noise becomes relationship evidence.

### What to Prevent
Weight:
- event participation > scene co-occurrence > chapter co-occurrence > mention proximity

---

## 18. RELATIONSHIP EVIDENCE SHOULD BE SOURCE-AWARE

### Problem
Some relationships are observed directly, some are reported, some are remembered, some are guessed.

### Failure Mode
All evidence has the same weight.

### Why It Hurts
Rumors become truth.

### What to Prevent
Track:
- observed
- reported
- recalled
- imagined
- rumored
- dialogic

---

## 19. STORY WORLD RELATIONSHIPS VS NARRATOR BELIEFS

### Problem
The narrator may believe one relationship exists while the world reality is different.

### Failure Mode
The graph stores belief as fact.

### Why It Hurts
Unreliable narrators ruin the graph.

### What to Prevent
Separate:
- narrator belief
- story fact
- inferred fact
- uncertain fact

---

## 20. FAMILIARITY IS NOT TRUST

### Problem
Two characters may know each other well and still hate each other.

### Failure Mode
High interaction count becomes high trust.

### Why It Hurts
Repeated conflict is still relationship data.

### What to Prevent
Track multiple relationship dimensions:
- familiarity
- trust
- hostility
- respect
- fear
- dependence

---

## 21. FAMILY GROUPS ARE NOT PERSONAL RELATIONSHIPS

### Problem
A house, clan, or family line may be socially important beyond individual members.

### Failure Mode
The graph only stores individual links.

### Why It Hurts
Power structures and shared identity disappear.

### What to Prevent
Add group-level relationship graphs:
- group to group
- group to individual
- individual to group

---

## 22. ALLIANCE NETWORKS

### Problem
A character may be aligned with a faction, but also have personal ties outside the faction.

### Failure Mode
Faction replaces personal web.

### Why It Hurts
Political and social nuance collapses.

### What to Prevent
Store:
- faction membership
- alliance
- ideological alignment
- personal relationship
- operational cooperation

---

## 23. CIRCULAR / CLUSTERED RELATIONSHIPS

### Problem
Some groups are mutual webs, not center-and-spokes structures.

### Failure Mode
The graph only sees “connected to protagonist” and misses the cluster.

### Why It Hurts
The relationship network becomes unrealistic.

### What to Prevent
Promote cluster-aware modeling:
- dense subgraphs
- clique-like groups
- recurring group sessions
- shared identity clusters

---

## 24. RELATIONSHIP REVERSALS

### Problem
A close ally can become a traitor, and an enemy can become a friend.

### Failure Mode
Old relationship data gets overwritten instead of preserved.

### Why It Hurts
You lose narrative arc.

### What to Prevent
Store:
- relationship transitions
- reversal events
- betrayal points
- reconciliation events

---

## 25. RELATIONSHIP IMPLICATIONS SHOULD NOT BE OVERPROMOTED

### Problem
If two characters appear near each other, it does not always mean deep connection.

### Failure Mode
The graph makes false strong ties from weak evidence.

### Why It Hurts
The relationship web becomes inflated and fake.

### What to Prevent
Use conservative promotion:
- weak tie
- inferred tie
- confirmed tie
- stable tie

---

## 26. GROUP RELATIONSHIP DEPTH

### Problem
Some groups have internal layers:
- leaders
- lieutenants
- members
- associates
- outsiders

### Failure Mode
The graph treats the group as flat.

### Why It Hurts
Hierarchy and influence vanish.

### What to Prevent
Support nested or layered group relationships.

---

## 27. INDIRECT PAIRING THROUGH SHARED SOCIAL HUBS

### Problem
Characters connected through the same house, school, ship, squad, or faction may never directly speak but still matter to each other.

### Failure Mode
No relationship edge is stored.

### Why It Hurts
Shared environments create social structure.

### What to Prevent
Use hub-based inference:
- shared location
- shared unit
- shared institution
- shared event chain

---

## 28. NARRATIVE FOCUS SHOULD NOT ERASE SIDE CHARACTER NETWORKS

### Problem
The reader may follow one POV, but side characters still have rich networks.

### Failure Mode
The graph only knows the POV’s social circle.

### Why It Hurts
Large casts become flattened.

### What to Prevent
Allow non-POV side-character graphs to build from:
- shared scenes
- shared events
- repeated co-mentions
- group membership

---

## 29. HIGH-DEGREE NODE BIAS

### Problem
A character with many connections is not always the “main” node; they may just be a hub.

### Failure Mode
Graph logic overvalues degree centrality alone.

### Why It Hurts
Social hubs and protagonists get confused.

### What to Prevent
Balance:
- degree
- event participation
- narrative importance
- POV proximity
- community bridging

---

## 30. FUTURE MASSIVE CAST BOOKS WILL BREAK NAIVE STAR GRAPHS

### Problem
Books with large casts will expose protagonist-centric bias immediately.

### Failure Mode
The graph degenerates into a star no matter the true structure.

### Why It Hurts
The model stops looking like a story and starts looking like an awkward orbit diagram.

### What to Prevent
Test on books with:
- ensembles
- crews
- factions
- rival houses
- multi-POV networks

---

## 31. DECEPTION NETWORKS

### Problem
Characters may act friendly inside a group while secretly undermining it.

### Failure Mode
The graph only stores visible alliances.

### Why It Hurts
Hidden conflict is a major part of many stories.

### What to Prevent
Support:
- concealed hostility
- hidden loyalty
- double agents
- betrayal indicators
- trust divergence by source

---

## 32. ROMANTIC, POLITICAL, AND FAMILIAL EDGES CAN COEXIST

### Problem
The same two characters can have multiple relationship types simultaneously.

### Failure Mode
One label replaces the rest.

### Why It Hurts
Human relationships are not single-valued.

### What to Prevent
Keep edges or edge metadata for:
- romance
- family
- politics
- mentorship
- rivalry
- loyalty

---

## 33. CHARACTER GROUPS CAN BE RECOGNIZED WITHOUT EXPLICIT NAMING

### Problem
A cluster may behave like a faction even if the text never gives it a clean name.

### Failure Mode
The graph waits for a named group label that never comes.

### Why It Hurts
A lot of real book social structure is implicit.

### What to Prevent
Infer factions from:
- repeated co-membership
- shared actions
- shared goals
- social isolation from others

---

## 34. SOCIAL RELATIONSHIP WEB SHOULD BE MULTI-LAYERED

### Problem
A single flat web cannot represent:
- family
- friendship
- enmity
- duty
- allegiance
- trust
- fear
- dependence

### Failure Mode
The graph becomes oversimplified.

### Why It Hurts
That is not a relationship web, that is a cartoon.

### What to Prevent
Use multi-layer relationship modeling.

---

## 35. DIRECT AND INDIRECT EVIDENCE SHOULD STACK, NOT REPLACE

### Problem
Indirect evidence should add support, not overwrite direct evidence.

### Failure Mode
A weak co-occurrence score can override a strong explicit statement.

### Why It Hurts
The graph starts believing vibes over text.

### What to Prevent
Use evidence stacking:
- explicit statements
- co-occurrence
- group membership
- event participation
- dialogue history

---

## 36. BOOKS WITH FACTIONS, CREWS, AND CIRCLES NEED COMMUNITY DETECTION

### Problem
Without cluster detection, the graph misses crew/faction structure.

### Failure Mode
All relationships are treated individually.

### Why It Hurts
The web misses the real social architecture.

### What to Prevent
Run community detection or cluster inference over the relationship graph.

---

## 37. CROSS-REFERENCE BETWEEN RELATIONSHIPS AND ENTITY RESOLUTION

### Problem
Relationship density can help resolve ambiguous identities.

### Failure Mode
The resolver ignores social context.

### Why It Hurts
A character with many shared edges may still be treated as ambiguous.

### What to Prevent
Use network context as a resolver signal:
- shared neighbors
- cluster membership
- repeated co-participation
- relationship consistency

---

## 38. CONTEXTUAL EDGE WEIGHTING

### Problem
A relationship in a battle scene should not be weighted the same as a casual mention.

### Failure Mode
All co-presence is treated equally.

### Why It Hurts
Context changes meaning.

### What to Prevent
Weight edges by:
- scene type
- narrative source
- evidence source
- emotional intensity
- event type

---

## 39. CHANGING SOCIAL TOPOLOGY ACROSS BOOKS

### Problem
Sequels and series books can radically change social structure.

### Failure Mode
The old web dominates the new book.

### Why It Hurts
The relationship graph becomes stale and misleading.

### What to Prevent
Use boundary-aware inheritance and decay for relationship carryover.

---

## 40. FINAL PRINCIPLE

BookBuddy should not only know **who** is connected to the protagonist.

It should also know:
- who is connected to each other
- who forms communities
- who bridges groups
- who hides conflict
- who changes alliances
- who stays local to a faction
- who matters even without direct protagonist contact

If the relationship web stays protagonist-only, the graph will never feel like a real story world.

It will just be a celebrity fan chart with extra math.