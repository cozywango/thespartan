"""CLI entry point for the modernized legacy Spartan (Ornith 1.0 only).

spartan-legacy                              # interactive session
spartan-legacy --model ornith:1.0-q8        # alternative quant
spartan-legacy --base-url http://host:11434/v1  # remote Ollama
"""

from __future__ import annotations

import argparse
import sys

from spartan_legacy._version import __version__


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spartan-legacy",
        description="Spartan (modernized legacy) — interactive pentest assistant powered by Ornith 1.0.",
    )
    parser.add_argument(
        "--reasoning-model",
        type=str,
        default="ollama:ornith",
        help="Model for reasoning / the Pentesting Task Tree (default: ollama:ornith).",
    )
    parser.add_argument(
        "--parsing-model",
        type=str,
        default="ollama:ornith",
        help="Model for summarizing tool/web output (default: ollama:ornith).",
    )
    parser.add_argument(
        "--generation-model",
        type=str,
        default=None,
        help="Model for expanding tasks into steps (defaults to reasoning model).",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:11434/v1",
        help="Ollama API base URL (default: http://localhost:11434/v1).",
    )
    parser.add_argument("--log-dir", type=str, default="logs", help="Directory for logs.")
    parser.add_argument(
        "--list-models", action="store_true", help="List all supported models and exit."
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Make a real API call to every configured model and report a matrix.",
    )
    parser.add_argument(
        "--model", type=str, default=None, help="Restrict --smoke-test to a single model id."
    )
    parser.add_argument("--version", action="version", version=f"spartan-legacy {__version__}")
    return parser


def display_models() -> None:
    """Render the supported-model registry."""
    from spartan_legacy.llm.registry import PROVIDERS, models_by_provider

    print(f"\nSpartan (modernized legacy) v{__version__} — supported models\n")
    for provider_key, specs in models_by_provider().items():
        info = PROVIDERS[provider_key]
        print(f"== {info.label} ==")
        for spec in specs:
            flag = spec.tier
            ctx = f"{spec.context_window // 1000}K ctx"
            note = f" — {spec.notes}" if spec.notes else ""
            print(f"   {spec.id:<32} [{flag:<8}] {ctx}{note}")
        print()
    print("Usage: pass 'ollama:<model>' (e.g. ollama:ornith) with --base-url if needed.\n")


def run_interactive(args: argparse.Namespace) -> None:
    reasoning_model = args.reasoning_model
    parsing_model = args.parsing_model

    # Apply base-url override into environment for the Ollama provider.
    import os

    os.environ["OLLAMA_BASE_URL"] = args.base_url

    # Imported lazily so --list-models / --smoke-test don't require prompt_toolkit/rich.
    from spartan_legacy.utils.spartan import Spartan

    try:
        session = Spartan(
            log_dir=args.log_dir,
            reasoning_model=reasoning_model,
            parsing_model=parsing_model,
            generation_model=args.generation_model,
        )
        session.main()
    except Exception as e:
        print(f"Spartan execution failed: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    args = _create_parser().parse_args()

    if args.list_models:
        display_models()
        return

    if args.smoke_test:
        from spartan_legacy.smoke_test import run_smoke_test

        sys.exit(run_smoke_test(provider="ollama", model=args.model))

    run_interactive(args)


if __name__ == "__main__":
    main()
