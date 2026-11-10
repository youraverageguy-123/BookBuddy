# BookBuddy API Key Onboarding and AI Configuration Audit

## Summary

Design a polished, beginner-friendly AI onboarding flow that makes optional Gemini configuration simple, transparent, and trustworthy.

The goal is that a first-time user with no prior Gemini experience can obtain an API key, configure BookBuddy, verify the connection, understand what AI features do, and begin using them without leaving the application confused.

Core reader functionality must remain completely usable without any API key.


============================================================
1. AI MUST REMAIN OPTIONAL
============================================================

Requirements

- Never require an API key to read EPUB files.
- Never block library import.
- Never block notes.
- Never block bookmarks.
- Never block reader settings.
- Never repeatedly nag users to configure AI.
- "Skip for now" should always exist.

Clearly communicate:

"This feature is optional."

BookBuddy is a reader first.
AI is an enhancement.


============================================================
2. FIRST-TIME ONBOARDING
============================================================

If no API key exists:

Display an onboarding card.

Title

Enable Optional AI Features

Description

BookBuddy works completely offline.

Optional AI enables:

• Contextual explanations
• AI dictionary
• Translation
• Chapter analysis
• Image understanding

Buttons

[Get Free API Key]

[How to Get One]

[Skip]


============================================================
3. GOOGLE AI STUDIO
============================================================

Provide a button that opens

Google AI Studio

Do not ask users to search for it.

Provide another button

Official API Documentation

The documentation should explain
how to generate an API key.

Never link to unofficial tutorials.


============================================================
4. SETTINGS PAGE
============================================================

Create a dedicated AI page.

Sections

--------------------------------------------------

Status

Not Configured

Configured

Connection Failed

Quota Exceeded

--------------------------------------------------

Capabilities

Explain every feature.

Example

✓ AI Dictionary

✓ Context Explanation

✓ Translation

✓ Background Analysis

✓ Image Understanding

Each feature should include
a one-line explanation.


============================================================
5. API KEY INPUT
============================================================

Provide

API Key textbox

Paste button

Show / Hide key

Save button

Clear button

Never expose stored keys.

Never log keys.

Never export keys.


============================================================
6. CONNECTION TEST
============================================================

After saving

Run a lightweight verification.

Possible outcomes

Success

Invalid key

Network unavailable

Quota exceeded

Region unsupported

Permission denied

Unexpected API error

Show a friendly explanation.

Never expose stack traces.


============================================================
7. SUCCESS SCREEN
============================================================

Example

✓ Connected successfully

Provider

Google Gemini

Model

Configured automatically

Status

Ready

Last verification

Timestamp

Buttons

Test Again

Manage Keys


============================================================
8. FAILURE SCREEN
============================================================

Examples

Invalid API key

Quota exceeded

Network unavailable

Gemini unavailable

Each error should contain

Short explanation

Possible causes

Retry button

Documentation button


============================================================
9. PRIVACY INFORMATION
============================================================

Add a dedicated information panel.

Explain

Reading stays local.

Bookmarks stay local.

Notes stay local.

Progress stays local.

Collections stay local.

Statistics stay local.

Only AI requests explicitly initiated
or enabled by the user may send
required text or images to Gemini.

API keys remain encrypted locally.

No API keys appear in logs.

No API keys appear in exports.


============================================================
10. BACKGROUND ANALYSIS
============================================================

Explain exactly what happens.

When enabled

BookBuddy may analyze
completed chapters.

Analysis happens in the background.

Knowledge is stored locally.

Users may pause

Resume

Cancel

Disable background analysis.

Provide a small status indicator.


============================================================
11. MODEL MANAGEMENT
============================================================

Current model

Show model name.

Allow future expansion.

Example

Gemini 2.5 Flash

Future

Model selector

Provider selector


============================================================
12. AI FEATURE DISCOVERY
============================================================

When users attempt an AI feature
without a configured key

Show

"This feature requires an optional
Gemini API key."

Buttons

Configure

Learn More

Cancel

Never silently fail.


============================================================
13. DOCUMENTATION LINKS
============================================================

Provide direct links to

Google AI Studio

Official Gemini API Key Guide

Official Gemini Documentation

Open in browser.


============================================================
14. ACCESSIBILITY
============================================================

Keyboard navigation.

Proper focus order.

Copyable links.

Screen reader labels.

Visible success and failure icons.

Do not rely on color alone.


============================================================
15. SECURITY
============================================================

Encrypt stored keys.

Never display full keys after saving.

Allow replacing keys.

Allow removing keys.

Support multiple keys in the future.

Never send keys to logs.

Never include keys in backups.


============================================================
16. FUTURE EXPANSION
============================================================

Design UI so future providers
fit naturally.

Examples

Google Gemini

OpenAI

Anthropic

Local LLM

Do not hardcode Gemini-specific
layout decisions.


============================================================
17. ACCEPTANCE TESTS
============================================================

Verify

✓ Fresh install

✓ Skip AI

✓ Configure later

✓ Valid key

✓ Invalid key

✓ Offline startup

✓ AI disabled

✓ Background analysis enabled

✓ Background analysis disabled

✓ Key replacement

✓ Key removal

✓ Connection test

✓ Documentation links

✓ Privacy information

✓ Error handling

✓ Windows packaged application

✓ Portable application

✓ Reader works fully without AI


============================================================
18. DESIGN PRINCIPLE
============================================================

The user should never need to search
Google to understand how to enable AI.

Everything necessary to:

• understand AI
• obtain an API key
• configure it
• verify it
• troubleshoot it

should be discoverable directly from
within BookBuddy.
And everything should be template compatible.

AI should feel like an optional extension
to an excellent reader, not a prerequisite
for using the application.