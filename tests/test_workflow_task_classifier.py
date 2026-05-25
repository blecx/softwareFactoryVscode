import json

from scripts.workflow_task_classifier import WorkflowTaskClassifier


def test_explicit_issue():
    classifier = WorkflowTaskClassifier()
    result = classifier.classify("resolve issue 123", False)
    assert result["task_kind"] == "issue"
    assert result["confidence"] > 0.8
    assert not result["clarification_flag"]


def test_pr_merge():
    classifier = WorkflowTaskClassifier()
    result = classifier.classify("execute pr merge", False)
    assert result["task_kind"] == "pr_merge"
    assert not result["clarification_flag"]


def test_approved_plan():
    classifier = WorkflowTaskClassifier()
    result = classifier.classify("execute approved plan", False)
    assert result["task_kind"] == "approved_plan"
    assert not result["clarification_flag"]


def test_vague_execute_plan():
    classifier = WorkflowTaskClassifier()
    result = classifier.classify("execute the plan", False)
    assert result["clarification_flag"]
    assert result["task_kind"] == "unknown"


def test_production_readiness_review():
    classifier = WorkflowTaskClassifier()
    result = classifier.classify("is this ready for production?", False)
    assert result["task_kind"] == "production_readiness"
    assert not result["clarification_flag"]


def test_stale_ambiguous_continuation():
    classifier = WorkflowTaskClassifier()
    result = classifier.classify("continue from last time", False)
    assert result["clarification_flag"]
    assert result["task_kind"] == "recovery"


def test_bypass_blocked_without_human():
    classifier = WorkflowTaskClassifier()
    result = classifier.classify("@harness-bypass-resolution fix this", False)
    assert result["task_kind"] == "bypass"
    assert result["blocked"]
    assert result["clarification_flag"]


def test_bypass_blocked_without_explicit_agent():
    classifier = WorkflowTaskClassifier()
    result = classifier.classify("i need to bypass this issue", False)
    assert result["task_kind"] == "bypass"
    assert result["blocked"]
    assert result["clarification_flag"]


def test_bypass_allowed_with_human():
    classifier = WorkflowTaskClassifier()
    result = classifier.classify("@harness-bypass-resolution fix this", True)
    assert result["task_kind"] == "bypass"
    assert not result["blocked"]
    assert not result["clarification_flag"]
    assert result["required_agent"] == "@harness-bypass-resolution"


def test_unknown_task():
    classifier = WorkflowTaskClassifier()
    result = classifier.classify("build the docker image", False)
    assert result["task_kind"] == "unknown"
    assert result["clarification_flag"]


def test_vague_prompts_return_term_evidence():
    classifier = WorkflowTaskClassifier()
    # "plan" alone should map to vague approved_plan and have clarification message
    res1 = classifier.classify("What is the plan?", False)
    assert res1["clarification_flag"] is True
    assert res1["task_kind"] == "unknown"
    assert "clarification_message" in res1
    assert "Do not guess which plan the operator means" in res1["clarification_message"]

    res2 = classifier.classify("Is it ready?", False)
    assert res2["clarification_flag"] is True
    assert res2["task_kind"] == "unknown"
    assert "clarification_message" in res2
    assert (
        "Validate against CI and pipeline reality before proceeding."
        in res2["clarification_message"]
        or "Refuse the claim and halt release actions until surfaces align."
        in res2["clarification_message"]
    )


def test_bypass_blocked_returns_evidence():
    classifier = WorkflowTaskClassifier()
    res = classifier.classify("i need to bypass this issue", False)
    assert res["blocked"] is True
    assert "clarification_message" in res
    assert (
        "Halt execution" in res["clarification_message"]
        or len(res["clarification_message"]) > 5
    )


def test_missing_language_config_flag():
    classifier = WorkflowTaskClassifier(config_path="missing_file.yml")
    result = classifier.classify("resolve issue 123", False)
    assert result["language_config_missing"] is True
