# Dictionary Subsystem

The reader dictionary is an optional backend capability. Core BookBuddy startup
does not require spaCy, Open English WordNet, or CMU pronunciation data.

Check or install its Python packages with:

```powershell
.\venv\Scripts\python.exe backend\dependency_manager.py --dictionary --check
.\venv\Scripts\python.exe backend\dependency_manager.py --dictionary --install
```

Install an English spaCy pipeline and the configured Open English WordNet data
separately. When either is absent, the affected response section reports
`unavailable`; glossary and reader-state services continue to work.

## Endpoints

- `POST /reader/{book}/{session}/highlight`
- `GET /dictionary/pronunciation/audio/{audio_id}`
- `POST /reader/profile`
- `POST /reader/{book}/{session}/knowledge/{kind}/{id}/view`
- `POST /reader/{book}/{session}/knowledge/{kind}/{id}/mark-known`
- `POST /reader/{book}/{session}/knowledge/{kind}/{id}/ignore`

Highlight lookup is read-only. Terminology candidates are discovered during
chapter ingestion and replay, require deterministic text support from multiple
chapters, and remain hidden before their confirmation chapter. Image-only or
AI-originated observations cannot become canonical terminology facts.

## Contextual selection resolution

Highlight responses include an additive `resolution` object with schema
`csre_v1`. The resolver preserves the original selection, performs linguistic
analysis and spoiler-safe story lookup before downstream explanation, assigns a
primary semantic class, ranks candidates, and returns the display order
`contextual`, `story`, `general`, `pronunciation`.

Clients may provide `sentence_text`, adjacent sentences, `paragraph_text`, and
sentence-relative selection offsets. Legacy `context_text` requests remain
supported. Pronouns, articles, determiners, and prepositions return
local grammar explanations by default without invoking dictionary,
pronunciation, or AI providers. Set `explain_function_words=false` to suppress
their popups instead.

Story candidates are filtered at `knowledge_as_of_chapter`. Highlight lookup
does not mutate graph facts, snapshots, terminology, or reader state. Optional
spaCy/WordNet failures produce structured degraded sections rather than failing
the reader route.

Reader history is stored in `library/reader_state/reader.db`, outside every
session graph. Generated glossary definitions are transient and are never
stored.
