# LLM.md

This file provides guidance to Ornith 1.0 when working with code in this repository.

## Project Overview

Spartan is an AI-powered autonomous penetration testing agent. It uses an agentic pipeline to solve CTF challenges, Hack The Box machines, and authorized security assessments. Output is raw streaming to stdout.


**Stack:** Python 3.12+, uv, Agent SDK

## Common Commands

```bash
# Setup
uv sync                           # Install dependencies
uv run spartan --target X      # Run locally

# Testing
make test                         # Run all tests
make test-cov                     # Run tests with coverage
uv run pytest tests/test_controller.py -v  # Run single test file

# Code Quality
make lint                         # Run ruff linter
make format                       # Format code with ruff
make typecheck                    # Run mypy type checking
make check                        # All checks (lint + typecheck)
```

## Architecture

### Entry Point
- `spartan/interface/main.py` - CLI entry, argument parsing, raw streaming output
- Command: `spartan --target <IP/URL> [--max-iterations N] [--instruction "hint"] [--debug]`

### Core Layer (`spartan/core/`)
- **pipeline.py** - `PipelineOrchestrator`: Runs an iteration loop, each iteration with a fresh backend + controller. Data classes: `IterationResult`, `LoopResult`. The agent writes a context file (`spartan_context.md`) as it works; the orchestrator reads it after each iteration and feeds it into the next. Loop terminates on flag capture, error, or max iterations.
- **backend.py** - `AgentBackend` interface + `ClaudeCodeBackend` implementation (framework-agnostic design)
- **controller.py** - `AgentController`: 5-state lifecycle (IDLE->RUNNING->PAUSED->COMPLETED->ERROR), pause/resume at message boundaries. Used per-iteration by the pipeline orchestrator
- **events.py** - `EventBus`: Singleton pub/sub for agent-output decoupling (STATE_CHANGED, MESSAGE, TOOL, FLAG_FOUND events)
- **session.py** - `SessionStore`: File-based persistence in `~/.spartan/sessions/`, supports session resumption
- **config.py** - Pydantic settings with `.env` file support; includes `max_iterations` (default 10) and `context_file` (default `spartan_context.md`)

### System Prompts (`spartan/prompts/`)
- **system_prompt.py** - Unified prompt builders: `build_system_prompt`, `build_first_task_prompt`, `build_continuation_task_prompt`. Shared fragments (`_IDENTITY`, `_TOOLS`, `_FLAG_PATTERNS`, `_PERSISTENCE`, `_FALLBACK_STRATEGIES`, `_CTF_CATEGORIES`, `_METHODOLOGY`, `_CONTEXT_PERSISTENCE`)

## Key Patterns

- **Iteration Loop**: `PipelineOrchestrator` runs iterations in a loop. Each iteration gets a fresh `ClaudeCodeBackend` + `AgentController` (system prompt is set at connect time, so a new backend is needed per iteration). The agent maintains a context file; the orchestrator reads it after each iteration and injects it into the next iteration's task prompt. Falls back to truncated prior output if the context file is missing.
- **Event-Driven**: Raw mode subscribes to EventBus; agent emits events for state changes, messages, flags
- **Singletons**: `EventBus.get()` for global access
- **Abstract Backend**: `AgentBackend` interface allows swapping LLM backends
- **Flag Detection**: Regex patterns in controller.py match `flag{}`, `HTB{}`, `CTF{}`, 32-char hex

## Testing

Tests use pytest with pytest-asyncio. Mock backends for unit tests.

```bash
uv run pytest tests/ -v                           # All tests
uv run pytest tests/test_controller.py -v         # Single file
uv run pytest tests/test_controller.py::test_name # Single test
```

## Repository Structure

```
.
├── spartan/           # Autonomous agent (Claude-only, claude CLI backend)
│   ├── core/             # Pipeline, controller, events, session, backend
│   ├── interface/        # CLI entry point (raw streaming)
│   └── prompts/          # System prompts (system_prompt.py)
├── spartan_legacy/    # Modernized legacy: interactive 3-session + PTT, multi-LLM
│   ├── llm/              # Native per-provider LLM layer (registry, factory, client, providers)
│   ├── utils/            # Orchestrator (spartan.py) + REPL helpers
│   └── prompts/          # Classic PTT/session prompts
├── tests/                # Test suite (tests/legacy/ covers spartan_legacy)
└── Makefile              # Development commands
```

### Modernized Legacy (`spartan_legacy/`)

The classic human-in-the-loop tool, rebuilt on a native multi-provider LLM
layer. CLI: `spartan-legacy` (`--list-models`, `--smoke-test`, `--reasoning-model`,
`--parsing-model`, `--base-url`).

- **llm/registry.py** — single source of truth for supported models (`ModelSpec`/`PROVIDERS`),
  web-verified IDs. `--list-models` and the README table render from it.
- **llm/factory.py** — `get_client(model_name)` -> `LLMClient`; resolves provider, builds it.
- **llm/client.py** — `LLMClient` bridges async providers to the core's synchronous
  `send_new_message`/`send_message` (drop-in for the old `LLMAPI`); holds per-conversation history.
- **llm/providers/** — `OpenAICompatibleProvider` (OpenAI + DeepSeek/Ollama/xAI/Qwen/Moonshot via
  base_url; Responses-API fallback for `*-pro`/`*-codex`), `AnthropicProvider`, `GeminiProvider`.
- **llm/config.py** — pydantic-settings credentials (per-provider keys + base-url overrides).
- **smoke_test.py** — `--smoke-test` makes a real round-trip per configured model (acceptance gate).

Note: `make typecheck` is scoped to `spartan/`; the new package is covered by ruff
(`make lint`) and `tests/legacy/`. Run `uv run mypy spartan_legacy/llm/` for its typed core.

## Modification Requirements

When modifying code, ensure:
- Adherence to existing architecture and patterns
- Comprehensive tests for new features
- Ensure to run tests after changes, and do further updates to ensure code quality. Always keep the documentation up to date with any architectural changes. Also ensure all tests pass after modifications.
