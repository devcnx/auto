# Dynamic Ollama Assistant – Application Overview

## Vision & Purpose
The Dynamic Ollama Assistant is a desktop application that empowers you to operate local large language models (LLMs) with rich context, curated prompts, and data pulled from multiple sources. It provides an opinionated workflow for:

- **Prompt discovery and management** via CSV-driven libraries.
- **Context gathering** from uploaded files, screenshots, spreadsheets, and authenticated web sessions.
- **Conversation orchestration** with Ollama for iterative reasoning.
- **Automation helpers** such as web crawling, AI-assisted login analysis, and remote browser control.

The result is a single control center that bridges structured prompts, user knowledge, and live web data so you can run complex research or content tasks with local models.

## High-Level Architecture
- **GUI (`gui.py`)** – Rich Tkinter interface that coordinates all features. Includes tree views for prompts, file upload panels, chat area, crawl insights, and remote Chrome controls.
- **Prompt & context management** – Prompt CSV ingestion, placeholder handling, conversation state persistence, and parsed file aggregation.
- **Web automation layer** – Playwright-backed authenticated crawler (`authenticated_scraper.py`) plus helper modules for remote Chrome launch (`launch_chrome_debug.py`, inlined utilities).
- **LLM integration** – Uses `dynamic_ollama_assistant.py` for querying Ollama models, streaming responses into the GUI.
- **Supporting utilities** – `file_utils.py`, `auth_dialogs.py`, `web_scraper.py`, and other helpers for file processing, login form collection, and generic scraping.

## Dependency-Based Build Plan
The following roadmap breaks down the build order into dependency-aware stages. Each stage lists prerequisites, primary objectives, deliverables, and downstream consumers.

### Stage 0 – Environment & Baseline Data
- **Prerequisites**: None.
- **Objectives**:
  - Provision Python virtual environment, install `requirements.txt`, and verify Playwright browsers + Ollama model availability.
  - Create starter CSV prompt files under `data/` following the schema in `README.md`.
- **Deliverables**:
  - Working `.venv/` or environment spec.
  - Sample prompt categories to power initial UI tests.
- **Unlocks**: Enables prompt ingestion and GUI development with real data.

### Stage 1 – Prompt Library Ingestion & Navigation
- **Prerequisites**: Stage 0 data.
- **Objectives**:
  - Implement CSV parsing utilities in `file_utils.py`.
  - Build prompt tree loader and search/filter interactions inside `gui.py::UIComponents`.
  - Support placeholder detection and editing widgets, even if they submit static values.
- **Deliverables**:
  - Prompt tree rendered in GUI with expand/collapse.
  - Placeholder metadata available for later chat integration.
- **Unlocks**: Required for conversation orchestration (Stage 2).

### Stage 2 – Conversation Engine & Ollama Integration
- **Prerequisites**: Stage 1 UI to select prompts.
- **Objectives**:
  - Connect `dynamic_ollama_assistant.query_ollama_chat_for_gui()` streams into the chat panel.
  - Implement conversation history buffer, typing indicator, and basic context assembly from placeholders.
  - Ensure prompts without placeholders can trigger instant conversations.
- **Deliverables**:
  - Operational chat panel sending prompts to Ollama and streaming responses.
  - Generic conversation log appended to `conversation_history` in `OllamaGUI`.
- **Unlocks**: Allows persistence and context management (Stage 3) to latch onto real chats.

### Stage 3 – Context Persistence & File Handling
- **Prerequisites**: Stage 2 conversation model.
- **Objectives**:
  - Implement file upload dialogs, screenshot/OCR placeholders, and parsed file registry (`file_utils.py`).
  - Persist session metadata to `conversation_state.json` and restore on launch.
  - Display parsed file summaries in the GUI, with linking into conversation context.
- **Deliverables**:
  - Stable state persistence across launches.
  - Parsed content list integrated with conversation composer.
- **Unlocks**: Required for storing scrape outputs and authenticated sessions.

### Stage 4 – Standard Web Scraping (Unauthenticated)
- **Prerequisites**: Stage 3 persistence.
- **Objectives**:
  - Integrate `web_scraper.scrape_url()` (requests + BeautifulSoup) into GUI controls.
  - Pipe scraped content into parsed files and optionally directly into conversation context.
  - Provide progress/status messaging in the UI alongside error handling.
- **Deliverables**:
  - One-click page scrape feature populating context store.
- **Unlocks**: Establishes content ingestion contract used by Playwright crawler.

### Stage 5 – Playwright Crawl Pipeline
- **Prerequisites**: Stage 4 ingestion model.
- **Objectives**:
  - Wire `authenticated_scraper.playwright_crawl_sync()` or equivalent into `crawl_site_playwright()`.
  - Build crawl insights panel (status text, progress log, stop button) in the GUI.
  - Store crawl output (pages, AI summaries) via Stage 3 persistence mechanisms.
- **Deliverables**:
  - Functional dynamic crawler for public content.
  - UI feedback on crawl progress/errors.
- **Unlocks**: Provides base on which authenticated flows will run.

### Stage 6 – Remote Chrome Debug Controls
- **Prerequisites**: Stage 5 Playwright integration.
- **Objectives**:
  - Implement Chrome launcher, stop button, and endpoint tester in `gui.py` (already partially complete).
  - Sync environment variables and button states with `PLAYWRIGHT_REMOTE_ENDPOINT` usage in crawlers.
  - Ensure cleanup on application shutdown.
- **Deliverables**:
  - GUI-managed remote debugging lifecycle for Chrome.
- **Unlocks**: Allows authenticated crawler to attach to manual login sessions.

### Stage 7 – Authenticated Login Assistant
- **Prerequisites**: Stage 6 remote browser tools, Stage 5 crawler.
- **Objectives**:
  - Finalize AI login analysis, manual selector dialogs (`auth_dialogs.py`), and credentials workflow in `gui.py`.
  - Handle session persistence (`scraper_sessions.json`) and CAPTCHA detection fallbacks.
  - Integrate authenticated results into parsed file store with appropriate metadata.
- **Deliverables**:
  - End-to-end authenticated scraping flow with AI-assistance and manual overrides.
- **Unlocks**: Capstone workflow for secure data gathering.

### Stage 8 – Polish, Observability & Testing
- **Prerequisites**: All prior stages implemented.
- **Objectives**:
  - Address outstanding lint (Ruff, Pylint, Sourcery) and refactor monolithic modules.
  - Expand automated tests (unit + integration) covering prompt loading, crawl flows, and remote browser management.
  - Improve logging, user notifications, and error recovery paths across the app.
- **Deliverables**:
  - Production-ready codebase with monitoring hooks and stable UX.
- **Unlocks**: Supports future feature growth and external contributions.

## Core Modules & Responsibilities
- `gui.py`
  - Main `OllamaGUI` class (Tkinter). Handles UI layout, event wiring, streaming chat, context state, and remote Chrome management.
  - `UIComponents` class builds reusable widgets: prompt tree, conversation panel, file operations, Playwright crawl controls, status area, etc.
  - Integrates new remote Chrome workflow: launch, test, and stop buttons; environment sync; status display.
  - Persists conversation state to `conversation_state.json` and restores it on launch.
- `dynamic_ollama_assistant.py`
  - CLI-oriented logic now leveraged by GUI for prompt loading, placeholder templating, OCR-based placeholder fill, and streaming replies.
  - Provides utility functions for warm-up, context building, and conversation logging.
- `authenticated_scraper.py`
  - Asynchronous Playwright crawler with authenticated session handling, AI-assisted login form detection, CAPTCHA diagnostics, and multi-page crawling.
  - Integrates with existing parsed file system and optional AI page summaries.
- `browser_launcher.py` / `launch_chrome_debug.py`
  - Standalone helpers for remote debugging sessions (legacy CLI entry points). GUI currently reimplements launch logic for in-app control; these scripts remain useful for headless automation.
- `auth_dialogs.py`
  - Tkinter dialogs for login analysis results, manual selector entry, and verification prompts.
- `file_utils.py`
  - Helper utilities for CSV parsing, file aggregation, deduplication, and conversation persistence.
- `ui_components.py` / `gui_refactored.py`
  - Earlier experiments/refactors for the GUI components. Main app currently relies on `gui.py` but these files document alternative architectures.
- `web_scraper.py`
  - Lightweight unauthenticated scraper used in earlier CLI flows.

## Feature Overview
### Prompt Library & Conversation Management
- **Prompt Tree Browser** – Browse categories, subcategories, and prompt entries derived from CSV files in `data/`. Supports search, expand/collapse, and contextual tooltips.
- **Dynamic Placeholder Resolution** – Prompts can contain placeholders. The GUI provides inline editors and supports loading values from files or OCR (via Smoldocling integration configured elsewhere).
- **Conversation Panel** – Rich-text chat area with streaming responses, token usage estimates, and conversation status indicator. Conversations can be restricted to use only certain context sources if desired.
- **Conversation Persistence** – Session state (conversation history, parsed files, settings) is stored in `conversation_state.json` and reloaded automatically.
- **CSV Library Refresh** – GUI actions to rescan `data/` and update the prompt tree without restarting the app.

### File & Context Management
- **File Uploads** – Supports local file selection (PDF, DOCX, CSV, etc.) to feed context. Files appear in a parsed-files list with previews.
- **Screenshot / OCR ingestion** – Flow to convert images into text placeholders invoked during prompt filling.
- **Spreadsheet Integration** – When CSVs or Excel files are loaded, the app can preview them and allow referencing specific sheets/rows.
- **Parsed Content Aggregation** – Consolidates scraped pages, uploaded files, and conversation artifacts into a single context store for LLM prompts.

### Web Automation & Scraping
- **Standard Web Scrape** (`web_scraper.py`) – Quickly fetches a single page via `requests`/`BeautifulSoup`, storing clean text into context.
- **Playwright Crawl (GUI)** – `crawl_site_playwright()` orchestrates dynamic crawls, handles login credentials, respects same-domain limits, and logs progress in a live panel.
- **Authenticated Sessions** (`authenticated_scraper.AuthenticatedScraper`)
  - AI-assisted login form analysis to auto-detect selectors.
  - Manual selector entry dialogs for complex forms.
  - CAPTCHA / bot detection with human-in-the-loop workflows.
  - Cookie/session persistence via `scraper_sessions.json`.
  - Per-page AI summaries and follow-up question suggestions.
- **Manual Verification Browser** – Launches a one-off Playwright window for completing 2FA or captcha challenges.

### Remote Chrome Debugging Workflow
- **Launch Chrome** – Built-in button to start a Chromium browser with remote debugging enabled (defaults to port 9222), using a temporary profile.
- **Stop Chrome** – Terminates the GUI-launched Chrome instance and cleans up its profile directory.
- **Test Endpoint** – Pings `/json/version` to validate connectivity, updating UI status and environment variables.
- **Attach Toggle** – Option to instruct Playwright to attach to an existing remote browser instead of launching its own.
- **Status Feedback** – Live status label shows whether the remote endpoint is connected, waiting, or failed.

### Login & Authentication Assistant
- **Analyze Login** – Uses Ollama to inspect HTML and return CSS selectors for login forms.
- **Login & Scrape** – Executes an authenticated crawl using provided credentials and selectors.
- **Verification Dialogs** – Guides the user when CAPTCHAs or human verification is detected, offering manual options.
- **Session Management** – Saves cookies/tokens to reuse across crawls.

### Conversation Enhancements & Utilities
- **Context Restriction Toggle** – Allows switching between shared/global context and more restricted prompt responses.
- **Thinking Indicator** – Visual spinner while the LLM streams responses.
- **AI Summary Toggle** – Choose whether to generate LLM summaries during crawls.
- **CSV Export** – Export conversation or crawl results to CSV for downstream analysis (implemented in supporting utilities).
- **Tooltips & Help Popovers** – Many UI elements include tooltips (via `ToolTip`) and popover dialogs for added guidance.

## Key Workflows
1. **Prompt-driven Chat Session**
   1. Launch GUI (`python gui.py`).
   2. Select a prompt from the tree and fill placeholders.
   3. Optionally attach contextual files, scraped pages, or manual notes.
   4. Start the conversation; responses stream from Ollama.
   5. Save or export the conversation for later use.

2. **Authenticated Web Crawl**
   1. Enable remote browser attachment or let the app launch Chrome.
   2. Click “Analyze Login” to auto-detect selectors, or specify manually.
   3. Provide credentials in the GUI fields.
   4. Launch “Login & Scrape” to gather authenticated content and AI summaries.
   5. Review results in parsed files and optionally insert into prompts.

3. **Remote Chrome Control**
   1. Click “Start Chrome” to spawn a debug session (or attach to an existing endpoint).
   2. Use “Test Endpoint” to confirm DevTools availability.
   3. Run Playwright crawls that leverage the active endpoint.
   4. Stop the session via the new “Stop Chrome” button when finished.

## Data & Persistence
- **Conversation State:** `conversation_state.json`
- **Window State:** `window_state.json`
- **Session Cookies:** `scraper_sessions.json`
- **Prompt Data:** CSV files under `data/`
- **Conversation Logs:** Stored under `output/` when exported.

## CLI Utilities & Scripts
- `dynamic_ollama_assistant.py` – Original CLI interface for prompt selection and chatting.
- `launch_chrome_debug.py` – Standalone script for remote Chrome launch.
- `browser_launcher.py` – Reusable module for Chrome automation (may be superseded by GUI logic).
- `web_scraper.py` – Simple CLI/web scraping entry point.

## Testing & Tooling
- `tests/` directory contains early unit tests for prompt parsing, utilities, and GUI helpers.
- `pytest.ini` configures test discovery.
- Ruff, Pylint, and Sourcery warnings are surfaced in the IDE; addressing them is ongoing work.

## Planned / In-Progress Enhancements
- **Lint & Refactor** – Resolve outstanding lint warnings and refactor large modules (`gui.py`) into reusable components.
- **Headless Automation Modes** – Expand CLI scripts for unattended crawls leveraging shared session data.
- **Better Error Surfacing** – Improve handling of Playwright connection errors (e.g., when remote Chrome isn’t running).
- **Configurable Profiles** – Allow specifying persistent user data dirs for remote Chrome sessions.
- **Enhanced Testing** – Add integration tests for GUI workflows and remote browser control.

## Getting Started
1. Install dependencies: `pip install -r requirements.txt`.
2. Ensure Ollama is running locally with your desired model pulled.
3. Populate `data/` with prompt CSVs (see `README.md` for structure).
4. Run the GUI: `python gui.py` (use the project’s virtual environment to access Playwright and GUI dependencies).
5. Explore the features via the left-hand navigation, file controls, and conversation panel.

For more detailed CLI usage, refer to `README.md`. This overview focuses on the integrated desktop experience.
