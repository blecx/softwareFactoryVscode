import re
from pathlib import Path

runner_file = Path("factory_runtime/agents/validation_runner.py")
content = runner_file.read_text(encoding="utf-8")

replacement = """                lambda deadline: self._execute_subprocess_step(
                    request,
                    bundle,
                    deadline,
                    step_id="validate-ai-surfaces",
                    summary="Validate AI surface structure and write catalog manifest.",
                    command=(
                        request.python_executable,
                        "./scripts/validate-ai-surfaces.py",
                        "--repo-root",
                        ".",
                    ),
                ),
                lambda deadline: self._execute_cached_step(
                    "pytest-docs-workflow","""

content = re.sub(
    r'                lambda deadline: self\._execute_cached_step\(\n\s*"pytest-docs-workflow",',
    replacement,
    content
)

runner_file.write_text(content, encoding="utf-8")
print("WIRED INTO VALIDATION RUNNER")
