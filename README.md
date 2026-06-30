<!-- Improved compatibility of back to top link: See: https://github.com/othneildrew/Best-README-Template/pull/73 -->
<a name="readme-top"></a>

<!-- PROJECT SHIELDS -->
[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url]
[![Discord][discord-shield]][discord-url]

<!-- PROJECT LOGO -->
<br />
<div align="center">

<h3 align="center">Spartan</h3>

  <p align="center">
    AI-Powered Autonomous Penetration Testing Agent
    <br />
    <strong>Published at USENIX Security 2024</strong>
    <br />
    <br />
    <a href="https://spartan.com"><strong>Official Website: spartan.com »</strong></a>
    <br />
    <br />
    <a href="https://www.usenix.org/conference/usenixsecurity24/presentation/deng">Research Paper</a>
    ·
    <a href="https://github.com/GreyDGL/Spartan/issues">Report Bug</a>
    ·
    <a href="https://github.com/GreyDGL/Spartan/issues">Request Feature</a>
  </p>
</div>

<!-- ABOUT THE PROJECT -->
<a href="https://trendshift.io/repositories/3770" target="_blank"><img src="https://trendshift.io/api/badge/repositories/3770" alt="GreyDGL%2FSpartan | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

---

## Demo

### Installation
[![Installation Demo](https://asciinema.org/a/761661.svg)](https://asciinema.org/a/761661)

[Watch on YouTube](https://www.youtube.com/watch?v=RUNmoXqBwVg)

### Spartan in Action
[![Spartan Demo](https://asciinema.org/a/761663.svg)](https://asciinema.org/a/761663)

[Watch on YouTube](https://www.youtube.com/watch?v=cWi3Yb7RmZA)

---

## What's New in v1.0 (Agentic Upgrade)

- **Iteration Loop** - The agent runs continuously, maintains a context file with progress, and restarts with prior context when hitting limits. Loop terminates on flag capture or max iterations.
- **Autonomous Agent** - Agentic pipeline for intelligent, autonomous penetration testing
- **Session Persistence** - Save and resume penetration testing sessions

> **Multi-model support** is available today in the interactive **modernized legacy** mode
> (`spartan-legacy`) — OpenAI, Anthropic, Google Gemini, DeepSeek, xAI, Qwen, Moonshot, and
> local Ollama. See [Interactive Multi-LLM Mode](#interactive-multi-llm-mode-modernized-legacy).

---

## Features

- **AI-Powered Challenge Solver** - Leverages LLM advanced reasoning to perform penetration testing and CTFs
- **Live Walkthrough** - Tracks steps in real-time as the agent works through challenges
- **Multi-Category Support** - Web, Crypto, Reversing, Forensics, PWN, Privilege Escalation
- **Real-Time Feedback** - Watch the AI work with live activity updates
- **Extensible Architecture** - Clean, modular design ready for future enhancements

---

## Quick Start

### Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** - Python package manager
- **Claude Code CLI** (`claude`) - installed and authenticated. See [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code)

### Installation

```bash
git clone https://github.com/GreyDGL/Spartan.git
cd Spartan
make install    # runs uv sync
```

### Commands Reference

| Command | Description |
|---------|-------------|
| `make install` | Install dependencies |
| `make test` | Run all tests |
| `make check` | Run lint + typecheck |
| `make build` | Build distributable package |

---

## Usage

```bash
# Run against a target
spartan --target 10.10.11.234

# With challenge context
spartan --target 10.10.11.50 --instruction "WordPress site, focus on plugin vulnerabilities"

# Limit iterations
spartan --target 10.10.11.234 --max-iterations 5
```

The agent runs in an **iteration loop**: it works autonomously, maintains a context file with progress, and restarts with prior context when hitting limits. The loop terminates on flag capture or max iterations (default: 10).

---

## Interactive Multi-LLM Mode (modernized legacy)

The classic, human-in-the-loop Spartan from the USENIX 2024 paper is preserved and
modernized as `spartan-legacy`. It runs three cooperating LLM sessions —
**reasoning / generation / parsing** — that maintain a **Pentesting Task Tree (PTT)** while you
drive the session interactively (`next`, `more`, `todo`, `discuss`). Unlike the autonomous agent
(Claude-only), this mode talks **natively** to many providers via their official SDKs.

### Configure providers

Set an API key for any provider you want to use (in your environment or `.env` — see
`.env.example`). Only the providers you configure are enabled.

```bash
OPENAI_API_KEY=...        ANTHROPIC_API_KEY=...     GEMINI_API_KEY=...   # or GOOGLE_API_KEY
DEEPSEEK_API_KEY=...      GROK_API_KEY=...          QWEN_API_KEY=...     KIMI_API_KEY=...
```

### Run

```bash
# Auto-pick the best available models for each session
spartan-legacy

# Choose models per session
spartan-legacy --reasoning-model claude-opus-4-8 --parsing-model gemini-3.5-flash

# Local model via Ollama (OpenAI-compatible)
spartan-legacy --reasoning-model ollama:qwen3 --base-url http://localhost:11434/v1

# List every supported model (shows which providers are configured)
spartan-legacy --list-models

# Live round-trip every configured model and print a pass/fail matrix
spartan-legacy --smoke-test
```

### Supported models (web-verified June 2026)

`spartan-legacy --list-models` always renders the live registry. Re-run `--smoke-test`
after model IDs change. Current snapshot:

| Provider | Current models | Legacy (kept) | Env key |
|----------|----------------|---------------|---------|
| **OpenAI** | `gpt-5.5`, `gpt-5.5-pro`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-5.2`, `gpt-5.3-codex` | `gpt-4o`, `gpt-4o-mini`, `o3`, `o4-mini` | `OPENAI_API_KEY` |
| **Anthropic** | `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001` | — | `ANTHROPIC_API_KEY` |
| **Google Gemini** | `gemini-3.1-pro`, `gemini-3.5-flash`, `gemini-3-pro`, `gemini-3.1-flash-lite` | `gemini-2.5-pro`, `gemini-2.5-flash` | `GEMINI_API_KEY` / `GOOGLE_API_KEY` |
| **DeepSeek** | `deepseek-v4-flash`, `deepseek-v4-pro` | `deepseek-chat`, `deepseek-reasoner` | `DEEPSEEK_API_KEY` |
| **xAI Grok** | `grok-4.3` | — | `GROK_API_KEY` / `XAI_API_KEY` |
| **Alibaba Qwen** | `qwen3.7-max`, `qwen3.5-flash` | `qwen3-max` | `QWEN_API_KEY` / `DASHSCOPE_API_KEY` |
| **Moonshot Kimi** | `kimi-k2.6` | — | `KIMI_API_KEY` (`.cn` default; set `MOONSHOT_BASE_URL` for `.ai`) |
| **Local (Ollama)** | `ollama:<model>` (e.g. `ollama:qwen3`) | — | none (`OLLAMA_BASE_URL`) |

> The registry lives in `spartan_legacy/llm/registry.py` (the single source of truth).
> Adding a model is one `ModelSpec` entry; OpenAI-compatible providers reuse one connector.

---

## Telemetry

Spartan collects anonymous usage data to help improve the tool. This data is sent to our [Langfuse](https://langfuse.com) project and includes:
- Session metadata (target type, duration, completion status)
- Tool execution patterns (which tools are used, not the actual commands)
- Flag detection events (that a flag was found, not the flag content)

**No sensitive data is collected** - command outputs, credentials, or actual flag values are never transmitted.

### Opting Out

```bash
# Via command line flag
spartan --target 10.10.11.234 --no-telemetry

# Via environment variable
export LANGFUSE_ENABLED=false
```

---

## Benchmarks

Spartan achieved an **86.5% success rate** (90/104 benchmarks) on the XBOW validation suite:

- **Cost**: Average $1.11, Median $0.42 per successful benchmark
- **Time**: Average 6.1 minutes, Median 3.3 minutes per successful benchmark
- **Success rates by difficulty**:
  - Level 1: 91.1%
  - Level 2: 74.5%
  - Level 3: 62.5%

---

## Citation

If you use Spartan in your research, please cite our paper:

```bibtex
@inproceedings{299699,
  author = {Gelei Deng and Yi Liu and Víctor Mayoral-Vilches and Peng Liu and Yuekang Li and Yuan Xu and Tianwei Zhang and Yang Liu and Martin Pinzger and Stefan Rass},
  title = {{Spartan}: Evaluating and Harnessing Large Language Models for Automated Penetration Testing},
  booktitle = {33rd USENIX Security Symposium (USENIX Security 24)},
  year = {2024},
  isbn = {978-1-939133-44-1},
  address = {Philadelphia, PA},
  pages = {847--864},
  url = {https://www.usenix.org/conference/usenixsecurity24/presentation/deng},
  publisher = {USENIX Association},
  month = aug
}
```

---

## License

Distributed under the MIT License. See `LICENSE.md` for more information.

**Disclaimer**: This tool is for educational purposes and authorized security testing only. The authors do not condone any illegal use. Use at your own risk.

---

## Acknowledgments

- Research supported by [Quantstamp](https://www.quantstamp.com/) and [NTU Singapore](https://www.ntu.edu.sg/)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/GreyDGL/Spartan.svg?style=for-the-badge
[contributors-url]: https://github.com/GreyDGL/Spartan/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/GreyDGL/Spartan.svg?style=for-the-badge
[forks-url]: https://github.com/GreyDGL/Spartan/network/members
[stars-shield]: https://img.shields.io/github/stars/GreyDGL/Spartan.svg?style=for-the-badge
[stars-url]: https://github.com/GreyDGL/Spartan/stargazers
[issues-shield]: https://img.shields.io/github/issues/GreyDGL/Spartan.svg?style=for-the-badge
[issues-url]: https://github.com/GreyDGL/Spartan/issues
[license-shield]: https://img.shields.io/github/license/GreyDGL/Spartan.svg?style=for-the-badge
[license-url]: https://github.com/GreyDGL/Spartan/blob/master/LICENSE.md
[linkedin-shield]: https://img.shields.io/badge/-LinkedIn-black.svg?style=for-the-badge&logo=linkedin&colorB=555
[linkedin-url]: https://www.linkedin.com/in/gelei-deng-225a10112/
[linkedin-url2]: https://www.linkedin.com/in/vmayoral/
[discord-shield]: https://dcbadge.vercel.app/api/server/eC34CEfEkK
[discord-url]: https://discord.gg/eC34CEfEkK
