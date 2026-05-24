import re
from pathlib import Path

repo_root = Path(".")

# Fix react-ts-testing-practices missing ## Objective
p = repo_root / ".copilot/skills/react-ts-testing-practices/SKILL.md"
if p.exists():
    text = p.read_text()
    # Remove one Objective
    text = text.replace("---\n\n## Objective\n\nEnsure canonical testing practices for React TS.\n", "", 1)
    p.write_text(text)

# Fix remaining agents
for agent in [".github/agents/workflow.md", ".github/agents/factory-operator.md"]:
    p = repo_root / agent
    if p.exists():
        text = p.read_text()
        text = text.replace("`.github/copilot-instructions.md`", ".copilot/skills/resolve-issue-workflow/SKILL.md")
        p.write_text(text)
print("done")
