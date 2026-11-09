"""Pure helpers for replaying and comparing saved crew runs.

A saved result is the dict produced by PageCrewRun.serialize_result and
stored through db_utils.save_result. Its shape is:

    {"result": {"raw": str, "type": "CrewOutput", "tasks_output": [
        {"raw": str, "type": "TaskOutput", "index": int, "description": str}
    ]}}

Older rows may hold a plain string instead, so every helper here accepts
both and never raises on a malformed entry.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass
class ReplayStep:
    """One task of a saved run, in the order the crew executed it."""

    index: int
    description: str
    output: str
    inputs: dict[str, str] = field(default_factory=dict)

    @property
    def title(self) -> str:
        if self.description:
            return self.description
        return f"Task {self.index + 1}"


@dataclass
class ReplayRun:
    """A saved run normalized for display."""

    run_id: str
    crew_name: str
    created_at: str
    inputs: dict[str, str]
    final_output: str
    steps: list[ReplayStep]

    @property
    def label(self) -> str:
        stamp = self.created_at.replace("T", " ")[:19]
        return f"{self.crew_name} - {stamp}"


def _as_text(value: Any) -> str:
    """Render any stored value as text without losing structure."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, indent=2, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _unwrap(result: Any) -> Any:
    """Peel the {"result": ...} envelope that serialize_result adds."""
    if isinstance(result, dict) and "result" in result and len(result) == 1:
        return result["result"]
    return result


def normalize_inputs(inputs: Any) -> dict[str, str]:
    """Turn stored inputs into a plain name -> text mapping.

    Keys saved with the placeholder_ prefix are stripped so the replay shows
    the name the task template used.
    """
    if not isinstance(inputs, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, value in inputs.items():
        name = str(key)
        if name.startswith("placeholder_"):
            name = name[len("placeholder_"):]
        normalized[name] = _as_text(value)
    return normalized


def extract_steps(result: Any) -> list[ReplayStep]:
    """Return the task outputs of a saved result as ordered steps.

    Handles the serialized CrewOutput dict, a bare list of task outputs and
    a plain string (which becomes a single step).
    """
    payload = _unwrap(result)
    if isinstance(payload, str):
        return [ReplayStep(index=0, description="", output=payload)]

    tasks_output: Iterable[Any] = []
    if isinstance(payload, dict):
        tasks_output = payload.get("tasks_output") or []
    elif isinstance(payload, list):
        tasks_output = payload

    steps: list[ReplayStep] = []
    for position, entry in enumerate(tasks_output):
        if isinstance(entry, dict):
            raw = entry.get("raw")
            if raw is None:
                raw = entry.get("data", entry)
            description = entry.get("description") or ""
            index = entry.get("index")
            if not isinstance(index, int):
                index = position
        else:
            raw = getattr(entry, "raw", entry)
            description = getattr(entry, "description", "") or ""
            index = position
        steps.append(
            ReplayStep(
                index=index,
                description=str(description),
                output=_as_text(raw),
            )
        )
    steps.sort(key=lambda step: step.index)
    return steps


def final_output(result: Any) -> str:
    """The crew's own final answer, when the saved run has one."""
    payload = _unwrap(result)
    if isinstance(payload, dict):
        return _as_text(payload.get("raw"))
    return _as_text(payload)


def build_replay(run: Any) -> ReplayRun:
    """Normalize a Result object (or a dict with the same fields)."""
    get = run.get if isinstance(run, dict) else lambda key, default=None: getattr(run, key, default)
    inputs = normalize_inputs(get("inputs", {}))
    steps = extract_steps(get("result"))
    for step in steps:
        step.inputs = dict(inputs)
    return ReplayRun(
        run_id=str(get("id", "")),
        crew_name=str(get("crew_name", "") or ""),
        created_at=str(get("created_at", "") or ""),
        inputs=inputs,
        final_output=final_output(get("result")),
        steps=steps,
    )


def run_text(run: ReplayRun) -> str:
    """Flatten a run into the text that the diff compares."""
    lines: list[str] = []
    for step in run.steps:
        lines.append(f"## {step.title}")
        lines.extend(step.output.splitlines() or [""])
        lines.append("")
    if run.final_output:
        lines.append("## Final output")
        lines.extend(run.final_output.splitlines() or [""])
    return "\n".join(lines)


def diff_runs(left: ReplayRun, right: ReplayRun, context: int = 3) -> list[str]:
    """Unified line diff between two runs, left as the old side."""
    return list(
        difflib.unified_diff(
            run_text(left).splitlines(),
            run_text(right).splitlines(),
            fromfile=left.label,
            tofile=right.label,
            lineterm="",
            n=context,
        )
    )


def diff_summary(diff_lines: list[str]) -> dict[str, int]:
    """Count added and removed lines in a unified diff."""
    added = 0
    removed = 0
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return {"added": added, "removed": removed}


def changed_steps(left: ReplayRun, right: ReplayRun) -> list[str]:
    """Titles of the steps whose output differs between two runs."""
    left_by_index = {step.index: step for step in left.steps}
    right_by_index = {step.index: step for step in right.steps}
    changed: list[str] = []
    for index in sorted(set(left_by_index) | set(right_by_index)):
        before = left_by_index.get(index)
        after = right_by_index.get(index)
        if before is None or after is None or before.output != after.output:
            title = (after or before).title
            changed.append(title)
    return changed
