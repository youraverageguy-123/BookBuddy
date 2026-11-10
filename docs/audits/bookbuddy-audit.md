# BookBuddy Audit

# Contextual Selection Resolution Engine (CSRE)

## Purpose

The Contextual Selection Resolution Engine (CSRE) determines what the user's selected text represents **before** any dictionary, glossary, knowledge-base, or LLM explanation is attempted.

The engine is responsible for semantic routing, not explanation generation.

It exists to answer one question:

> **"What does the user mean by selecting this text at this exact location in this story?"**

instead of

> "What is the most popular thing with this spelling?"

---

# Core Design Principles

## 1. Context First

The surrounding sentence and story context always take precedence over general language resources.

Priority order:

```
Story Context

↓

Story Entity

↓

Contextual Meaning

↓

General Dictionary

↓

General Knowledge

↓

Fallback
```

The backend must never query a general dictionary or knowledge base before attempting contextual resolution.

---

## 2. Never Hardcode

Never implement rules like:

```python
if word == "French":
```

or

```python
if word == "Myrtle":
```

The system must generalize to unseen books.

Examples shown in this document are validation cases, **not implementation rules**.

---

## 3. Explanation is downstream

Classification occurs before explanation.

Wrong:

```
Selection

↓

Dictionary

↓

LLM
```

Correct:

```
Selection

↓

Classification

↓

Routing

↓

Explanation
```

---

# Pipeline

```
Raw Selection

↓

Normalization

↓

Lexical Analysis

↓

Morphological Analysis

↓

Named Entity Detection

↓

Context Window Extraction

↓

Semantic Classification

↓

Disambiguation

↓

Route

↓

Response Assembly
```

---

# Stage 1

## Raw Selection

Input:

```
selected_text

chapter

paragraph

sentence

surrounding context

selection offsets

book

session
```

The raw selection must preserve:

* exact casing
* punctuation
* whitespace
* Unicode

Never lowercase immediately.

---

# Stage 2

## Normalization

Produce multiple forms.

Example

```
US
```

Produces

```
original

US

lower

us

lemma

US

normalized

US
```

The original token is always preserved.

---

# Case Sensitivity

Case is semantic.

These are not equivalent.

```
US
```

Country.

```
us
```

Pronoun.

Likewise

```
May
```

Month.

```
may
```

Modal verb.

```
Turkey
```

Country.

```
turkey
```

Bird.

```
Bill
```

Person.

```
bill
```

Invoice.

Never destroy case information before classification.

---

# Stage 3

## Morphological Analysis

Determine

* lemma
* tense
* plurality
* possessive
* derivation

Example

```
running

↓

run
```

```
reappeared

↓

reappear
```

Dictionary lookup uses lemma.

Display preserves original.

---

# Stage 4

## Lexical Classification

Every selection must receive one primary class.

Possible classes

```
Named Person

Named Place

Organization

Object

Title

Vocabulary

Pronoun

Determiner

Article

Preposition

Verb

Adjective

Nationality

Language

Number

Roman Numeral

Chemical Symbol

Unknown
```

This stage never explains.

It only classifies.

---

# Stage 5

## Context Window

Use

Current sentence.

Previous sentence.

Next sentence.

Current paragraph.

Current chapter index.

Current story state.

Not the whole novel.

---

# Stage 6

## Story Entity Resolution

Before dictionaries.

Search canonical graph.

Aliases.

Snapshots.

Relationships.

Spoiler-safe state.

If matched

```
selection_type

named_entity
```

Return entity immediately.

---

Example

```
Myrtle
```

Current chapter:

```
Character

↓

Myrtle Wilson
```

NOT

Plant.

---

# Stage 7

## Semantic Disambiguation

Only if multiple meanings exist.

Use:

POS

Dependency

Nearby nouns

Nearby verbs

Nearby adjectives

Book context

---

Example

Sentence

```
He spoke French.
```

Meaning

```
Language
```

---

Sentence

```
The French army advanced.
```

Meaning

```
Nationality
```

---

Sentence

```
Daniel Chester French sculpted...
```

Meaning

```
Person
```

---

Sentence

```
French doors
```

Meaning

```
Adjective
```

---

Never choose based on popularity.

---

# Stage 8

## Routing

Decision table

### Named Entity

Return

Story Context

↓

Contextual Description

↓

General Meaning (if applicable)

---

### Vocabulary

Return

Contextual Meaning

↓

Dictionary

↓

Pronunciation

---

### Pronoun

Usually suppress popup.

Or return

```
First-person singular pronoun referring to the narrator.
```

---

### Stopwords

Default

No popup.

Configurable.

---

### Unknown

Return

Contextual explanation only.

Do not hallucinate.

---

# Response Order

Always

```
Contextual

↓

Story

↓

General

↓

Pronunciation
```

Never

```
Dictionary

↓

Context
```

The reader cares about the story first.

---

# UI Specification

For

```
Myrtle
```

Display

```
Character

Myrtle Wilson

Context

Married to George Wilson.

Currently introduced as Tom Buchanan's mistress.

Known so far:
...

Dictionary

myrtle

Evergreen shrub...
```

---

For

```
French
```

```
Context

Refers to France or French nationality in this sentence.

Dictionary

Relating to France.
```

Never

```
American sculptor.
```

---

For

```
reappeared
```

```
Context

Appeared again after previously leaving.

Dictionary

reappear

To appear again.
```

---

For

```
US
```

```
Context

United States

Dictionary

Country.
```

Never

```
us

Pronoun.
```

---

For

```
I
```

Prefer

No popup.

If enabled

```
Context

First-person singular pronoun.

Dictionary

Pronoun.

```

Never

Roman numeral.

Never

Iodine.

---

# Ranking Strategy

Each candidate meaning receives a score.

Factors

* Context similarity.
* Part-of-speech agreement.
* Story entity match.
* Exact case match.
* Lemma match.
* Named entity confidence.
* Chapter visibility.
* Dictionary confidence.

Highest confidence wins.

Popularity alone must never determine ranking.

---

# Fallback Rules

If

Story match fails

↓

Context match fails

↓

Dictionary fails

↓

LLM explanation unavailable

Return

```
No reliable explanation could be determined.

```

Never fabricate.

---

# Testing Matrix

The resolver must correctly classify:

| Selection  | Expected                                   |
| ---------- | ------------------------------------------ |
| Myrtle     | Character                                  |
| Daisy      | Character                                  |
| French     | Language/Nationality depending on sentence |
| US         | Country                                    |
| us         | Pronoun                                    |
| May        | Month or modal verb depending on sentence  |
| Turkey     | Country or bird depending on sentence      |
| Bill       | Person or invoice                          |
| Apple      | Company or fruit                           |
| Amazon     | Company or river                           |
| running    | run                                        |
| reappeared | reappear                                   |
| children   | child                                      |
| mice       | mouse                                      |
| I          | Pronoun                                    |
| he         | Pronoun                                    |
| they       | Pronoun                                    |

These are regression tests, **not hardcoded mappings**. The engine should derive the correct interpretation from morphology, casing, part of speech, surrounding context, and the spoiler-safe story graph.

---

## Acceptance Criteria

The Selection Resolution Engine is considered complete when:

* Every selection is classified before explanation.
* Exact casing is preserved and influences disambiguation.
* Lemmatization is used for dictionary lookup while displaying the original token.
* Story entities always outrank general dictionary and knowledge-base entries.
* Contextual meaning is displayed before any generic definition.
* Named entities are resolved from the spoiler-safe graph and presented as story context, not dictionary words.
* Common function words (or other configured stopwords) are suppressed or handled with lightweight grammatical explanations rather than forced through the dictionary pipeline.
* Unknown or ambiguous selections degrade gracefully without inventing meanings.
* The resolver operates entirely through general linguistic analysis, semantic classification, and context. **No book-specific, author-specific, or token-specific hardcoded rules are permitted.**
