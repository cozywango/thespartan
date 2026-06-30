"""Native tool-execution sandbox for local LLM function calling.

Replaces the implicit tool execution that Claude Code CLI provided. Runs bash
commands via ``asyncio.create_subprocess_shell``, captures stdout, stderr, and
the exit code, and returns structured results suitable for injection into the
LLM conversation as tool-call responses.

Security note: This sandbox is designed for *authorized* penetration testing
inside an isolated environment (Docker container, VM, lab network). It does
**not** restrict which commands can be run — that is intentional for pentest
workflows.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Maximum combined stdout+stderr returned to the model (characters).
_MAX_OUTPUT_CHARS = 80_000

# Default per-command timeout (seconds).
_DEFAULT_TIMEOUT = 120

# ── OpenAI-compatible function-calling schema ────────────────────────────────

TOOL_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": (
                "Execute a bash command on the local penetration-testing system. "
                "Use this to run security tools (nmap, gobuster, sqlmap …), read "
                "files, write exploit scripts, and interact with the target. "
                "Commands run in a real shell with full privileges."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": (
                            "Maximum execution time in seconds. "
                            f"Defaults to {_DEFAULT_TIMEOUT}."
                        ),
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write content to a file on disk. Use this to create exploit "
                "scripts, configuration files, or any other file needed for "
                "the penetration test."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative file path to write.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to write to the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
]


@dataclass
class CommandResult:
    """Structured result of a single command execution."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    error: str | None = None

    def to_tool_response(self) -> str:
        """Serialize to a string suitable for an LLM tool-response message."""
        parts: list[str] = []
        if self.timed_out:
            parts.append(f"[TIMEOUT after {_DEFAULT_TIMEOUT}s]")
        if self.error:
            parts.append(f"[ERROR] {self.error}")
        if self.stdout:
            parts.append(f"STDOUT:\n{self.stdout}")
        if self.stderr:
            parts.append(f"STDERR:\n{self.stderr}")
        parts.append(f"EXIT_CODE: {self.exit_code}")
        combined = "\n".join(parts)
        # Truncate to keep the context window manageable.
        if len(combined) > _MAX_OUTPUT_CHARS:
            combined = combined[: _MAX_OUTPUT_CHARS] + "\n... [output truncated]"
        return combined


@dataclass
class ToolDispatcher:
    """Dispatches LLM tool calls to local execution handlers.

    Attributes:
        working_directory: CWD for all subprocess invocations.
        default_timeout: Fallback timeout if the model doesn't specify one.
        command_history: Running log of every command executed (for auditing).
    """

    working_directory: str = "."
    default_timeout: int = _DEFAULT_TIMEOUT
    command_history: list[CommandResult] = field(default_factory=list)

    # ── Public API ───────────────────────────────────────────────────────

    async def dispatch(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Route a tool call to the appropriate handler.

        Args:
            tool_name: Function name from the LLM's tool_call.
            arguments: Parsed JSON arguments from the tool_call.

        Returns:
            A string to be sent back as the tool-response content.
        """
        if tool_name == "execute_command":
            return await self._handle_execute_command(arguments)
        if tool_name == "write_file":
            return self._handle_write_file(arguments)
        return f"[ERROR] Unknown tool '{tool_name}'. Available tools: execute_command, write_file."

    # ── Handlers ─────────────────────────────────────────────────────────

    async def _handle_execute_command(self, args: dict[str, Any]) -> str:
        command = args.get("command", "")
        if not command or not isinstance(command, str):
            return "[ERROR] 'command' argument is required and must be a non-empty string."
        timeout = int(args.get("timeout", self.default_timeout))
        result = await self.run_command(command, timeout=timeout)
        self.command_history.append(result)
        return result.to_tool_response()

    def _handle_write_file(self, args: dict[str, Any]) -> str:
        path = args.get("path", "")
        content = args.get("content", "")
        if not path:
            return "[ERROR] 'path' argument is required."
        try:
            full_path = os.path.join(self.working_directory, path) if not os.path.isabs(path) else path
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)
            return f"[OK] Wrote {len(content)} bytes to {full_path}"
        except Exception as exc:
            return f"[ERROR] Failed to write file '{path}': {exc}"

    # ── Subprocess runner ────────────────────────────────────────────────

    async def run_command(self, command: str, *, timeout: int | None = None) -> CommandResult:
        """Execute a shell command asynchronously.

        Args:
            command: Bash command string.
            timeout: Per-command timeout in seconds (falls back to default).

        Returns:
            A :class:`CommandResult` with captured output.
        """
        effective_timeout = timeout if timeout is not None else self.default_timeout
        logger.info("sandbox exec [timeout=%ds]: %s", effective_timeout, command[:200])

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_directory,
                env=self._build_env(),
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=effective_timeout,
                )
                return CommandResult(
                    command=command,
                    exit_code=process.returncode or 0,
                    stdout=stdout_bytes.decode("utf-8", errors="replace"),
                    stderr=stderr_bytes.decode("utf-8", errors="replace"),
                )
            except TimeoutError:
                # Kill the process tree on timeout.
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                return CommandResult(
                    command=command,
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    timed_out=True,
                    error=f"Command timed out after {effective_timeout}s",
                )

        except Exception as exc:
            logger.error("sandbox error: %s", exc, exc_info=True)
            return CommandResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr="",
                error=str(exc),
            )

    @staticmethod
    def _build_env() -> dict[str, str]:
        """Build sanitized environment for subprocesses."""
        env = dict(os.environ)
        # Ensure non-interactive tools behave well.
        env["TERM"] = env.get("TERM", "xterm-256color")
        env["PYTHONUNBUFFERED"] = "1"
        return env


def parse_tool_arguments(raw: str | dict[str, Any]) -> dict[str, Any]:
    """Best-effort parse of tool-call arguments from the LLM.

    Local models sometimes emit slightly malformed JSON. This helper tries
    ``json.loads`` first, then falls back to heuristic extraction so the
    agent can continue rather than crash on a single bad response.

    Args:
        raw: Either a dict (already parsed) or a JSON string.

    Returns:
        Parsed argument dict, or a dict with an ``_parse_error`` key.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        # Strip markdown code fences that some models wrap around JSON.
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()
        try:
            result = json.loads(cleaned)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
        # Heuristic: try to extract a command string from free-form text.
        return {"_parse_error": f"Could not parse tool arguments: {raw[:500]}"}
    return {"_parse_error": f"Unexpected argument type: {type(raw).__name__}"}
