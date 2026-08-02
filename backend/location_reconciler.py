from collections import defaultdict
from itertools import combinations
MAX_BLOCK_SIZE = 60
AUTO_MERGE_SCORE = 1.55
REVIEW_SCORE = 0.95
GENERIC_LOCATION_TERMS = {
    "apartment", "avenue", "bay", "building", "camp", "city", "club",
    "coast", "drive", "estate", "house", "hotel", "island", "lane",
    "mine", "planet", "region", "river", "road", "room", "street",
    "town", "valley", "village",
}

class DisjointSet:
    def __init__(self):
        self.parent = {}
    def find(self, item):
        self.parent.setdefault(item, item)
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]
    def union(self, left, right):
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root
    def groups(self):
        grouped = defaultdict(list)
        for item in list(self.parent):
            grouped[self.find(item)].append(item)
        return grouped.values()
def _tokens(value: str) -> list[str]:
    return [token for token in str(value or "").lower().split() if token]
def _last_token(value: str) -> str:
    tokens = _tokens(value)
    return tokens[-1] if tokens else ""
def _is_generic_location_key(key: str) -> bool:
    tokens = _tokens(key)
    return len(tokens) == 1 and tokens[0] in GENERIC_LOCATION_TERMS
def _has_specific_overlap(left_key: str, right_key: str) -> bool:
    left_tokens = set(_tokens(left_key)) - GENERIC_LOCATION_TERMS
    right_tokens = set(_tokens(right_key)) - GENERIC_LOCATION_TERMS
    return bool(left_tokens & right_tokens)
def _load_location_signatures(db):
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, canonical_name, first_seen_chapter, last_verified_chapter,
                   confidence, surface_form_class, location_subtype
            FROM entities
            WHERE entity_type = 'LOCATION'
        """)
        locations = {
            entity_id: {
                "id": entity_id,
                "canonical": canonical_name,
                "canonical_key": db.normalize_alias_key(canonical_name),
                "first_seen": first_seen,
                "last_seen": last_seen,
                "confidence": confidence or 0,
                "surface_class": surface_class or "",
                "location_subtype": location_subtype or "",
                "aliases": set(),
                "titles": set(),
                "neighbors": set(),
                "events": set(),
            }
            for (
                entity_id,
                canonical_name,
                first_seen,
                last_seen,
                confidence,
                surface_class,
                location_subtype,
            ) in cursor.fetchall()
        }
        cursor.execute("""
            SELECT entity_id, alias_key
            FROM aliases
            WHERE COALESCE(status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
        """)
        for entity_id, alias_key in cursor.fetchall():
            if entity_id in locations and alias_key:
                locations[entity_id]["aliases"].add(alias_key)
        cursor.execute("""
            SELECT entity_id, title_key
            FROM title_links
            WHERE COALESCE(status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
        """)
        for entity_id, title_key in cursor.fetchall():
            if entity_id in locations and title_key:
                locations[entity_id]["titles"].add(title_key)
        cursor.execute("SELECT source_id, target_id FROM relationships")
        for source_id, target_id in cursor.fetchall():
            if source_id in locations:
                locations[source_id]["neighbors"].add(target_id)
            if target_id in locations:
                locations[target_id]["neighbors"].add(source_id)

        cursor.execute("SELECT event_id, entity_id FROM event_participants")
        for event_id, entity_id in cursor.fetchall():
            if entity_id in locations:
                locations[entity_id]["events"].add(event_id)
    return locations
def _blocking_pairs(db, locations):
    blocks = defaultdict(set)
    for location_id, sig in locations.items():
        canonical_key = sig["canonical_key"]
        if canonical_key and not _is_generic_location_key(canonical_key):
            blocks[("canonical", canonical_key)].add(location_id)
            for token in set(_tokens(canonical_key)) - GENERIC_LOCATION_TERMS:
                if len(token) > 2:
                    blocks[("token", db.normalize_alias_key(token))].add(location_id)
        for alias_key in sig["aliases"]:
            if alias_key and not _is_generic_location_key(alias_key):
                blocks[("alias", alias_key)].add(location_id)
                for token in set(_tokens(alias_key)) - GENERIC_LOCATION_TERMS:
                    if len(token) > 2:
                        blocks[("token", db.normalize_alias_key(token))].add(location_id)
        for title_key in sig["titles"]:
            if title_key and not _is_generic_location_key(title_key):
                blocks[("title", title_key)].add(location_id)

        last = _last_token(canonical_key)
        if len(last) > 2 and last not in GENERIC_LOCATION_TERMS:
            blocks[("last", db.normalize_alias_key(last))].add(location_id)
        subtype = sig["location_subtype"]
        if subtype and subtype != "fragment":
            for event_id in sig["events"]:
                blocks[("event", event_id)].add(location_id)
            for neighbor_id in sig["neighbors"]:
                blocks[("neighbor", neighbor_id)].add(location_id)
    pairs = set()
    for members in blocks.values():
        if len(members) < 2 or len(members) > MAX_BLOCK_SIZE:
            continue
        for left, right in combinations(sorted(members), 2):
            pairs.add((left, right))
    return pairs
def _score_pair(left, right):
    left_terms = {left["canonical_key"], *left["aliases"]}
    right_terms = {right["canonical_key"], *right["aliases"]}
    left_terms.discard("")
    right_terms.discard("")

    shared_terms = {
        term for term in (left_terms & right_terms)
        if not _is_generic_location_key(term)
    }
    shared_titles = left["titles"] & right["titles"]
    shared_neighbors = left["neighbors"] & right["neighbors"]
    shared_events = left["events"] & right["events"]
    score = 0.0
    positive_identity_evidence = False
    features = {
        "shared_terms": sorted(shared_terms),
        "shared_titles": sorted(shared_titles),
        "shared_neighbors": len(shared_neighbors),
        "shared_events": len(shared_events),
        "specific_overlap": _has_specific_overlap(left["canonical_key"], right["canonical_key"]),
        "generic_location": (
            _is_generic_location_key(left["canonical_key"])
            or _is_generic_location_key(right["canonical_key"])
        ),
    }
    if left["canonical_key"] and left["canonical_key"] == right["canonical_key"]:
        score += 1.15
        positive_identity_evidence = True
    if shared_terms:
        score += 1.0
        positive_identity_evidence = True
    if shared_titles:
        score += 0.35
        positive_identity_evidence = True

    if left["canonical_key"] in right_terms or right["canonical_key"] in left_terms:
        score += 0.65
        positive_identity_evidence = True
    left_last = _last_token(left["canonical_key"])
    right_last = _last_token(right["canonical_key"])
    if left_last and left_last == right_last and left_last not in GENERIC_LOCATION_TERMS:
        score += 0.25
    if _has_specific_overlap(left["canonical_key"], right["canonical_key"]):
        score += 0.25
        positive_identity_evidence = True
    if left["location_subtype"] and left["location_subtype"] == right["location_subtype"]:
        score += 0.15
    score += min(len(shared_neighbors), 3) * 0.10
    score += min(len(shared_events), 3) * 0.08
    if left["first_seen"] is not None and right["last_seen"] is not None:
        if left["first_seen"] <= right["last_seen"] and right["first_seen"] <= left["last_seen"]:
            score += 0.08
    if left["location_subtype"] == "fragment" or right["location_subtype"] == "fragment":
        score -= 0.45
    if left["surface_class"] == "location_fragment" or right["surface_class"] == "location_fragment":
        score -= 0.35
    if _is_generic_location_key(left["canonical_key"]) or _is_generic_location_key(right["canonical_key"]):
        score -= 0.55

    if not positive_identity_evidence:
        score = min(score, REVIEW_SCORE - 0.01)
        features["hard_rejection"] = "no positive identity evidence"
    features["positive_identity_evidence"] = positive_identity_evidence
    return score, features
def reconcile_locations(db, auto_merge: bool = True) -> dict:
    locations = _load_location_signatures(db)
    pairs = _blocking_pairs(db, locations)
    disjoint = DisjointSet()
    reviewed = 0
    merged_pairs = 0
    actual_merges = 0
    for left_id, right_id in pairs:
        score, features = _score_pair(locations[left_id], locations[right_id])
        if score >= AUTO_MERGE_SCORE:
            disjoint.union(left_id, right_id)
            merged_pairs += 1
        elif score >= REVIEW_SCORE:
            reviewed += 1
            db.register_merge_candidate(
                left_id,
                right_id,
                score=score,
                evidence=features,
                state="probable" if score >= 1.2 else "candidate",
            )
    merge_groups = [group for group in disjoint.groups() if len(group) > 1]
    if auto_merge:
        for group in merge_groups:
            survivor = group[0]
            for location_id in group[1:]:
                merged_survivor = db.merge_entities(survivor, location_id)
                if merged_survivor:
                    survivor = merged_survivor
                    actual_merges += 1
    return {
        "candidate_pairs": len(pairs),
        "review_candidates": reviewed,
        "auto_merge_pairs": merged_pairs,
        "merge_groups": len(merge_groups),
        "actual_merges": actual_merges,
    }
