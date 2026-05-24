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
