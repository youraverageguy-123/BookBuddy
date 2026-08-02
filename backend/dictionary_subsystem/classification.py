from __future__ import annotations

import re


FUNCTION_CLASSES = {"pronoun", "determiner", "article", "preposition"}
_ROMAN = re.compile(r"^(?=[MDCLXVI]+$)M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_ELEMENT_SYMBOLS = frozenset(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split()
)
_NATIONAL_GROUP_HEADS = frozenset({"army", "citizen", "community", "delegation", "government", "nation", "people", "population", "public", "society", "troop"})
_NATURAL_PROCESS_VERBS = frozenset({"flow", "flood", "rise", "drain", "empty", "erode", "wind"})
_EDIBLE_OBJECT_VERBS = frozenset({"bite", "cook", "eat", "peel", "ripen", "slice", "taste"})


class SelectionClassifier:
    def classify(self, analysis: dict, story_glossary=None) -> dict:
        pos, tag, entity = analysis.get("pos", ""), analysis.get("tag", ""), analysis.get("entity_type", "")
        surface = analysis.get("forms", {}).get("original", "").strip()
        dependency = analysis.get("dependency", "")
        evidence: list[str] = []

        if pos == "PRON":
            primary, confidence, evidence = "pronoun", 0.99, ["pos:PRON"]
        elif pos == "DET":
            primary = "article" if tag in {"DT", "PDT"} and surface.casefold() in {"a", "an", "the"} else "determiner"
            confidence, evidence = 0.97, [f"pos:{pos}", f"tag:{tag}"]
        elif pos == "ADP":
            primary, confidence, evidence = "preposition", 0.96, ["pos:ADP"]
        elif entity == "PERSON":
            primary, confidence, evidence = "named_person", 0.94, ["ner:PERSON"]
        elif entity in {"GPE", "LOC", "FAC"}:
            primary, confidence, evidence = "named_place", 0.93, [f"ner:{entity}"]
        elif entity == "ORG":
            governor = str(analysis.get("governor_lemma") or "").casefold()
            nearby_nouns = {str(value).casefold() for value in analysis.get("nearby_nouns", [])}
            if governor in _NATURAL_PROCESS_VERBS and nearby_nouns & {"bank", "river", "water", "valley"}:
                primary, confidence, evidence = "named_place", 0.82, ["ner:ORG_overridden", "natural_process_context"]
            elif governor in _EDIBLE_OBJECT_VERBS:
                primary, confidence, evidence = "object", 0.82, ["ner:ORG_overridden", "edible_object_context"]
            else:
                primary, confidence, evidence = "organization", 0.93, ["ner:ORG"]
        elif entity == "WORK_OF_ART":
            primary, confidence, evidence = "title", 0.9, ["ner:WORK_OF_ART"]
        elif entity == "LANGUAGE":
            primary, confidence, evidence = "language", 0.96, ["ner:LANGUAGE"]
        elif entity == "NORP":
            primary = "nationality" if pos in {"NOUN", "PROPN"} or analysis.get("governor_lemma", "").casefold() in _NATIONAL_GROUP_HEADS else "adjective"
            confidence, evidence = 0.88, ["ner:NORP", f"pos:{pos}", f"dependency:{dependency}"]
        elif entity in {"DATE", "TIME"}:
            primary, confidence, evidence = "vocabulary", 0.85, [f"ner:{entity}", "temporal_expression"]
        elif pos == "NUM" or entity in {"CARDINAL", "ORDINAL", "QUANTITY", "PERCENT"}:
            primary, confidence, evidence = "number", 0.94, [f"pos:{pos}", f"ner:{entity}"]
        elif pos in {"NUM", "PROPN", "NOUN", ""} and _ROMAN.fullmatch(surface.upper()) and surface.isupper():
            primary, confidence, evidence = "roman_numeral", 0.72, ["roman_numeral_grammar", "uppercase"]
        elif pos not in {"PRON", "DET"} and surface in _ELEMENT_SYMBOLS and analysis.get("nearby_nouns") and set(analysis["nearby_nouns"]) & {"element", "atom", "ion", "metal", "gas", "molecule"}:
            primary, confidence, evidence = "chemical_symbol", 0.8, ["element_symbol_resource", "chemical_context"]
        elif pos in {"VERB", "AUX"}:
            primary, confidence, evidence = "verb", 0.9, [f"pos:{pos}"]
        elif pos == "ADJ":
            primary, confidence, evidence = "adjective", 0.9, ["pos:ADJ"]
        elif story_glossary is not None and story_glossary.status == "ok" and not story_glossary.data.get("ambiguous"):
            category = str(story_glossary.data.get("category") or "").casefold()
            mapping = {"person": "named_person", "character": "named_person", "location": "named_place", "place": "named_place", "organization": "organization", "object": "object"}
            primary, confidence, evidence = mapping.get(category, "object"), 0.9, ["spoiler_safe_story_match"]
        elif pos in {"NOUN", "PROPN", "ADV", "INTJ"}:
            primary, confidence, evidence = "vocabulary", 0.72, [f"pos:{pos}"]
        else:
            primary, confidence, evidence = "unknown", 0.3, ["insufficient_linguistic_evidence"]
        return {"primary_class": primary, "confidence": confidence, "evidence": evidence, "ambiguous": False}

    @staticmethod
    def grammatical_explanation(primary_class: str, analysis: dict) -> str:
        number = {"Sing": "singular", "Plur": "plural"}.get(str(analysis.get("number") or ""), "")
        person = {"1": "first-person", "2": "second-person", "3": "third-person"}.get(str(analysis.get("person") or ""), "")
        pronoun_details = " ".join(value for value in (person, number, "pronoun") if value)
        details = {
            "pronoun": f"A {pronoun_details} used in this sentence.",
            "determiner": "A determiner that specifies or limits the nearby noun.",
            "article": "An article used to introduce or identify a noun.",
            "preposition": "A preposition expressing a relationship to another part of the sentence.",
        }
        return details.get(primary_class, "A grammatical function word in this sentence.")
