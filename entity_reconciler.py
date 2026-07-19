from collections import defaultdict
from itertools import combinations


MAX_BLOCK_SIZE = 50
AUTO_MERGE_SCORE = 1.55
REVIEW_SCORE = 0.9

TITLE_PREFIXES = {
    "baron", "captain", "chief", "commander", "count", "countess", "doctor",
    "dr", "duke", "duchess", "emperor", "empress", "governor", "king",
    "lady", "lord", "magistrate", "major", "minister", "miss", "mr", "mrs",
    "ms", "officer", "president", "prince", "princess", "professor", "queen",
    "senator", "sir", "warden",
}

TITLE_PREFIX_CLASSES = {
    "mr": "masculine",
    "sir": "masculine",
    "mrs": "feminine",
    "ms": "feminine",
    "miss": "feminine",
    "lady": "feminine",
}

LOW_INFORMATION_SUFFIXES = {
    "boy", "brother", "child", "daughter", "father", "friend", "girl",
    "guard", "husband", "man", "mother", "servant", "sister", "son",
    "uncle", "wife", "woman",
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


def _last_token(name: str) -> str:
    parts = str(name or "").split()
    return parts[-1].lower() if parts else ""


def _tokens(value: str) -> list[str]:
    return [token for token in str(value or "").lower().split() if token]


def _is_title_prefix(token: str) -> bool:
    token = str(token or "").lower()
    if token in TITLE_PREFIXES:
        return True
    return token.startswith("arch") and token[4:] in TITLE_PREFIXES


def _strip_title_prefix(tokens: list[str]) -> list[str]:
    stripped = list(tokens)
    while len(stripped) > 1 and _is_title_prefix(stripped[0]):
        stripped.pop(0)
    return stripped


def _core_key(value: str) -> str:
    return " ".join(_strip_title_prefix(_tokens(value)))


def _has_title_prefix(value: str) -> bool:
    tokens = _tokens(value)
    return bool(tokens and _is_title_prefix(tokens[0]))


def _title_prefix(value: str) -> str:
    tokens = _tokens(value)
    return tokens[0] if tokens and _is_title_prefix(tokens[0]) else ""


def _suffix_key(value: str) -> str:
    tokens = _strip_title_prefix(_tokens(value))
    if not tokens:
        return ""
    suffix = tokens[-1]
    if len(suffix) <= 2 or suffix in LOW_INFORMATION_SUFFIXES:
        return ""
    return suffix


def _is_standalone_suffix(sig: dict) -> bool:
    return sig["canonical_key"] and sig["canonical_key"] == sig["suffix_key"]


def _is_full_suffix_owner(sig: dict) -> bool:
    return bool(sig["suffix_key"] and sig["stripped_token_count"] > 1 and not sig["has_title_prefix"])


def _has_incompatible_title_prefix(left: dict, right: dict) -> bool:
    left_class = TITLE_PREFIX_CLASSES.get(left["title_prefix"])
    right_class = TITLE_PREFIX_CLASSES.get(right["title_prefix"])
    return bool(left_class and right_class and left_class != right_class)


def _load_entity_signatures(db):
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, canonical_name, entity_type, first_seen_chapter,
                   last_verified_chapter, confidence, surface_form_class,
                   mention_count, boundary_title_id, boundary_book_id,
                   boundary_volume_id, session_id, COALESCE(inherited_confidence, 1.0)
            FROM entities
            WHERE entity_type != 'LOCATION'
        """)
        entities = {
            entity_id: {
                "id": entity_id,
                "canonical": canonical_name,
                "canonical_key": db.normalize_alias_key(canonical_name),
                "entity_type": entity_type,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "confidence": confidence or 0,
                "surface_class": surface_class or "",
                "mention_count": mention_count or 0,
                "boundary_title_id": boundary_title_id,
                "boundary_book_id": boundary_book_id,
                "boundary_volume_id": boundary_volume_id,
                "session_id": session_id,
                "inherited_confidence": inherited_confidence if inherited_confidence is not None else 1.0,
                "aliases": set(),
                "titles": set(),
                "neighbors": set(),
                "events": set(),
                "core_keys": set(),
                "suffix_key": "",
                "has_title_prefix": False,
                "title_prefix": "",
                "stripped_token_count": 0,
            }
            for (
                entity_id,
                canonical_name,
                entity_type,
                first_seen,
                last_seen,
                confidence,
                surface_class,
                mention_count,
                boundary_title_id,
                boundary_book_id,
                boundary_volume_id,
                session_id,
                inherited_confidence,
            )
            in cursor.fetchall()
        }

        cursor.execute("""
            SELECT entity_id, alias_key
            FROM aliases
            WHERE COALESCE(status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
        """)
        for entity_id, alias_key in cursor.fetchall():
            if entity_id in entities and alias_key:
                entities[entity_id]["aliases"].add(alias_key)

        cursor.execute("""
            SELECT entity_id, title_key
            FROM title_links
            WHERE COALESCE(status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
        """)
        for entity_id, title_key in cursor.fetchall():
            if entity_id in entities and title_key:
                entities[entity_id]["titles"].add(title_key)

        cursor.execute("SELECT source_id, target_id FROM relationships")
        for source_id, target_id in cursor.fetchall():
            if source_id in entities and target_id in entities:
                entities[source_id]["neighbors"].add(target_id)
                entities[target_id]["neighbors"].add(source_id)

        cursor.execute("SELECT event_id, entity_id FROM event_participants")
        for event_id, entity_id in cursor.fetchall():
            if entity_id in entities:
                entities[entity_id]["events"].add(event_id)

    for sig in entities.values():
        raw_forms = {sig["canonical"], sig["canonical_key"], *sig["aliases"], *sig["titles"]}
        for form in raw_forms:
            core = _core_key(form)
            if core and core not in LOW_INFORMATION_SUFFIXES:
                sig["core_keys"].add(core)
        sig["suffix_key"] = _suffix_key(sig["canonical_key"])
        sig["has_title_prefix"] = _has_title_prefix(sig["canonical_key"])
        sig["title_prefix"] = _title_prefix(sig["canonical_key"])
        sig["stripped_token_count"] = len(_strip_title_prefix(_tokens(sig["canonical_key"])))

    return entities


def _suffix_owners(entities):
    owners = defaultdict(set)
    for entity_id, sig in entities.items():
        tokens = _strip_title_prefix(_tokens(sig["canonical_key"]))
        suffix = sig["suffix_key"]
        if suffix and len(tokens) > 1 and not sig["has_title_prefix"]:
            owners[(sig["entity_type"], suffix)].add(entity_id)
    return owners


def _dominant_suffix_owners(entities, suffix_owners):
    dominant = {}
    for suffix_key, owner_ids in suffix_owners.items():
        ranked = sorted(
            owner_ids,
            key=lambda entity_id: (
                entities[entity_id]["mention_count"],
                entities[entity_id]["confidence"],
                -entities[entity_id]["id"],
            ),
            reverse=True,
        )
        if not ranked:
            continue
        top_id = ranked[0]
        top_mentions = entities[top_id]["mention_count"]
        next_mentions = entities[ranked[1]]["mention_count"] if len(ranked) > 1 else 0
        if top_mentions >= 3 and top_mentions >= (next_mentions * 2):
            dominant[suffix_key] = top_id
    return dominant


def _blocking_pairs(db, entities):
    blocks = defaultdict(set)
    for entity_id, sig in entities.items():
        entity_type = sig["entity_type"]
        canonical_key = sig["canonical_key"]
        if canonical_key:
            blocks[(entity_type, "canonical", canonical_key)].add(entity_id)
        for alias_key in sig["aliases"]:
            blocks[(entity_type, "alias", alias_key)].add(entity_id)
        for title_key in sig["titles"]:
            blocks[(entity_type, "title", title_key)].add(entity_id)
        for core_key in sig["core_keys"]:
            blocks[(entity_type, "core", core_key)].add(entity_id)
        last = _last_token(sig["canonical"])
        if len(last) > 2:
            blocks[(entity_type, "last", db.normalize_alias_key(last))].add(entity_id)
        suffix = sig["suffix_key"]
        if suffix:
            blocks[(entity_type, "suffix", suffix)].add(entity_id)
        for neighbor_id in sig["neighbors"]:
            blocks[(entity_type, "neighbor", neighbor_id)].add(entity_id)
        for event_id in sig["events"]:
            blocks[(entity_type, "event", event_id)].add(entity_id)

    pairs = set()
    for members in blocks.values():
        if len(members) < 2 or len(members) > MAX_BLOCK_SIZE:
            continue
        for left, right in combinations(sorted(members), 2):
            pairs.add((left, right))
    return pairs


def _score_pair(left, right, suffix_owners, dominant_suffix_owners):
    if left["entity_type"] != right["entity_type"]:
        return 0.0, {"hard_rejection": "entity type mismatch"}
    left_book = left.get("boundary_book_id") or left.get("boundary_title_id")
    right_book = right.get("boundary_book_id") or right.get("boundary_title_id")
    if left_book and right_book and left_book != right_book:
        return 0.0, {"hard_rejection": "different book boundary"}
    if left.get("boundary_volume_id") and right.get("boundary_volume_id") and left["boundary_volume_id"] != right["boundary_volume_id"]:
        return 0.0, {"hard_rejection": "different volume boundary"}
    if left.get("session_id") and right.get("session_id") and left["session_id"] != right["session_id"]:
        return 0.0, {"hard_rejection": "different session boundary"}
    if (left.get("inherited_confidence") or 1.0) < 0.999 or (right.get("inherited_confidence") or 1.0) < 0.999:
        left_terms = {left["canonical_key"], *left["aliases"]}
        right_terms = {right["canonical_key"], *right["aliases"]}
        if left_terms.isdisjoint(right_terms) and not (left["events"] & right["events"]):
            return 0.0, {"hard_rejection": "inherited candidate without direct local corroboration"}
    if _has_incompatible_title_prefix(left, right):
        return 0.0, {"hard_rejection": "incompatible title evidence"}

    left_terms = {left["canonical_key"], *left["aliases"], *left["core_keys"]}
    right_terms = {right["canonical_key"], *right["aliases"], *right["core_keys"]}
    left_terms.discard("")
    right_terms.discard("")

    shared_terms = left_terms & right_terms
    shared_cores = left["core_keys"] & right["core_keys"]
    shared_titles = left["titles"] & right["titles"]
    shared_neighbors = left["neighbors"] & right["neighbors"]
    shared_events = left["events"] & right["events"]

    score = 0.0
    cap_score_to_review = False
    positive_identity_evidence = False
    features = {
        "shared_terms": sorted(shared_terms),
        "shared_cores": sorted(shared_cores),
        "shared_titles": sorted(shared_titles),
        "shared_neighbors": len(shared_neighbors),
        "shared_events": len(shared_events),
        "suffix_overlap": False,
        "name_containment": False,
    }
    if left["canonical_key"] and left["canonical_key"] == right["canonical_key"]:
        score += 1.0
        positive_identity_evidence = True
    if shared_terms:
        score += 0.9
        positive_identity_evidence = True
    if shared_cores:
        score += 0.35
        positive_identity_evidence = True
    if shared_titles:
        score += 0.35
        positive_identity_evidence = True
    if _last_token(left["canonical"]) and _last_token(left["canonical"]) == _last_token(right["canonical"]):
        score += 0.25
    if left["canonical_key"] in right_terms or right["canonical_key"] in left_terms:
        score += 0.45
        positive_identity_evidence = True
        features["name_containment"] = True

    left_suffix = left["suffix_key"]
    right_suffix = right["suffix_key"]
    if left_suffix and left_suffix == right_suffix:
        features["suffix_overlap"] = True
        owner_count = len(suffix_owners.get((left["entity_type"], left_suffix), set()))
        one_is_suffix_only = _is_standalone_suffix(left) or _is_standalone_suffix(right)
        one_is_titled = left["has_title_prefix"] or right["has_title_prefix"]
        one_is_full_owner = _is_full_suffix_owner(left) or _is_full_suffix_owner(right)
        if owner_count <= 1:
            if one_is_full_owner and (one_is_suffix_only or one_is_titled):
                score += 1.15
                positive_identity_evidence = True
            elif owner_count == 0 and one_is_suffix_only and one_is_titled:
                score += 1.15
                positive_identity_evidence = True
            elif one_is_suffix_only or one_is_titled:
                score += 0.45
            else:
                score += 0.35
        elif one_is_suffix_only:
            dominant_id = dominant_suffix_owners.get((left["entity_type"], left_suffix))
            pair_ids = {left["id"], right["id"]}
            if dominant_id in pair_ids and one_is_full_owner:
                score += 1.15
                positive_identity_evidence = True
        elif one_is_titled:
            dominant_id = dominant_suffix_owners.get((left["entity_type"], left_suffix))
            pair_ids = {left["id"], right["id"]}
            if dominant_id in pair_ids and one_is_full_owner:
                score += 1.15
                positive_identity_evidence = True
            else:
                score += 0.55
        if owner_count > 0 and one_is_titled and one_is_suffix_only and not one_is_full_owner:
            cap_score_to_review = True

    score += min(len(shared_neighbors), 3) * 0.12
    score += min(len(shared_events), 3) * 0.08

    if left["first_seen"] is not None and right["last_seen"] is not None:
        if left["first_seen"] <= right["last_seen"] and right["first_seen"] <= left["last_seen"]:
            score += 0.10

    low_value_classes = {"role", "descriptor", "location_fragment"}
    if left["surface_class"] in low_value_classes or right["surface_class"] in low_value_classes:
        score -= 0.25

    if cap_score_to_review:
        score = min(score, REVIEW_SCORE)
    if not positive_identity_evidence:
        score = min(score, REVIEW_SCORE - 0.01)
        features["hard_rejection"] = "no positive identity evidence"

    features["positive_identity_evidence"] = positive_identity_evidence
    return score, features


def reconcile_entities(db, auto_merge: bool = True) -> dict:
    entities = _load_entity_signatures(db)
    suffix_owners = _suffix_owners(entities)
    dominant_suffix_owners = _dominant_suffix_owners(entities, suffix_owners)
    pairs = _blocking_pairs(db, entities)
    disjoint = DisjointSet()
    reviewed = 0
    merged_pairs = 0
    actual_merges = 0

    for left_id, right_id in pairs:
        score, features = _score_pair(entities[left_id], entities[right_id], suffix_owners, dominant_suffix_owners)
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
            for entity_id in group[1:]:
                merged_survivor = db.merge_entities(survivor, entity_id)
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
