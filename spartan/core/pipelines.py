"""Factory module: assembles stage definitions for CTF and Pentest pipelines."""

from spartan.core.pipeline import PipelineMode, StageDefinition
from spartan.prompts import stages

# ── Final reporting stage (shared across all modes) ──────────────────────────
#
# The task prompt builder has an optional `intermediate_reports` kwarg that
# PipelineOrchestrator._run_stage() injects with pre-read Markdown strings
# from prior stage reports saved to disk.

_FINAL_REPORT_STAGE = StageDefinition(
    name="final_report",
    display_name="Final Master Report",
    get_system_prompt=stages.final_report_stage_system_prompt,
    get_task_prompt=stages.final_report_stage_task_prompt,  # type: ignore[arg-type]
)

CTF_STAGES: list[StageDefinition] = [
    StageDefinition(
        name="recon",
        display_name="Reconnaissance & Enumeration",
        get_system_prompt=stages.ctf_stage1_system_prompt,
        get_task_prompt=stages.ctf_stage1_task_prompt,
    ),
    StageDefinition(
        name="exploit",
        display_name="Exploitation (DFS)",
        get_system_prompt=stages.ctf_stage2_system_prompt,
        get_task_prompt=stages.ctf_stage2_task_prompt,
    ),
    StageDefinition(
        name="walkthrough",
        display_name="Walkthrough Generation",
        get_system_prompt=stages.ctf_stage3_system_prompt,
        get_task_prompt=stages.ctf_stage3_task_prompt,
    ),
    _FINAL_REPORT_STAGE,
]

PENTEST_STAGES: list[StageDefinition] = [
    StageDefinition(
        name="asset_identification",
        display_name="Asset Identification",
        get_system_prompt=stages.pentest_stage1_system_prompt,
        get_task_prompt=stages.pentest_stage1_task_prompt,
    ),
    StageDefinition(
        name="vulnerability_identification",
        display_name="Vulnerability Identification (BFS)",
        get_system_prompt=stages.pentest_stage2_system_prompt,
        get_task_prompt=stages.pentest_stage2_task_prompt,
    ),
    StageDefinition(
        name="report",
        display_name="Penetration Test Report",
        get_system_prompt=stages.pentest_stage3_system_prompt,
        get_task_prompt=stages.pentest_stage3_task_prompt,
    ),
    _FINAL_REPORT_STAGE,
]

PASSIVE_STAGES: list[StageDefinition] = [
    StageDefinition(
        name="asset_discovery",
        display_name="Passive Asset Discovery",
        get_system_prompt=stages.passive_stage1_system_prompt,
        get_task_prompt=stages.passive_stage1_task_prompt,
    ),
    StageDefinition(
        name="vulnerability_inference",
        display_name="Vulnerability Inference (Passive)",
        get_system_prompt=stages.passive_stage2_system_prompt,
        get_task_prompt=stages.passive_stage2_task_prompt,
    ),
    StageDefinition(
        name="assessment_report",
        display_name="Passive Assessment Report",
        get_system_prompt=stages.passive_stage3_system_prompt,
        get_task_prompt=stages.passive_stage3_task_prompt,
    ),
    _FINAL_REPORT_STAGE,
]


def get_stages(mode: PipelineMode) -> list[StageDefinition]:
    """Return the stage definitions for the given pipeline mode.

    Args:
        mode: Pipeline mode (CTF, Pentest, or Passive).

    Returns:
        Ordered list of StageDefinition instances.

    Raises:
        ValueError: If mode is not recognized.
    """
    if mode == PipelineMode.CTF:
        return CTF_STAGES
    elif mode == PipelineMode.PENTEST:
        return PENTEST_STAGES
    elif mode == PipelineMode.PASSIVE:
        return PASSIVE_STAGES
    else:
        raise ValueError(f"Unknown pipeline mode: {mode}")
