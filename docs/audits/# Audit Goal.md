# Audit Goal

**Remove `gemini_test.py` as the application entrypoint.**

After this audit:

* `gemini_test.py` no longer starts BookBuddy.
* Gemini becomes a service, not the application.
* Backend has a proper initialization lifecycle.
* React/Tauri can launch the backend without knowing anything about Gemini.
* Future providers (OpenAI, Claude, local models) can be added without changing parser logic.

This audit **does not** redesign your parser, graph, replay, dictionary, image pipeline, or API. It only addresses the startup architecture.

---

# Current Architecture (Problem)

Current flow is approximately:

```text
gemini_test.py
      │
      ▼
Load API keys
      │
      ▼
Initialize Gemini
      │
      ▼
Parser
      │
      ▼
Replay
      │
      ▼
Graph
      │
      ▼
Output
```

Problems:

* Application identity is tied to Gemini.
* Startup logic and AI logic are mixed.
* Difficult to launch from another application.
* Future providers require touching startup code.
* Test script has become production entrypoint.

---

# Target Architecture

```text
BookBuddy

main.py
    │
    ▼
Initialize Application
    │
    ▼
Load Configuration
    │
    ▼
Initialize Services
    │
    ▼
Create API
    │
    ▼
Wait For Requests
```

Notice:

Gemini never starts the application.

It is merely initialized.

---

# Required Responsibilities

## main.py

Only responsible for:

* application startup
* configuration loading
* dependency initialization
* service registration
* API startup
* graceful shutdown

Must NEVER:

* build prompts
* parse books
* call Gemini
* analyze chapters

---

## config.py

Single responsibility:

Load configuration.

Examples:

* API keys
* database paths
* cache directory
* parser settings
* image settings
* AI model selection

Should expose one immutable configuration object.

Must NEVER:

* initialize services
* open database
* call APIs

---

## bootstrap.py (recommended)

Purpose:

Create every long-lived service.

Example order:

```text
Configuration

↓

Database

↓

Caches

↓

AI Manager

↓

Parser Services

↓

Replay

↓

Dictionary

↓

Image Pipeline

↓

API
```

Nothing else.

---

## app.py

Creates FastAPI application.

Registers routes.

Registers middleware.

Registers startup/shutdown hooks.

Returns application.

Nothing more.

---

# Gemini Refactor

Current conceptual state:

```text
gemini_test.py

↓

Gemini

↓

Everything
```

Target:

```text
AIManager

↓

GeminiProvider
```

Parser communicates only with:

```python
ai_manager.generate(...)
```

Never:

```python
gemini.generate(...)
```

---

# Gemini Provider Responsibilities

Allowed:

* send prompts
* receive responses
* retry
* safety handling
* provider-specific parsing
* usage statistics

Forbidden:

* parser orchestration
* graph mutation
* replay logic
* database writes
* startup

---

# AI Manager Responsibilities

Owns:

* provider selection
* API key rotation
* quota handling
* retry policy
* failover
* model selection

Parser never knows:

* which key
* which provider
* which model

Parser only requests:

```text
Generate analysis.
```

---

# Startup Lifecycle

Target sequence:

```text
main.py

↓

Load Config

↓

Initialize Logger

↓

Open Database

↓

Initialize Cache

↓

Initialize AI Manager

↓

Initialize Parser Services

↓

Initialize Replay

↓

Initialize Dictionary

↓

Initialize Image Pipeline

↓

Create FastAPI

↓

Serve Requests
```

No parsing occurs during startup.

---

# Shutdown Lifecycle

Should cleanly:

* close SQLite
* flush caches
* stop worker threads
* close HTTP clients
* save pending state

No abrupt exits.

---

# Configuration Audit

Configuration should become centralized.

Instead of scattered constants:

```text
Gemini Keys

Parser Limits

Models

Database Paths

Cache Paths

Output Directories
```

everything should originate from one configuration source.

Nothing should hardcode paths.

---

# Dependency Direction

Must become:

```text
main

↓

bootstrap

↓

services

↓

providers
```

Never:

```text
provider

↓

main
```

Lower layers never import higher layers.

---

# Parser Contract

Parser should know only:

```python
analysis = ai_manager.generate(...)
```

Parser should NOT know:

* Gemini exists
* number of API keys
* quota exhaustion
* provider names

---

# Future Provider Support

After refactor:

```text
AIManager

├── Gemini
├── OpenAI
├── Claude
├── Local Llama
└── DeepSeek
```

Parser unchanged.

---

# Logging

Startup should produce something like:

```text
Starting BookBuddy Backend...

Loading Configuration...

Opening Database...

Loading Dictionary...

Initializing AI Manager...

Registering Routes...

Backend Ready.
```

No Gemini-specific startup messages.

---

# Error Handling

If AI initialization fails:

Application should still start if AI is optional.

API can return:

```text
AI Service Unavailable
```

instead of crashing.

Only mandatory startup failures should terminate the backend.

---

# File Naming

Suggested structure:

```text
backend/

main.py
app.py
bootstrap.py
config.py

services/
    ai_manager.py
    parser_service.py
    replay_service.py
    dictionary_service.py
    image_service.py

ai/
    gemini_provider.py
    provider_base.py
```

`gemini_test.py` should be removed as the production entrypoint. If you want to keep it, repurpose it as a developer-only diagnostic script for testing Gemini connectivity and provider behavior in isolation.

---

# Success Criteria Checklist

* `main.py` is the sole backend entrypoint.
* Startup performs initialization only.
* No parsing occurs during startup.
* No AI requests occur during startup.
* Gemini is no longer referenced outside the AI layer.
* Parser depends only on `AIManager`.
* API launches independently of Gemini implementation details.
* Configuration is centralized.
* Initialization order is deterministic.
* Shutdown is graceful.
* `gemini_test.py` is no longer part of the production execution path.

