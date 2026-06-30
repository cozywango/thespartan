#!/usr/bin/env python3
"""Main CLI entry point for Spartan (Ornith 1.0 backend)."""

import argparse
import asyncio
import sys


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="spartan",
        description="Spartan - AI-Powered Penetration Testing Agent (Ornith 1.0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # HTB machine
  spartan --target 10.10.11.234

  # Web challenge
  spartan --target https://ctf.example.com/challenge1

  # With challenge context/hints
  spartan --target 10.10.11.100 --instruction "Wordpress site, focus on plugin vulnerabilities"

  # Pentest mode (BFS vuln identification)
  spartan --target 10.10.11.50 --mode pentest

  # Passive mode (Non-intrusive asset mapping and vulnerability inference)
  spartan --target example.com --mode passive

  # Custom Ollama model
  spartan --target 10.10.11.50 --model ornith:1.0-q8

  # Custom endpoint
  spartan --target 10.10.11.50 --api-base http://192.168.1.10:11434/v1

For more information: https://github.com/GreyDGL/spartan
        """,
    )

    parser.add_argument(
        "-t",
        "--target",
        type=str,
        required=True,
        help="Target CTF challenge or machine (URL, IP address, domain, or file path)",
    )

    parser.add_argument(
        "-i",
        "--instruction",
        type=str,
        help="Custom challenge context, hints, or instructions",
    )

    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default="ornith:1.0",
        help="Ollama model tag (default: ornith:1.0)",
    )

    parser.add_argument(
        "--api-base",
        type=str,
        default="http://localhost:11434/v1",
        help="OpenAI-compatible API base URL (default: local Ollama)",
    )

    parser.add_argument(
        "--mode",
        type=str,
        choices=["ctf", "pentest", "passive"],
        default="ctf",
        help="Pipeline mode: 'ctf' (DFS exploitation), 'pentest' (BFS vuln identification), or 'passive' (non-intrusive inference)",
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=300,
        help="Maximum agent iterations (default: 300)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug mode with detailed logging",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    # Session management
    parser.add_argument(
        "-r",
        "--resume",
        action="store_true",
        help="Resume the most recent session for the target",
    )

    parser.add_argument(
        "--session-id",
        type=str,
        help="Resume a specific session by ID",
    )

    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="List available sessions and exit",
    )

    # Telemetry
    parser.add_argument(
        "--no-telemetry",
        action="store_true",
        help="Disable anonymous telemetry data collection",
    )

    return parser.parse_args()


def print_banner() -> None:
    """Print welcome banner."""
    print()
    print("Spartan v1.0.0")
    print("AI-Powered Penetration Testing Agent — Ornith 1.0")
    print()


async def run_raw_mode(args: argparse.Namespace) -> None:
    """Run in raw CLI mode with streaming output."""
    from spartan.core.config import load_config
    from spartan.core.events import Event, EventBus, EventType
    from spartan.core.pipeline import PipelineMode, PipelineOrchestrator
    from spartan.core.pipelines import get_stages

    # Print startup info
    print(f"[INFO] Target: {args.target}")
    print(f"[INFO] Mode: {args.mode}")
    print(f"[INFO] Model: {args.model}")
    print(f"[INFO] Endpoint: {args.api_base}")
    if args.instruction:
        print(f"[INFO] Instruction: {args.instruction}")
    if args.debug:
        print("[INFO] Debug mode: enabled")
        import logging

        logging.basicConfig(level=logging.DEBUG)
    print("[INFO] Starting pipeline...", flush=True)

    # Set up event handlers that print directly to stdout
    events = EventBus.get()

    def on_message(event: Event) -> None:
        text = event.data.get("text", "")
        msg_type = event.data.get("type", "info")
        if text:
            print(f"[{msg_type.upper()}] {text}", flush=True)

    def on_tool(event: Event) -> None:
        status = event.data.get("status")
        name = event.data.get("name", "unknown")
        if status == "start":
            args_data = event.data.get("args", {})
            print(f"[TOOL] {name}: {args_data}", flush=True)
        else:
            print(f"[TOOL] {name} done", flush=True)

    def on_flag(event: Event) -> None:
        flag = event.data.get("flag", "")
        if flag:
            print(f"[FLAG] {flag}", flush=True)

    def on_state(event: Event) -> None:
        state = event.data.get("state", "")
        details = event.data.get("details", "")
        if details:
            print(f"[STATE] {state}: {details}", flush=True)
        else:
            print(f"[STATE] {state}", flush=True)

    events.subscribe(EventType.MESSAGE, on_message)
    events.subscribe(EventType.TOOL, on_tool)
    events.subscribe(EventType.FLAG_FOUND, on_flag)
    events.subscribe(EventType.STATE_CHANGED, on_state)

    # Build config
    config_kwargs: dict[str, str | int] = {
        "target": args.target,
        "mode": args.mode,
        "llm_model": args.model,
        "llm_api_base": args.api_base,
    }
    if args.instruction:
        config_kwargs["custom_instruction"] = args.instruction
    if args.max_iterations:
        config_kwargs["max_iterations"] = args.max_iterations

    config = load_config(**config_kwargs)

    # Set up pipeline
    pipeline_mode = PipelineMode(args.mode)
    stages = get_stages(pipeline_mode)

    orchestrator = PipelineOrchestrator(
        config=config,
        stages=stages,
        mode=pipeline_mode,
    )

    try:
        pipeline_result = await orchestrator.run()

        # Print final result
        flags = pipeline_result.all_flags
        cost = pipeline_result.total_cost
        session_id = (
            pipeline_result.stage_results[-1].session_id if pipeline_result.stage_results else ""
        )
        print(
            f"[DONE] Flags: {len(flags)}, Cost: ${cost:.4f}, Session: {session_id}",
            flush=True,
        )

        # Save the final report to a Markdown file
        if pipeline_result.stage_results:
            final_stage = pipeline_result.stage_results[-1]
            if final_stage.output:
                import re
                safe_target = re.sub(r'[^a-zA-Z0-9]+', '_', args.target).strip('_')
                report_filename = f"pentest_report_{safe_target}.md"
                try:
                    with open(report_filename, "w", encoding="utf-8") as f:
                        f.write(final_stage.output)
                    print(f"[INFO] Report successfully saved to {report_filename}", flush=True)
                except Exception as e:
                    print(f"[WARN] Failed to save report to {report_filename}: {e}", flush=True)
        if not flags and args.mode == "ctf":
            print("[WARN] No flags captured", flush=True)
            sys.exit(1)
        if not pipeline_result.success:
            print("[WARN] Pipeline completed with errors", flush=True)
            sys.exit(1)

    except Exception as e:
        print(f"[ERROR] {e!s}", flush=True)
        import traceback

        print(f"[TRACE] {traceback.format_exc()}", flush=True)
        sys.exit(1)


def list_sessions(target: str | None = None) -> None:
    """List available sessions."""
    from spartan.core.session import SessionStore

    sessions = SessionStore()
    session_list = sessions.list_sessions(target)

    if not session_list:
        print("No sessions found.")
        return

    print(f"Sessions{f' for {target}' if target else ''}:\n")
    print(f"{'ID':<10} {'Date':<18} {'Target':<25} {'Status':<12} {'Flags':<6}")
    print("-" * 75)

    for s in session_list:
        date_str = s.created_at.strftime("%Y-%m-%d %H:%M")
        target_str = s.target[:23] + ".." if len(s.target) > 25 else s.target
        flags_count = len(s.flags_found)
        print(
            f"{s.session_id:<10} {date_str:<18} {target_str:<25} {s.status.value:<12} {flags_count:<6}"
        )


def main() -> None:
    """Main entry point."""
    args = parse_arguments()

    # Handle --list-sessions
    if args.list_sessions:
        list_sessions(args.target if hasattr(args, "target") else None)
        return

    # Initialize telemetry (enabled by default, use --no-telemetry to disable)
    from spartan.core.langfuse import init_langfuse, shutdown_langfuse

    init_langfuse(disabled=args.no_telemetry)

    print_banner()

    try:
        asyncio.run(run_raw_mode(args))
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        shutdown_langfuse()


if __name__ == "__main__":
    main()
