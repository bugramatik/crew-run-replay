import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from run_replay import (  # noqa: E402
    build_replay,
    changed_steps,
    diff_runs,
    diff_summary,
    extract_steps,
    normalize_inputs,
)


def serialized_run(tasks, raw="final answer"):
    return {
        "result": {
            "raw": raw,
            "type": "CrewOutput",
            "tasks_output": [
                {"raw": output, "type": "TaskOutput", "index": index, "description": description}
                for index, (description, output) in enumerate(tasks)
            ],
        }
    }


def test_extract_steps_from_serialized_result():
    steps = extract_steps(serialized_run([("Research", "found three sources"), ("Write", "draft v1")]))
    assert [step.description for step in steps] == ["Research", "Write"]
    assert [step.output for step in steps] == ["found three sources", "draft v1"]
    assert [step.index for step in steps] == [0, 1]


def test_extract_steps_from_plain_string():
    steps = extract_steps("just a string result")
    assert len(steps) == 1
    assert steps[0].output == "just a string result"
    assert steps[0].title == "Task 1"


def test_extract_steps_sorts_by_index():
    payload = {
        "result": {
            "raw": "done",
            "tasks_output": [
                {"raw": "second", "index": 1, "description": "B"},
                {"raw": "first", "index": 0, "description": "A"},
            ],
        }
    }
    assert [step.output for step in extract_steps(payload)] == ["first", "second"]


def test_normalize_inputs_strips_placeholder_prefix():
    inputs = normalize_inputs({"placeholder_topic": "solar", "count": 3})
    assert inputs == {"topic": "solar", "count": "3"}
    assert normalize_inputs(None) == {}


def test_build_replay_reads_result_object():
    class Result:
        id = "R_1"
        crew_name = "Research crew"
        created_at = "2025-03-01T10:00:00"
        inputs = {"placeholder_topic": "solar"}
        result = serialized_run([("Research", "a\nb")])

    run = build_replay(Result())
    assert run.run_id == "R_1"
    assert run.inputs == {"topic": "solar"}
    assert run.steps[0].inputs == {"topic": "solar"}
    assert run.final_output == "final answer"
    assert run.label.startswith("Research crew - 2025-03-01 10:00:00")


def test_diff_of_identical_runs_is_empty():
    run = build_replay({"id": "R_1", "crew_name": "c", "created_at": "t", "inputs": {}, "result": serialized_run([("A", "same")])})
    assert diff_runs(run, run) == []


def test_diff_reports_changed_lines():
    left = build_replay({"id": "R_1", "crew_name": "c", "created_at": "t1", "inputs": {}, "result": serialized_run([("A", "old line")])})
    right = build_replay({"id": "R_2", "crew_name": "c", "created_at": "t2", "inputs": {}, "result": serialized_run([("A", "new line")])})
    lines = diff_runs(left, right)
    assert any(line.startswith("-old line") for line in lines)
    assert any(line.startswith("+new line") for line in lines)
    assert diff_summary(lines) == {"added": 1, "removed": 1}
    assert changed_steps(left, right) == ["A"]


def test_changed_steps_detects_missing_step():
    left = build_replay({"id": "R_1", "crew_name": "c", "created_at": "t1", "inputs": {}, "result": serialized_run([("A", "x"), ("B", "y")])})
    right = build_replay({"id": "R_2", "crew_name": "c", "created_at": "t2", "inputs": {}, "result": serialized_run([("A", "x")])})
    assert changed_steps(left, right) == ["B"]


def test_run_text_keeps_json_output_readable():
    payload = {"result": {"raw": "done", "tasks_output": [{"raw": {"k": 1}, "index": 0, "description": "A"}]}}
    run = build_replay({"id": "R_1", "crew_name": "c", "created_at": "t", "inputs": {}, "result": payload})
    assert json.loads(run.steps[0].output) == {"k": 1}
