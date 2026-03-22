import pytest
from pathlib import Path
from factory_runtime.agents.complexity_scorer import ComplexityScorer, ScoringBreakdown
from factory_runtime.agents.agent_registry import resolve_agent_spec, _load_agent_class
from factory_runtime.agents.coverage_analyzer import CoverageAnalyzer, CoverageReport, CoverageFile, CoverageDiff

def test_complexity_scorer_basic():
    scorer = ComplexityScorer()
    body = "This issue introduces a breaking change to the API and missing test coverage."
    files = ["apps/api/test.py", "apps/tui/other.py"]
    score, breakdown = scorer.score(body, files)
    assert breakdown.file_count_score == 0
    assert breakdown.cross_service_score == 1 # api and tui
    assert breakdown.breaking_score > 0
    assert breakdown.test_gap_score > 0
    assert score > 0

def test_agent_registry():
    spec = resolve_agent_spec("autonomous")
    assert spec == "factory_runtime.agents.factory_adapter:FactoryAdapter"
    
def test_coverage_analyzer():
    analyzer = CoverageAnalyzer(coverage_threshold=80.0, working_directory="/tmp")
    base_data = {
        "file1.py": CoverageFile(path="file1.py", total_lines=10, covered_lines=8, missing_lines=2, percent_covered=80.0),
        "file2.py": CoverageFile(path="file2.py", total_lines=20, covered_lines=20, missing_lines=0, percent_covered=100.0),
    }
    head_data = {
        "file1.py": CoverageFile(path="file1.py", total_lines=10, covered_lines=7, missing_lines=3, percent_covered=70.0),
        "file2.py": CoverageFile(path="file2.py", total_lines=20, covered_lines=20, missing_lines=0, percent_covered=100.0),
    }
    before = CoverageReport(total_percent=90.0, files=base_data)
    after = CoverageReport(total_percent=85.0, files=head_data)
    
    diff = analyzer.analyze_coverage_impact(before, after, ["file1.py"])
    assert "file1.py" in diff.regressions
    
