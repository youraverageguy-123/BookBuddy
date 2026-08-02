# BookBuddy Image Parser: Free-First, API-Fallback Plan

## Goal

Build the image parser as an **evidence extractor**, not a dumb OCR toy pretending to be smart.

The parser should turn images into structured evidence that flows through the same BookBuddy pipeline already used for text:
- evidence
- replay
- resolvers
- graph
- snapshots

The image parser should **not** own truth.
It should only produce evidence.

---

## Core strategy

Use this stack in order:

1. **OpenCV** for image preprocessing and basic visual structure
2. **PaddleOCR** for OCR, layout, tables, and reading order
3. **Pillow** for image handling and cropping
4. **ImageHash** for deduplication
5. **Gemini Vision API only as fallback** when local parsing is uncertain or the image is weird enough to deserve a human-like second opinion

Do **not** start with a local vision LLM.
That is how projects become a 10 GB solution to the question “is this a map?”

---

## Recommended pipeline

```text
Book image
    ↓
Extract image
    ↓
Hash image
    ↓
Already seen?
    ↓
Yes → reuse prior evidence
No  → continue
    ↓
Preprocess with OpenCV
    ↓
OCR + layout with PaddleOCR
    ↓
Enough confidence?
    ↓
Yes → build evidence bundle
No  → Gemini Vision fallback
    ↓
Evidence bundle
    ↓
Replay
    ↓
Resolvers
    ↓
Graph + snapshots
````

---

## What each tool is for

### 1. OpenCV

Use it for:

* denoising
* thresholding
* edge detection
* contour detection
* crop detection
* line detection
* map segmentation
* page segmentation
* panel detection
* image cleanup before OCR

This is the boring, useful part. The part that does not win social media points, which is how you know it might actually work.

---

### 2. PaddleOCR

Use it for:

* text extraction
* reading order
* structured layout
* tables
* mixed text/image pages
* chapter scans
* captions
* notes
* pages with weird formatting

This should be the default OCR backbone.

---

### 3. Pillow

Use it for:

* image loading
* cropping
* resizing
* format conversion
* saving crops for sub-parsers

---

### 4. ImageHash

Use it for:

* detecting repeated images
* skipping duplicate OCR
* avoiding repeated processing of the same map, sigil, or portrait

If the same image appears again, do not waste time pretending it is a fresh mystery.

---

### 5. Gemini Vision API fallback

Use it only when:

* OCR confidence is low
* layout detection is unclear
* image type is ambiguous
* semantic interpretation is needed
* the image is not mainly text
* the local parser cannot decide what the image is

Examples:

* map vs diagram vs symbol page
* portrait vs illustration vs heraldry
* family tree with unusual styling
* page scan where text is too messy
* symbolic art that needs interpretation

Gemini should be the **fallback**, not the default.

---

## Image kinds to support

Classify every image before parsing it.

Supported kinds:

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

---

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

---

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
That is how the graph starts making confident nonsense.

Output:

* descriptive evidence
* possible entity association
* visual clue evidence

---

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

---

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

---

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

---

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

---

### Table

Extract:

* rows
* columns
* comparisons
* entity lists
* quantities

Output:

* structured evidence, not just a text dump wearing a fake moustache

---

### Handwritten note

Extract:

* OCR
* note text
* marginalia
* corrections
* addenda

Output:

* paratext evidence

---

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

## What the image parser should never do

Do **not**:

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

## Recommended module structure

A clean split would look like this:

```text
image_parser.py
image_router.py
image_evidence_builder.py
image_preprocessor.py
image_hashing.py
image_specialized_parsers/
    map_parser.py
    portrait_parser.py
    family_tree_parser.py
    glyph_parser.py
    symbol_parser.py
    diagram_parser.py
    timeline_parser.py
    table_parser.py
    note_parser.py
```

If you want it lighter:

```text
image_parser.py
image_router.py
image_evidence_builder.py
```

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

### Phase 5: Evidence

* save structured evidence
* attach provenance
* attach confidence
* attach chapter/page metadata

### Phase 6: Replay

* replay the same resolver pipeline already used for text

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
* optionally escalate to Gemini Vision

If the image is decorative and useless:

* hash it
* ignore it
* move on with your life

---

## The free-first recommendation

Use this by default:

* **OpenCV**
* **PaddleOCR**
* **Pillow**
* **ImageHash**

Use **Gemini Vision API** only when the local pipeline cannot confidently classify or parse the image.

That keeps cost down, keeps the architecture simple, and avoids turning the project into a local GPU furnace just to answer “is this a map or a weird drawing?”

---

## Why this works well with BookBuddy

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

> “What evidence is in this image?”

Not:

> “What truth should I force into the graph right now?”

That distinction is the difference between a useful parser and another AI feature that looks impressive until it starts hallucinating a family tree into a wallpaper.

```
```
