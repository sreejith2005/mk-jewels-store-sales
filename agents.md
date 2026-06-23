# MK Jewels Store Tool - AI Assistant Guidelines

This document contains mandatory instructions for AI coding assistants working in this repository. All agents must read and follow these guidelines before making changes.

---

## 1. Project Mission & Architecture

MK Jewels Store Tool is an AI-powered customer interaction monitoring and intelligence platform for M K Jewels.

The system:
* Captures store conversations.
* Performs speech transcription.
* Analyzes interactions using AI models.
* Generates alerts.
* Provides operational visibility through a web dashboard.

The codebase is evolving from demo software to a production-ready cloud-hosted platform. Always prioritize long-term production readiness and incremental improvements over large rewrites.

---

## 2. Component Boundaries

### 2.1 Backend
**Location:** `/mk-jewels-assistant`
**Entry point:** `main.py`

**Responsibilities:**
* Audio processing and speech transcription.
* AI triage and alert generation.
* Session tracking and database persistence.
* External AI provider integrations.

**Tech Stack:**
* Python
* SQLite (current)
* Gemini
* OpenRouter

**Backend Standards:**
* Follow PEP 8 and use type hints for new code.
* Prefer small focused functions with docstrings.
* Keep business logic separate from infrastructure code.
* Use virtual environments and update `requirements.txt` when dependencies change.

### 2.2 Frontend
**Location:** `/dashboard-ui`

**Responsibilities:**
* Session monitoring and operational dashboard.
* Alert visualization and analytics.

**Tech Stack:**
* Next.js App Router
* React and TypeScript
* Tailwind CSS
* Shadcn UI and Base UI

**Frontend Standards:**
* Follow App Router and TypeScript best practices.
* Use reusable components and Shadcn UI patterns.
* Avoid duplicated UI components and unnecessary custom CSS.
* Do not inline business logic in pages.

---

## 3. Production & Safety Requirements

### 3.1 AI Pipeline Safety
The speech → transcription → triage pipeline is business critical.

**When modifying AI workflows, you MUST preserve:**
* Auditability and request tracing.
* Session tracking and alert generation behavior.
* Failure reporting.

**You MUST NEVER:**
* Silently discard transcription or model failures.
* Remove logging around AI decisions.
* Hardcode API keys or model credentials.

**Future Strategy:**
Prefer abstractions allowing Gemini, OpenRouter, Ollama, vLLM, or self-hosted models. Avoid tight coupling to a single provider.

### 3.2 Database Safety
The database (`sessions.db`) contains operational business records.

**You MUST NEVER:**
* Delete the database or drop tables.
* Reset production data.
* Remove historical session records.

**Schema changes require:**
* Migration strategy and rollback strategy.
* Documentation updates.
* Design considerations for future PostgreSQL migration.

### 3.3 Logging & Security
**Logging:**
* Prefer structured logging and meaningful error messages.
* Ensure explicit failure reporting and log/session correlation.
* Avoid empty exception handlers and console spam.

**Security:**
* Never commit API keys, secrets, credentials, tokens, or DB exports.
* Use `.env` for local secrets and `.env.example` as documentation.
* Never log sensitive credentials.

---

## 4. Validation & Definition of Done

### 4.1 Validation Commands
Before completing any task, run relevant validation, report results, or explain if skipped.

**Backend Validation:**
```bash
cd mk-jewels-assistant
pytest
```

**Frontend Validation:**
```bash
cd dashboard-ui
npm run lint
npm run build
```

### 4.2 Definition of Done
A task is NOT complete until all of the following are met:
1. Relevant code is implemented.
2. Existing functionality is preserved.
3. Relevant tests pass.
4. New Python code includes appropriate type hints.
5. Error handling is present.
6. Logging is preserved.
7. Documentation is updated when necessary.
8. Production impact has been considered.

### 4.3 Technical Debt Management
This repository contains demo-era code. When technical debt is discovered:
* Document it and report it.
* Improve it ONLY when directly related to the task.
* Avoid unrelated refactoring.
* Favor incremental modernization.
