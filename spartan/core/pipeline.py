"""Pipeline orchestrator for multi-stage penetration testing."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from spartan.core.config import SpartanConfig
from spartan.core.events import EventBus
from spartan.core.session import SessionStore

if TYPE_CHECKING:
    from spartan.core.controller import AgentController

logger = logging.getLogger(__name__)


class PipelineMode(Enum):
    """Pipeline execution modes."""

    CTF = "ctf"
    PENTEST = "pentest"
    PASSIVE = "passive"


@dataclass
class StageDefinition:
    """Definition of a single pipeline stage.

    Attributes:
        name: Machine-readable name (e.g. "asset_identification").
        display_name: Human-readable name (e.g. "Asset Identification").
        get_system_prompt: Callable returning the system prompt for this stage.
        get_task_prompt: Callable returning the task prompt, given prior results.
    """

    name: str
    display_name: str
    get_system_prompt: Callable[[SpartanConfig], str]
    get_task_prompt: Callable[[SpartanConfig, list[StageResult]], str]


@dataclass
class StageResult:
    """Result from a single pipeline stage.

    Attributes:
        stage_name: Machine name of the stage.
        display_name: Human-readable stage name.
        status: Outcome status ("completed", "error", "stopped").
        output: Combined text output from the stage.
        flags_found: List of flag strings detected.
        cost_usd: Cost in USD for this stage.
        error: Error message if the stage failed.
        session_id: Session ID used for this stage.
        report_path: Filesystem path where the stage report was saved (if any).
    """

    stage_name: str
    display_name: str
    status: str = "completed"
    output: str = ""
    flags_found: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    error: str | None = None
    session_id: str = ""
    report_path: str = ""


@dataclass
class PipelineResult:
    """Aggregate result from the full pipeline.

    Attributes:
        mode: The pipeline mode that was executed.
        stage_results: Ordered list of per-stage results.
    """

    mode: PipelineMode
    stage_results: list[StageResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True if all stages completed without error."""
        return all(r.status == "completed" for r in self.stage_results)

    @property
    def all_flags(self) -> list[str]:
        """Deduplicated flags from all stages."""
        seen: set[str] = set()
        flags: list[str] = []
        for r in self.stage_results:
            for f in r.flags_found:
                if f not in seen:
                    seen.add(f)
                    flags.append(f)
        return flags

    @property
    def total_cost(self) -> float:
        """Sum of costs across all stages."""
        return sum(r.cost_usd for r in self.stage_results)

    @property
    def combined_output(self) -> str:
        """Combined output from all stages with stage headers."""
        parts: list[str] = []
        for r in self.stage_results:
            parts.append(f"=== {r.display_name} ===")
            parts.append(r.output)
        return "\n\n".join(parts)


class PipelineOrchestrator:
    """Runs a sequence of stages, each with a fresh backend + controller.

    Each stage gets:
    - A fresh OrnithBackend with a stage-specific system prompt.
    - An AgentController for lifecycle management.
    - Context from all prior stages injected into the task prompt.
    """

    def __init__(
        self,
        config: SpartanConfig,
        stages: list[StageDefinition],
        mode: PipelineMode,
        session_store: SessionStore | None = None,
        events: EventBus | None = None,
    ) -> None:
        """Initialize the pipeline orchestrator.

        Args:
            config: Spartan configuration.
            stages: Ordered list of stage definitions.
            mode: Pipeline mode (CTF or Pentest).
            session_store: Optional session store override.
            events: Optional event bus override.
        """
        self.config = config
        self.stages = stages
        self.mode = mode
        self.session_store = session_store or SessionStore()
        self.events = events or EventBus.get()

        self._current_controller: AgentController | None = None
        self._stop_requested = False

    async def run(self) -> PipelineResult:
        """Execute all pipeline stages sequentially.

        Returns:
            PipelineResult with per-stage and aggregate results.
        """
        result = PipelineResult(mode=self.mode)
        self._stop_requested = False

        for i, stage_def in enumerate(self.stages):
            if self._stop_requested:
                logger.info("Pipeline stopped by user")
                break

            stage_num = i + 1
            total = len(self.stages)
            logger.info(f"Pipeline stage {stage_num}/{total}: {stage_def.display_name}")
            self.events.emit_message(
                f"[Stage {stage_num}/{total}] {stage_def.display_name}",
                "info",
            )

            # Collect intermediate report paths for the final reporting stage.
            intermediate_reports = self._load_intermediate_reports(result.stage_results)
            stage_result = await self._run_stage(
                stage_def, result.stage_results, intermediate_reports=intermediate_reports
            )
            result.stage_results.append(stage_result)

            if stage_result.status == "error":
                logger.error(f"Stage '{stage_def.display_name}' failed: {stage_result.error}")
                # Continue to next stage on error — downstream stages get partial context
                # but the pipeline doesn't abort entirely
                self.events.emit_message(
                    f"Stage '{stage_def.display_name}' had an error: {stage_result.error}",
                    "warning",
                )

        # Post-process: synthesize master report with audit log appendix.
        master_report_path = await self._synthesize_master_report(result)
        if master_report_path:
            self.events.emit_message(
                f"Master report written: {master_report_path}", "success"
            )

        # Emit final summary
        self.events.emit_message(
            f"Pipeline complete: {len(result.all_flags)} flag(s), ${result.total_cost:.4f}",
            "success" if result.success else "warning",
        )

        return result

    async def _run_stage(
        self,
        stage_def: StageDefinition,
        prior_results: list[StageResult],
        intermediate_reports: list[str] | None = None,
    ) -> StageResult:
        """Run a single pipeline stage with a fresh backend + controller.

        Args:
            stage_def: Stage definition with prompt builders.
            prior_results: Results from previously completed stages.
            intermediate_reports: Pre-read Markdown strings for stages that
                consume previous reports (e.g. the final reporting stage).

        Returns:
            StageResult for this stage.
        """
        from spartan.core.backend import OrnithBackend
        from spartan.core.controller import AgentController

        system_prompt = stage_def.get_system_prompt(self.config)

        # Some stages accept intermediate_reports as a keyword arg (e.g. final report).
        import inspect
        sig = inspect.signature(stage_def.get_task_prompt)
        if "intermediate_reports" in sig.parameters and intermediate_reports is not None:
            task_prompt = stage_def.get_task_prompt(
                self.config, prior_results, intermediate_reports=intermediate_reports
            )
        else:
            task_prompt = stage_def.get_task_prompt(self.config, prior_results)

        # Enforce the recon gate only on Stage 1 variants of pentest/ctf.
        enforce_gate = stage_def.name in ("asset_identification", "recon")
        audit_log = str(
            Path(str(self.config.working_directory)) / "raw_execution_audit.log"
        )

        backend = OrnithBackend(
            working_directory=str(self.config.working_directory),
            system_prompt=system_prompt,
            model=self.config.llm_model,
            base_url=self.config.llm_api_base or "http://localhost:11434/v1",
            audit_log_path=audit_log,
            enforce_recon_gate=enforce_gate,
        )

        controller = AgentController(
            config=self.config,
            backend=backend,
            session_store=self.session_store,
            events=self.events,
        )
        self._current_controller = controller

        try:
            result = await controller.run(task_prompt)

            # Harvest stage_comprehensive_report from backend.
            stage_report = backend.stage_comprehensive_report
            report_path = ""
            if stage_report:
                report_path = self._save_stage_report(stage_def, stage_report)

            if result.get("success"):
                return StageResult(
                    stage_name=stage_def.name,
                    display_name=stage_def.display_name,
                    status="completed",
                    output=result.get("output", ""),
                    flags_found=result.get("flags_found", []),
                    cost_usd=result.get("cost_usd", 0.0),
                    session_id=result.get("session_id", ""),
                    report_path=report_path,
                )
            else:
                return StageResult(
                    stage_name=stage_def.name,
                    display_name=stage_def.display_name,
                    status="error",
                    output=result.get("output", ""),
                    error=result.get("error", "Unknown error"),
                    cost_usd=result.get("cost_usd", 0.0),
                    session_id=result.get("session_id", ""),
                    report_path=report_path,
                )
        except Exception as e:
            logger.error(f"Stage '{stage_def.display_name}' raised: {e}", exc_info=True)
            return StageResult(
                stage_name=stage_def.name,
                display_name=stage_def.display_name,
                status="error",
                error=str(e),
            )
        finally:
            self._current_controller = None

    # === Stage report helpers ===

    def _save_stage_report(self, stage_def: StageDefinition, report_md: str) -> str:
        """Write a stage's comprehensive report to the workspace.

        Args:
            stage_def: The completed stage definition.
            report_md: Markdown report string from the LLM.

        Returns:
            Absolute path string where the report was saved.
        """
        workspace = Path(str(self.config.working_directory))
        # Use a stable, human-readable name keyed by stage name.
        filename = f"stage_{stage_def.name}_report.md"
        path = workspace / filename
        try:
            path.write_text(report_md, encoding="utf-8")
            logger.info("Stage report saved: %s", path)
            self.events.emit_message(f"Stage report saved: {filename}", "info")
        except OSError as exc:
            logger.warning("Failed to save stage report to %s: %s", path, exc)
        return str(path)

    def _load_intermediate_reports(self, stage_results: list[StageResult]) -> list[str]:
        """Read previously saved stage report files from disk.

        Args:
            stage_results: Completed stage results (with report_path populated).

        Returns:
            List of Markdown strings, one per report found on disk.
        """
        reports: list[str] = []
        for sr in stage_results:
            if not sr.report_path:
                continue
            p = Path(sr.report_path)
            if p.exists():
                try:
                    reports.append(p.read_text(encoding="utf-8"))
                except OSError as exc:
                    logger.warning("Cannot read intermediate report %s: %s", p, exc)
        return reports

    async def _synthesize_master_report(self, pipeline_result: PipelineResult) -> str:
        """Append the raw execution audit log to the final master report.

        Finds the most recently saved report whose stage name contains 'report'
        (or falls back to the last non-empty report) and appends the full
        audit log as an appendix.

        Args:
            pipeline_result: Completed PipelineResult.

        Returns:
            Absolute path string of the master report, or empty string if nothing
            was written.
        """
        workspace = Path(str(self.config.working_directory))
        audit_log_path = workspace / "raw_execution_audit.log"
        master_path = workspace / "master_report.md"

        # Find the best candidate for the master report content.
        report_content = ""
        for sr in reversed(pipeline_result.stage_results):
            if sr.report_path and Path(sr.report_path).exists():
                try:
                    report_content = Path(sr.report_path).read_text(encoding="utf-8")
                    break
                except OSError:
                    continue

        if not report_content:
            # Nothing to synthesize.
            return ""

        # Build the master document.
        parts: list[str] = [report_content, ""]

        if audit_log_path.exists():
            try:
                audit_text = audit_log_path.read_text(encoding="utf-8")
                parts.append("---")
                parts.append("")
                parts.append("## Appendix A — Raw Execution Audit Log")
                parts.append("")
                parts.append(
                    "_This appendix contains the complete, unabridged, append-only record "
                    "of every command executed during the engagement and its verbatim output. "
                    "It is generated automatically and is unmodified by the reporting stage._"
                )
                parts.append("")
                parts.append("```")
                parts.append(audit_text)
                parts.append("```")
            except OSError as exc:
                logger.warning("Cannot read audit log for master report: %s", exc)

        try:
            master_path.write_text("\n".join(parts), encoding="utf-8")
            logger.info("Master report written: %s", master_path)
        except OSError as exc:
            logger.warning("Failed to write master report: %s", exc)
            return ""

        return str(master_path)

    # === Forwarding control methods to the active stage's controller ===

    def pause(self) -> bool:
        """Forward pause to the currently-active stage controller."""
        if self._current_controller:
            return self._current_controller.pause()
        return False

    def resume(self, instruction: str | None = None) -> bool:
        """Forward resume to the currently-active stage controller."""
        if self._current_controller:
            return self._current_controller.resume(instruction)
        return False

    def stop(self) -> bool:
        """Request pipeline stop and forward to the active controller."""
        self._stop_requested = True
        if self._current_controller:
            return self._current_controller.stop()
        return True

    def inject(self, instruction: str) -> bool:
        """Forward instruction injection to the active controller."""
        if self._current_controller:
            return self._current_controller.inject(instruction)
        return False
