# Image Parser Completion Checklist Before Touching Anything Else

The core image pipeline is already laid out as a clean evidence boundary: `ImageDescriptor` is the adapter contract and intentionally keeps raw bytes out of JSON serialization, the pipeline has hashing/cache, preprocessing, OCR, classification, routing, fallback, evidence building, and a replay adapter, and the plugin contract is conservative by design.        

What is left now is not “more image features.” It is finishing the pipeline so it actually becomes part of BookBuddy’s normal chapter lifecycle, replay, snapshotting, export, and diagnostics.

---

## 1. Finish the chapter-side image ingestion contract

* [ ] Extend `RawChapter` to carry ordered image descriptors, not just text.
* [ ] Make EPUB extraction keep image occurrence order, source locator, document item ID, caption, alt text, image hash, perceptual hash, and image metadata.
* [ ] Ensure chapter analysis sees images in the same chapter-scoped pipeline as text, not as a separate side channel.
* [ ] Keep EPUB as the source adapter boundary for now. Do not add PDF/scan ingestion yet.

The EPUB extractor already resolves image occurrences, captions, alt text, metadata, and hashes, and produces `ImageDescriptor` objects. That boundary should be the only EPUB-specific piece.  

---

## 2. Finish the storage and schema side

* [ ] Add the SQLite tables needed for:

  * [ ] exact-image cache
  * [ ] image evidence revisions
  * [ ] image occurrence provenance
* [ ] Add migrations/version bumps for image evidence schema changes.
* [ ] Store source-independent parse artifacts in cache, but keep chapter-specific occurrence provenance separate.
* [ ] Make sure repeated identical images reuse cached parse artifacts, while each chapter occurrence still gets its own evidence record.
* [ ] Keep perceptual hashes as near-duplicate hints only. They must not become cache identity.

This matches the current cache design: exact cache keys are `image_hash + parser_fingerprint`, and perceptual hashing is only a near-duplicate hint, not a reuse key.  

---

## 3. Finish the parser pipeline boundaries

* [ ] Keep the classifier as a routing stage, not a truth stage.
* [ ] Keep the router as the only place that chooses plugins.
* [ ] Keep plugins isolated and conservative.
* [ ] Keep OCR and preprocessing optional, local-first, and failure-tolerant.
* [ ] Make classification run before heavy OCR/semantic work.
* [ ] Keep fallback strictly opt-in and threshold-gated.

The classifier already routes on EPUB context and cheap visual signals, and it produces category + subcategory + confidence + reason.  

The router already dispatches categories to isolated plugins, including conservative unknown handling. 

The plugins are deliberately non-authoritative. They return observations only.  

The preprocessing and OCR layers already degrade gracefully when optional packages are missing.  

The fallback path is explicitly conditional, disabled by default, and only allowed below threshold with authorization.  

---

## 4. Finish the evidence contract

* [ ] Make `image_evidence` a stable chapter payload section.
* [ ] Include:

  * [ ] schema version
  * [ ] descriptor
  * [ ] category and subcategory
  * [ ] OCR text
  * [ ] layout blocks
  * [ ] typed observations
  * [ ] confidence breakdown
  * [ ] diagnostics
  * [ ] provenance
  * [ ] failure state
* [ ] Preserve uncertain outputs instead of dropping them.
* [ ] Never promote image claims directly into canonical entities, relationships, life status, or landmarks.
* [ ] Keep portrait evidence as appearance-only, never identity proof.

The current evidence builder already points in this direction and includes schema version, descriptor, OCR, layout, observations, confidence breakdown, provenance, and cache status. 

---

## 5. Finish the replay adapter integration

* [ ] Hook image evidence into the same replay path as text evidence.
* [ ] Let the adapter translate image observations into:

  * [ ] reviewable mention evidence
  * [ ] language observations
  * [ ] optional reference-safe location hints
* [ ] Do **not** let the image parser call graph mutation APIs.
* [ ] Do **not** let replay rerun image parsing.
* [ ] Replay must consume stored evidence only.
* [ ] Keep canonical graph mutations restricted to existing resolver/replay paths.

The replay adapter already behaves this way: it records mentions, links only already-resolved locations, stores language observations, and explicitly says canonical mutations are zero. 

---

## 6. Finish diagnostics and failure handling

* [ ] Preserve structured diagnostics for every stage:

  * [ ] extraction
  * [ ] hashing
  * [ ] preprocessing
  * [ ] OCR
  * [ ] classification
  * [ ] routing
  * [ ] fallback
  * [ ] evidence building
* [ ] Ensure corrupt images, missing dependencies, OCR failures, cache failures, and fallback failures produce degraded evidence, not chapter abortion.
* [ ] Make “decorative image ignored” a first-class outcome.
* [ ] Make unknown/unsupported images safe, not silent.

The diagnostics helpers already exist for this purpose, and the fallback code already returns structured degraded states instead of breaking the chapter.  

---

## 7. Finish dependency handling

* [ ] Make the dependency check run before FastAPI or image packages are imported.
* [ ] Keep it standard-library only.
* [ ] Keep the “install dependencies” path explicit and user-approved.
* [ ] Keep requirements for the image pipeline separate and documented.
* [ ] Make startup fail cleanly with a clear message if required packages are missing.

You already have a startup dependency manager that checks requirements without importing the app stack first, and it can prompt or print manual install instructions. 

Your requirements file already separates core app packages from the free-first local image pipeline packages. 

---

## 8. Finish cache behavior

* [ ] Cache source-independent parse artifacts by exact hash + parser fingerprint.
* [ ] Never cache-reuse on perceptual hash alone.
* [ ] Make parser fingerprint sensitive to:

  * [ ] parser version
  * [ ] schema version
  * [ ] confidence threshold
  * [ ] fallback model settings
  * [ ] router mapping
  * [ ] installed OCR/OpenCV/Pillow/ImageHash versions
* [ ] Add cache-write and cache-read failure diagnostics.
* [ ] Preserve source-independent artifacts, but keep chapter occurrence provenance separate.

The parser fingerprint already includes schema, parser, thresholds, fallback settings, router mapping, and dependency versions. 

The cache key is already exact-image-hash plus parser fingerprint. 

---

## 9. Finish the category and plugin coverage

* [ ] Keep the category list explicit.
* [ ] Keep unsupported categories routed to conservative unknown handling.
* [ ] Keep each plugin focused on one image kind.
* [ ] Keep all outputs typed as candidate observations only.
* [ ] Ensure decorative images stay ignored unless they contain actual text/symbol evidence.
* [ ] Ensure portrait output never resolves identity.
* [ ] Ensure maps only emit location candidates, family trees only emit relationship candidates, glyphs only emit language candidates, and so on.

The current categories and router mapping already reflect this structure.  

---

## 10. Finish testing before touching any other feature

* [ ] EPUB image extraction smoke test
* [ ] No-image chapter regression
* [ ] Duplicate image reuse test
* [ ] Perceptual-hash near-duplicate safety test
* [ ] Missing Pillow/OpenCV/PaddleOCR test
* [ ] OCR success and OCR failure test
* [ ] Classification and router mapping test
* [ ] Decorative-image ignored test
* [ ] Gemini fallback disabled-by-default test
* [ ] Gemini fallback opt-in and threshold-gated test
* [ ] Replay determinism test
* [ ] Snapshot spoiler-safety test
* [ ] Existing retention/pre-retention contract tests
* [ ] Graph sanity test after image evidence is added

The existing codebase already has the pieces needed to support these tests, including the conservative plugin contract, fallback gating, exact-hash cache, and replay adapter.    

---

## 11. Stop condition for the image parser

Do **not** move to dictionary, translator, cipher learning, or any new user-facing feature until all of this is true:

* [ ] image evidence is persisted
* [ ] replay consumes it deterministically
* [ ] snapshots stay spoiler-safe
* [ ] cache reuse works
* [ ] fallback is opt-in
* [ ] dependency failures degrade cleanly
* [ ] no parser plugin mutates graph state
* [ ] no image path bypasses replay
* [ ] tests pass on real EPUBs

---

## Final priority order

1. Finish chapter image ingestion
2. Finish image evidence persistence
3. Finish cache and fingerprinting
4. Finish replay integration
5. Finish snapshot/export wiring
6. Finish diagnostics and failure handling
7. Finish tests
