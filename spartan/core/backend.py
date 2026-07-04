"""Framework-agnostic agent backend protocol and Ornith 1.0 implementation.

The ``OrnithBackend`` talks to a local Ollama instance (or any OpenAI-compatible
endpoint) running the **Ornith 1.0** model. It replaces the former
``ClaudeCodeBackend`` which shelled out to the proprietary ``claude`` CLI.

Tool execution is handled by the :mod:`spartan.core.sandbox` module —
the model issues ``tool_calls`` via the standard OpenAI function-calling
protocol, we execute them locally, and feed the results back into the
conversation.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from spartan.core.sandbox import (
    TOOL_SCHEMA,
    ToolDispatcher,
    parse_tool_arguments,
)

logger = logging.getLogger(__name__)

# ── Default endpoint & model ────────────────────────────────────────────────
_DEFAULT_BASE_URL = "http://localhost:11434/v1"
_DEFAULT_MODEL = "ornith:1.0"
_MAX_RETRIES_ON_BAD_JSON = 3
_MAX_TOOL_ROUNDS = 50  # safety valve: stop after N tool-call round-trips

# Signals that MUST appear in the conversation history (message content joined)
# before a Stage 1 complete_stage call is honoured.
_REQUIRED_RECON_SIGNALS: tuple[str, ...] = ("-p-", "-sV", "-sC")


class MessageType(Enum):
    """Framework-agnostic message types from agent backends."""

    TEXT = "text"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    RESULT = "result"
    ERROR = "error"


@dataclass
class AgentMessage:
    """Framework-agnostic message from any agent backend."""

    type: MessageType
    content: Any
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentBackend(ABC):
    """
    Abstract interface for agent backends.

    Implement this to support different LLM providers:
    - OrnithBackend (current — local Ollama)
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the agent."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""
        ...

    @abstractmethod
    async def query(self, prompt: str) -> None:
        """Send a query/instruction to the agent."""
        ...

    @abstractmethod
    def receive_messages(self) -> AsyncIterator[AgentMessage]:
        """Async iterator yielding messages from agent."""
        ...

    @property
    @abstractmethod
    def session_id(self) -> str | None:
        """Current session ID (if backend supports sessions)."""
        ...

    @property
    def supports_resume(self) -> bool:
        """Whether this backend supports session resume."""
        return False

    @abstractmethod
    async def resume(self, session_id: str) -> bool:
        """Resume a previous session. Returns success."""
        ...


class OrnithBackend(AgentBackend):
    """Ornith 1.0 backend via an OpenAI-compatible local endpoint (Ollama).

    Implements a full tool-calling loop:
    1. Send the user prompt + tool schemas to the model.
    2. If the model responds with ``tool_calls``, execute each via
       :class:`~spartan.core.sandbox.ToolDispatcher`.
    3. Inject tool results back into the conversation and re-query.
    4. Repeat until the model emits a final text response (no tool calls).

    Messages are streamed to the controller through an ``asyncio.Queue``
    exposed via :meth:`receive_messages`.
    """

    def __init__(
        self,
        working_directory: str,
        system_prompt: str,
        model: str = _DEFAULT_MODEL,
        base_url: str = _DEFAULT_BASE_URL,
        audit_log_path: str = "/workspace/raw_execution_audit.log",
        enforce_recon_gate: bool = False,
    ):
        self._cwd = working_directory
        self._system_prompt = system_prompt
        self._model = model
        self._base_url = base_url
        self._audit_log_path = audit_log_path
        # When True, validate required recon scans before honouring complete_stage.
        self._enforce_recon_gate = enforce_recon_gate

        # Conversation state
        self._messages: list[dict[str, Any]] = []
        self._queue: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._session_id: str | None = None
        self._client: Any | None = None  # AsyncOpenAI instance
        self._dispatcher: ToolDispatcher | None = None
        self._task: asyncio.Task[None] | None = None
        # Harvested by PipelineOrchestrator after stage completion.
        self.stage_comprehensive_report: str = ""

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Initialize the HTTP client and tool dispatcher."""
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The 'openai' package is required for OrnithBackend. "
                "Install with: uv add openai"
            ) from exc

        self._client = AsyncOpenAI(
            api_key="not-needed",  # Ollama ignores the key
            base_url=self._base_url,
        )
        self._dispatcher = ToolDispatcher(
            working_directory=self._cwd,
            audit_log_path=self._audit_log_path,
        )

        # Seed the conversation with the system prompt.
        self._messages = [{"role": "system", "content": self._system_prompt}]
        self._session_id = f"ornith-{id(self)}"
        logger.info(
            "OrnithBackend connected: model=%s endpoint=%s",
            self._model,
            self._base_url,
        )

    async def disconnect(self) -> None:
        """Cancel any running task and close the client."""
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._client:
            await self._client.close()
            self._client = None

    # ── Query & message loop ─────────────────────────────────────────────

    async def query(self, prompt: str) -> None:
        """Append the user prompt and kick off the tool-calling loop."""
        self._messages.append({"role": "user", "content": prompt})
        # Launch the conversation loop in a background task so
        # receive_messages() can yield events as they arrive.
        self._task = asyncio.create_task(self._conversation_loop())

    async def receive_messages(self) -> AsyncIterator[AgentMessage]:
        """Yield messages produced by the background conversation loop."""
        while True:
            msg = await self._queue.get()
            if msg.type == MessageType.RESULT:
                yield msg
                return  # Sentinel — conversation is done.
            yield msg

    # ── Core loop ────────────────────────────────────────────────────────

    async def _conversation_loop(self) -> None:
        """Run the tool-calling loop until the model gives a final answer."""
        if not self._client:
            await self._queue.put(
                AgentMessage(type=MessageType.ERROR, content="Backend not connected")
            )
            return

        rounds = 0
        try:
            while rounds < _MAX_TOOL_ROUNDS:
                rounds += 1
                response = await self._chat_completion()
                if response is None:
                    break

                choice = response.choices[0]
                message = choice.message

                # Intercept hallucinated tool calls if the model failed to format them as JSON
                if not message.tool_calls and message.content and "Tool Call:" in message.content:
                    import re
                    import uuid
                    from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall, Function
                    
                    pattern = r"Tool Call:\s*(\w+)\s*\|\s*Args:\s*({.+?})(?=\n|$)"
                    matches = list(re.finditer(pattern, message.content))
                    
                    if matches:
                        message.tool_calls = []
                        for match in matches:
                            func = Function(name=match.group(1), arguments=match.group(2))
                            call = ChatCompletionMessageToolCall(
                                id=f"call_{uuid.uuid4().hex[:8]}", 
                                type="function", 
                                function=func
                            )
                            message.tool_calls.append(call)
                        
                        # Remove the hallucinated text so it isn't appended to the final response
                        message.content = re.sub(pattern, "", message.content).strip()

                # ── Final text answer (no tool calls) ────────────────
                if not message.tool_calls:
                    text = message.content or ""
                    if text:
                        self._messages.append({"role": "assistant", "content": text})
                        await self._queue.put(
                            AgentMessage(type=MessageType.TEXT, content=text)
                        )
                    break

                # ── Tool calls to execute ────────────────────────────
                # Record the full assistant message (without tool_calls array to avoid Jinja/OpenAI validation errors).
                assistant_content = message.content or ""
                if message.tool_calls:
                    calls_desc = "\n".join([f"Tool Call: {tc.function.name} | Args: {tc.function.arguments}" for tc in message.tool_calls])
                    assistant_content = f"{assistant_content}\n\n{calls_desc}".strip()
                    
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": assistant_content,
                }
                self._messages.append(assistant_msg)
                
                if assistant_content:
                    await self._queue.put(
                        AgentMessage(type=MessageType.TEXT, content=assistant_content)
                    )

                tool_results_combined = []

                for tc in message.tool_calls:
                    tool_name = tc.function.name
                    raw_args = tc.function.arguments

                    # ── complete_stage interception ───────────────────────
                    if tool_name == "complete_stage":
                        parsed_cs = parse_tool_arguments(raw_args)
                        if "_parse_error" not in parsed_cs:
                            # Validate recon gate if enabled.
                            if self._enforce_recon_gate:
                                missing = self._check_recon_gate()
                                if missing:
                                    gate_msg = (
                                        "[SYSTEM] Cannot complete stage. "
                                        "Required comprehensive scans have not been executed. "
                                        f"Missing signals in history: {', '.join(missing)}. "
                                        "You must run: (1) nmap -p- all-ports TCP scan, "
                                        "(2) nmap -sU --top-ports 1000 UDP scan, and "
                                        "(3) nmap -sV -sC deep service enumeration "
                                        "before calling complete_stage."
                                    )
                                    logger.warning(
                                        "complete_stage BLOCKED — missing recon signals: %s",
                                        missing,
                                    )
                                    self._messages.append(
                                        {"role": "user", "content": gate_msg}
                                    )
                                    await self._queue.put(
                                        AgentMessage(
                                            type=MessageType.TEXT,
                                            content=gate_msg,
                                        )
                                    )
                                    # Do NOT break — let the loop continue so the
                                    # model has a chance to run the missing scans.
                                    continue

                            # Gate passed (or not enforced): harvest the report.
                            self.stage_comprehensive_report = parsed_cs.get(
                                "stage_comprehensive_report", ""
                            )
                            logger.info(
                                "complete_stage accepted — report length=%d chars",
                                len(self.stage_comprehensive_report),
                            )
                            # Signal conversation end via RESULT sentinel.
                            await self._queue.put(
                                AgentMessage(
                                    type=MessageType.RESULT,
                                    content=None,
                                    metadata={
                                        "session_id": self._session_id,
                                        "cost_usd": 0,
                                        "stage_comprehensive_report": self.stage_comprehensive_report,
                                    },
                                )
                            )
                            return

                    # ── All other tool calls ──────────────────────────────

                    # Emit TOOL_START event
                    await self._queue.put(
                        AgentMessage(
                            type=MessageType.TOOL_START,
                            content=None,
                            tool_name=tool_name,
                            tool_args={"raw": raw_args},
                        )
                    )

                    # Parse arguments (with resilience to malformed JSON).
                    parsed = parse_tool_arguments(raw_args)
                    if "_parse_error" in parsed:
                        # Ask the model to fix its output.
                        tool_result = await self._retry_malformed_args(
                            tc.id, tool_name, raw_args
                        )
                    else:
                        assert self._dispatcher is not None, "Dispatcher not initialized"
                        tool_result = await self._dispatcher.dispatch(tool_name, parsed)

                    # Truncate tool result to prevent context window exhaustion (4096 limit on some local models)
                    max_chars = 1000
                    if len(tool_result) > max_chars:
                        tool_result = tool_result[:max_chars] + f"\n... [TRUNCATED {len(tool_result)-max_chars} chars]"

                    tool_results_combined.append(f"--- Result from {tool_name} ---\n{tool_result}")

                    # Emit TOOL_RESULT event
                    await self._queue.put(
                        AgentMessage(
                            type=MessageType.TOOL_RESULT,
                            content=tool_result,
                            tool_name=tool_name,
                        )
                    )

                # Record the tool result in conversation history as a user message.
                if tool_results_combined:
                    self._messages.append(
                        {
                            "role": "user",
                            "content": "\n\n".join(tool_results_combined),
                        }
                    )

            # ── Conversation finished — emit sentinel ────────────────
            await self._queue.put(
                AgentMessage(
                    type=MessageType.RESULT,
                    content=None,
                    metadata={"session_id": self._session_id, "cost_usd": 0},
                )
            )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("OrnithBackend conversation error: %s", exc, exc_info=True)
            await self._queue.put(
                AgentMessage(type=MessageType.ERROR, content=str(exc))
            )
            await self._queue.put(
                AgentMessage(
                    type=MessageType.RESULT,
                    content=None,
                    metadata={"session_id": self._session_id, "cost_usd": 0},
                )
            )

    # ── API call ─────────────────────────────────────────────────────────

    async def _chat_completion(self) -> Any:
        """Send the current conversation to the Ornith model."""
        try:
            assert self._client is not None, "Client not initialized"
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=self._messages,
                tools=TOOL_SCHEMA,
                tool_choice="auto",
                max_tokens=4096,
                extra_body={"options": {"num_ctx": 32768}},
            )
            return response
        except Exception as exc:
            logger.error("Chat completion failed: %s", exc, exc_info=True)
            await self._queue.put(
                AgentMessage(
                    type=MessageType.TEXT,
                    content=f"[BACKEND ERROR] LLM request failed: {exc}",
                )
            )
            return None

    # ── Retry logic for malformed tool args ───────────────────────────────

    async def _retry_malformed_args(
        self, tool_call_id: str, tool_name: str, raw_args: str
    ) -> str:
        """Prompt the model to fix malformed tool-call JSON.

        Gives the model up to ``_MAX_RETRIES_ON_BAD_JSON`` attempts to emit
        valid JSON for the tool call. If all retries fail, returns an error
        string that gets injected as the tool response.
        """
        for attempt in range(1, _MAX_RETRIES_ON_BAD_JSON + 1):
            logger.warning(
                "Malformed tool args (attempt %d/%d): %s",
                attempt,
                _MAX_RETRIES_ON_BAD_JSON,
                raw_args[:300],
            )
            # Inject a corrective tool-response asking the model to fix it.
            correction = (
                f"[SYSTEM] Your previous tool call to '{tool_name}' had malformed "
                f"JSON arguments. The raw text was:\n\n{raw_args[:500]}\n\n"
                "Please re-issue the tool call with valid JSON matching the schema."
            )
            self._messages.append(
                {"role": "user", "content": correction}
            )

            response = await self._chat_completion()
            if response is None:
                break

            choice = response.choices[0]
            message = choice.message

            if message.tool_calls:
                for tc in message.tool_calls:
                    if tc.function.name == tool_name:
                        parsed = parse_tool_arguments(tc.function.arguments)
                        if "_parse_error" not in parsed:
                            # Success — record the corrected assistant msg and
                            # execute the tool.
                            corrected_msg: dict[str, Any] = {
                                "role": "assistant",
                                "content": (message.content or "") + f"\n\nTool Call: {tc.function.name} | Args: {tc.function.arguments}",
                            }
                            self._messages.append(corrected_msg)
                            assert self._dispatcher is not None, "Dispatcher not initialized"
                            result = await self._dispatcher.dispatch(tool_name, parsed)
                            return result
                        raw_args = tc.function.arguments  # update for next retry

        return (
            f"[ERROR] Failed to parse tool arguments after "
            f"{_MAX_RETRIES_ON_BAD_JSON} retries. Raw: {raw_args[:300]}"
        )

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def supports_resume(self) -> bool:
        return False

    async def resume(self, session_id: str) -> bool:
        return False

    # ── Recon gate ───────────────────────────────────────────────────────

    def _check_recon_gate(self) -> list[str]:
        """Check whether required recon signals appear in the message history.

        Scans all non-system message content for the presence of each string
        in ``_REQUIRED_RECON_SIGNALS``.

        Returns:
            A list of missing signal strings. Empty list means gate is passed.
        """
        # Concatenate all message content (skip system prompt) for pattern search.
        history_text = " ".join(
            str(msg.get("content", ""))
            for msg in self._messages
            if msg.get("role") != "system"
        )
        return [sig for sig in _REQUIRED_RECON_SIGNALS if sig not in history_text]
