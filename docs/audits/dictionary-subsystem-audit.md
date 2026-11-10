# Dictionary Subsystem Audit

## Overall Architecture

Treat these as **four completely independent services**.

```text
Highlight

        │

        ▼

Dictionary Controller

        │
        ├────────────► General Dictionary
        │
        ├────────────► Context Dictionary
        │
        ├────────────► Story Glossary
        │
        └────────────► Pronunciation
```

Never merge them.

Each solves a different problem.

---

# Module 1

# General Dictionary

Purpose:

Give the meaning of ordinary English words.

Example

```
ephemeral

noun/adjective

IPA

Definition

Examples

Synonyms

Antonyms

Etymology

Pronunciation
```

No AI.

Ever.

---

## Library

### spaCy

Purpose

* tokenizer
* POS tagging
* lemmatization

Why?

Because user may select

```
running
```

Dictionary lookup should actually search

```
run
```

not

```
running
```

---

### Open English WordNet

Purpose

Actual dictionary database.

Contains

* definitions
* synonyms
* antonyms
* semantic hierarchy
* multiple meanings

Never hardcode meanings.

Always query.

---

### spacy-wordnet

Purpose

Connects spaCy tokens directly to WordNet.

Flow

```
running

↓

spaCy

↓

lemma

↓

run

↓

WordNet

↓

definitions
```

---

# Storage

Never cache permanently.

Only memory cache.

```
lemma

↓

lookup

↓

LRU cache

↓

dictionary
```

Because dictionary data almost never changes.

---

# Module 2

# Pronunciation

Treat pronunciation as three completely separate datasets.

---

## 1 IPA

Store

```
run

↓

/rʌn/
```

Dictionary lookup.

---

## 2 Human phonetic

Display

```
run

RUN
```

or

```
ephemeral

uh-FEM-er-ul
```

This is for humans.

---

## 3 Audio

Never synthesize.

Never use Gemini.

Never use TTS.

Instead

```
word

↓

pronunciation dataset

↓

audio file
```

If unavailable

fallback

```
grapheme-to-phoneme

↓

small TTS
```

Only then.

---

Never

```
Gemini

↓

Read this word
```

Waste of money.

---

# Module 3

Context Dictionary

Purpose

Explain what highlighted word means **inside this sentence.**

---

Example

```
cold smile
```

Dictionary

```
low temperature
```

Wrong.

Context

```
emotionally distant
```

Correct.

---

Pipeline

```
Highlighted word

↓

Sentence extraction

↓

spaCy parser

↓

POS

↓

Dependency parser

↓

Word Sense Disambiguation

↓

Meaning
```

---

Tool

spaCy

Need

```
dependency parse

head

children

POS

lemma
```

---

Word Sense Disambiguation

Use

WordNet senses

Choose highest scoring sense.

---

AI

ONLY IF

```
confidence

< threshold
```

Then

Gemini

Prompt

```
Explain ONLY this word
inside this sentence.

Do not explain entire sentence.

Return one concise meaning.
```

Never

```
Explain chapter
```

Waste.

---

# Module 4

Story Glossary

This is NOT a dictionary.

It is a graph view.

---

Never store

```
definition TEXT
```

Store

```
Entity

Attributes

Evidence

Relationships

Confidence
```

Definition should always be generated from graph.

---

Example

gravBoots

Store

```
Category

Technology

Subtype

Wearable

Functions

Jumping

Magnetic propulsion

Landing assist

Users

Darrow

Victra

Obsidians

First seen

Chapter

Confidence

0.94
```

Definition

generated

```
Wearable magnetic propulsion boots
used for enhanced mobility and controlled
jumps.
```

---

Never save that sentence.

Save facts.

---

# Story Glossary Database

Every glossary item

```
id

display_name

aliases

entity_type

subtype

status

importance

confidence

first_seen

last_seen
```

---

Attributes table

```
attribute

value

confidence

source evidence
```

---

Functions table

```
entity

function

confidence

chapter
```

---

Evidence table

Already exists.

Reuse.

---

# Related Concepts

Automatically generated.

No AI.

Simply graph traversal.

```
gravBoots

↓

Technology

↓

same chapter

↓

same users

↓

same relationships
```

Return

```
PulseArmor

Starshell

Razor
```

---

# Timeline

Every entity

```
introduced

modified

destroyed

renamed

revealed

first used

last mentioned
```

All deterministic.

---

# Confidence

Store

```
definition confidence

attribute confidence

relationship confidence
```

Never only entity confidence.

---

# Explainability

This is huge.

Every inferred definition

should answer

```
Why?
```

Example

gravBoots

```
Technology

because

activated

equipped

worn

powered

magnetic

jumped
```

These should link directly to evidence.

---

# Images

Since image parser already exists

Every glossary entry

should optionally have

```
portrait

map

symbol

crest

diagram

weapon image
```

Retrieved

from image evidence.

No AI.

---

# Reader Highlight Flow

User

```
highlights

gravBoots
```

Pipeline

```
Highlight

↓

Is this graph entity?

↓

YES

↓

Glossary
```

Else

```
English dictionary
```

Never confuse.

---

# Smart Detection

Suppose

```
Republic
```

Could be

English

or

story entity.

Use graph first.

```
exists as entity?

YES

↓

Glossary

NO

↓

Dictionary
```

---

# Context Panel

Display

```
Meaning in this sentence

↓

General definition

↓

Story definition

↓

Pronunciation

↓

Examples

↓

Related concepts
```

All separate cards.

---

# Caching

Never cache UI.

Cache

```
dictionary lookups

IPA

WordNet

pronunciation

WSD result
```

Glossary comes from graph.

---

# Search

Support

```
grav

↓

gravBoots
```

Alias search.

Not exact search.

Reuse alias resolver.

---

# Multilingual Future

Do NOT hardcode English.

Create interface

```
DictionaryProvider

lookup()

pronounce()

examples()

ipa()
```

Current implementation

```
EnglishProvider
```

Future

```
FrenchProvider

GermanProvider

JapaneseProvider
```

No rewrite needed.

---

# Pronunciation Interface

Never hardcode audio source.

```
PronunciationProvider

↓

IPA

↓

Audio

↓

Human phonetics
```

Future

Swap provider.

Nothing changes.

---

# Context Interface

```
ContextResolver

↓

spaCy

↓

WordNet

↓

AI fallback
```

Later

swap

```
spaCy

↓

Stanza

↓

transformers
```

No rewrite.

---

# Glossary Interface

```
GlossaryResolver

↓

Graph

↓

Evidence

↓

Inference

↓

Renderer
```

Renderer

ONLY renders.

Never infers.

---

# Example UI (Do not make or work on UI right now, this is an example of how it show up in final UI)

Dictionary popup

```
──────────────────────

gravBoots

Technology

★★★★☆

First Seen

Chapter 8

──────────────────────

Definition

──────────────────────

Meaning in this sentence

──────────────────────

Pronunciation

──────────────────────

Evidence

──────────────────────

Timeline

──────────────────────

Related Concepts

──────────────────────

Images

──────────────────────

Explain Why
```

---

# Things to NEVER Hardcode

This is probably the most important section.

Never hardcode:

* Dictionary provider (use `DictionaryProvider` interface)
* Pronunciation provider (use `PronunciationProvider`)
* Word Sense Disambiguation engine (use `ContextResolver`)
* Graph renderer (render from graph data only)
* Glossary definition templates (use a configurable renderer with templates, not scattered string concatenation)
* Audio provider
* IPA source
* Etymology source
* Example sentence source
* Search engine (exact, fuzzy, semantic)
* Ranking algorithm for multiple senses
* Confidence thresholds (keep them configurable)
* AI fallback model or prompt (centralize in configuration)
* Entity category lists (load from configuration or registry, not switch statements)
* UI card order (drive from a layout configuration if practical)
* Any book related examples

---

# My biggest recommendation

Treat the Dictionary subsystem exactly the way you treated the Image Pipeline.

You didn't make the image parser "an EPUB image parser." You built an **evidence extraction pipeline** with adapters, routing, immutable evidence, replay, and resolvers.

Do the same here:

```text
Reader Highlight
        │
        ▼
Highlight Resolver
        │
        ├────────► Dictionary Provider
        │
        ├────────► Pronunciation Provider
        │
        ├────────► Context Resolver
        │
        ├────────► Glossary Resolver
        │
        └────────► Response Composer
                         │
                         ▼
                  Dictionary Popup
```

Every box should expose a clean interface with swappable implementations. The UI should know nothing about WordNet, spaCy, Gemini, or your graph internals. It simply asks for a `DictionaryResponse` and renders it. That separation is what will let you improve or replace individual pieces years later without turning the subsystem into the sort of tangled archaeological site that gives software engineers recurring nightmares.
