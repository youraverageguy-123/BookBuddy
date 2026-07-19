


# BookBuddy Image Parser Plan

## Build an evidence extractor, not a dumb OCR toy

## Goal

Turn images into **structured evidence** that flows through the same BookBuddy pipeline already used for text:

* evidence
* replay
* resolvers
* graph
* snapshots

The image parser should **not** own truth.
It should only produce evidence.

---

## Recommended stack

### Free-first local stack

* **OpenCV** for preprocessing and visual structure
* **PaddleOCR** for OCR, layout, tables, and reading order
* **Pillow** for image handling and cropping
* **ImageHash** for deduplication

### Fallbacks

* **Gemini Vision** only when local parsing is uncertain or the image is weird enough to need semantic interpretation
* **Qwen2-VL / Qwen2.5 family** if you want an open multimodal fallback for image understanding
* **Google Document AI** or **Azure Document Intelligence** if you want a managed cloud parser

---

## Core principle

Do **not** think:

* image -> OCR -> text -> done

Think:

* image -> classify -> parse -> extract evidence -> replay

Or better:

* image -> image kind -> specialized parser -> evidence bundle -> resolvers -> graph -> snapshots

The image parser is a **producer** of evidence.
The resolvers are the **interpreters** of evidence.
The snapshots are the **reader-safe projection**.

---

## What the image parser should handle

* maps
* family trees
* portraits
* heraldry / sigils
* chapter ornaments
* handwritten notes
* diagrams
* tables embedded in images
* symbols
* fictional alphabets
* page illustrations
* battle maps
* charts
* timelines
* captions
* footnotes in image form
* scanned pages from bad EPUBs / PDFs

---

## What it should never do

* directly merge entities
* directly set final life status
* directly decide canonical identity
* directly decide canonical landmark identity
* directly infer spoilers
* directly treat portraits as identity proof
* hardcode book-specific image behavior
* create separate special-case logic per book

The parser should only emit evidence.

Resolvers decide what survives.

---

## Pipeline

1. Extract embedded images from EPUB / PDF / scanned pages
2. Hash each image
3. Deduplicate identical images
4. Classify the image kind
5. Route to a specialized parser
6. Run OCR + layout + semantic interpretation
7. Build an evidence bundle
8. Write an evidence revision
9. Replay downstream resolvers
10. Rebuild reader snapshots if needed

---

## Image kinds to support

* `map`
* `portrait`
* `family_tree`
* `heraldry`
* `symbol`
* `glyph`
* `fictional_alphabet`
* `diagram`
* `timeline`
* `table`
* `chart`
* `handwritten_note`
* `captioned_illustration`
* `page_scan`
* `chapter_ornament`
* `battle_map`
* `character_sheet`
* `unknown`

---

## What each kind should produce

### Map

Extract:

* locations
* roads
* rivers
* borders
* regions
* landmarks
* route hints
* faction territory
* travel paths

Output:

* location evidence
* landmark evidence
* relationship evidence between places
* route evidence

### Family tree

Extract:

* parent-child links
* spouse links
* siblings
* succession hints
* house links
* lineage

Output:

* family relationship evidence
* legacy evidence
* political inheritance hints

### Portrait

Extract:

* caption text
* armor
* clothing
* weapon
* symbols
* pose
* visible object associations

Do **not** do face recognition as identity truth.

Output:

* descriptive evidence
* possible entity association
* visual clue evidence

### Heraldry

Extract:

* house
* faction
* sigil
* symbol
* banner
* lineage hint

Output:

* group evidence
* faction evidence
* symbol evidence

### Symbol / glyph / fictional alphabet

Extract:

* repeated shapes
* recurring symbols
* caption text
* nearby translation hints
* chapter context

Output:

* language observations
* cipher observations
* symbol evidence

### Diagram / chart

Extract:

* labels
* arrows
* hierarchy
* flow
* relationships
* process structure

Output:

* concept evidence
* relation evidence
* event or system evidence

### Timeline

Extract:

* sequence
* dates
* phases
* named landmarks
* historical ordering

Output:

* landmark evidence
* chronology evidence

### Table

Extract:

* rows
* columns
* comparisons
* entity lists
* quantities

Output:

* structured evidence, not just a text dump

### Handwritten note

Extract:

* OCR
* note text
* marginalia
* corrections
* addenda

Output:

* paratext evidence

### Chapter ornament / decoration

Usually low value.
If it contains a symbol, treat it as symbol evidence.
Otherwise ignore it after hashing.

---

## Evidence model

The image parser should emit structured evidence like this:

```python
class ImageEvidenceDict(BaseModel):
    image_hash: str
    image_kind: str
    image_subkind: str = "unknown"
    chapter_index: int
    page_index: int | None = None
    source_type: str = "epub_image"
    ocr_text: str = ""
    caption_text: str = ""
    layout_blocks: list[dict] = []
    detected_entities: list[dict] = []
    detected_locations: list[dict] = []
    detected_relationships: list[dict] = []
    detected_symbols: list[dict] = []
    detected_language: str = "unknown"
    translation_candidates: list[dict] = []
    confidence: float = 0.5
    parser_version: str = "image_parser_v1"
    source_model: str = ""
    source_model_version: str = ""
    source_reason: str = ""
```

This is **evidence**, not final truth.

---

## Suggested module structure

* `image_parser.py`
* `image_router.py`
* `image_evidence_builder.py`
* `image_preprocessor.py`
* `image_hashing.py`
* `image_specialized_parsers/`

  * `map_parser.py`
  * `portrait_parser.py`
  * `family_tree_parser.py`
  * `glyph_parser.py`
  * `symbol_parser.py`
  * `diagram_parser.py`
  * `timeline_parser.py`
  * `table_parser.py`
  * `note_parser.py`

If you want it lighter:

* `image_parser.py`
* `image_router.py`
* `image_evidence_builder.py`

---

## Best implementation order

### Phase 1: Extraction

* extract all embedded images
* hash them
* deduplicate them
* store metadata

### Phase 2: Classification

* identify image kind
* identify subkind
* route to the right parser

### Phase 3: Parsing

* run OpenCV preprocessing
* run PaddleOCR
* extract layout
* extract text
* extract structure

### Phase 4: Fallback

* if confidence is too low, send the image or crop to Gemini Vision
* if you want a local open model fallback, use Qwen2-VL / Qwen2.5-family multimodal models
* if you want a hosted fallback, use Google Document AI or Azure Document Intelligence

### Phase 5: Evidence

* save structured evidence
* attach provenance
* attach confidence
* attach chapter/page metadata

### Phase 6: Replay

* let resolvers incorporate the evidence
* rebuild snapshots if needed

### Phase 7: Evaluation

* compare parsed output with expected landmarks, relations, and glossary terms

---

## Confidence rules

If confidence is high:

* emit evidence
* replay downstream

If confidence is low:

* preserve evidence as uncertain
* do not force a merge
* optionally escalate to a fallback model

If the image is decorative and useless:

* hash it
* ignore it
* move on

---

## Tool choices in practice

### Use this by default

* OpenCV
* PaddleOCR
* Pillow
* ImageHash

### Use this only when needed

* Gemini Vision API fallback
* Qwen2-VL / Qwen2.5-family fallback
* Google Document AI
* Azure Document Intelligence

---

## Why this fits BookBuddy

The image parser plugs into the existing system without changing it.

It produces evidence.
The engine replays.
Resolvers interpret.
Snapshots hide spoilers.

So the image parser becomes just another source of evidence, alongside:

* chapter text
* life evidence
* landmark evidence
* relationship evidence
* language observations

That is the right abstraction.

---

## Final principle

The image parser should answer:

> What evidence is in this image?

Not:

> What truth should I force into the graph right now?

That distinction is the difference between a useful parser and another AI feature that looks impressive until it starts hallucinating a family tree into a wallpaper.


