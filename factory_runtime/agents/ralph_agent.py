"""Ralph agent profile for issue resolution.

Ralph is a stricter orchestration profile built on top of the existing
AutonomousWorkflowAgent runtime. It boosts planning quality by enforcing
skill-based acceptance criteria and explicit specialist review gates.
"""

from pathlib import Path

from factory_runtime.agents.factory_adapter import FactoryAdapter


class RalphAgent(FactoryAdapter):
    """High-discipline issue resolver with skill and review gates."""

    def _load_github_agent_overlay(self) -> str:
        """Load Ralph instructions from agents/prompts definition when available."""
        project_root = Path(__file__).resolve().parent.parent
        agent_file = Path(__file__).parent / "prompts" / "ralph-agent.md"
        if not agent_file.exists():
            return ""

        content = agent_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        in_chatagent = False
        in_frontmatter = False
        parsed: list[str] = []

        for raw_line in lines:
            line = raw_line.rstrip("\n")

            if line.strip() == "```chatagent":
                in_chatagent = True
                in_frontmatter = False
                continue

            if in_chatagent and line.strip() == "```":
                break

            if not in_chatagent:
                continue

            if line.strip() == "---" and not in_frontmatter and not parsed:
                in_frontmatter = True
                continue

            if line.strip() == "---" and in_frontmatter:
                in_frontmatter = False
                continue

            if in_frontmatter:
                continue

            parsed.append(line)

        return "\n".join(parsed).strip()

    def _build_system_instructions(self) -> str:
        base = super()._build_system_instructions()
        file_overlay = self._load_github_agent_overlay()
        if file_overlay:
            return (
                base
                + "\n"
                + file_overlay
                + f"\n\nIssue Context:\n- Current issue number: #{self.issue_number}\n"
            )

        ralph_overlay = f"""

Ralph Profile (Spec-Kit discipline):
- Run a strict loop: Context -> Plan -> Implement -> Validate -> Review -> Handoff.
- Keep one issue per PR unless an explicitly linked issue chain is required.
- Prefer smallest safe diff that fully satisfies acceptance criteria.

Skill-Based Acceptance Criteria (must be explicit in outputs):
- Domain modeling skill: preserve DDD boundaries and responsibilities.
- Verification skill: run repository-native lint/build/test commands for changed scope.
- Cross-repo skill: detect whether work touches backend, client, or both and validate both when needed.
- Documentation skill: update technical docs for behavior, contracts, and operations changes.
- Safety skill: avoid secret leakage, avoid protected paths, and record escalation context when blocked.

Specialist Review Gates (required before PR handoff):
- Architecture reviewer: boundary correctness, scope control, and maintainability.
- Quality reviewer: deterministic validations, test sufficiency, and failure triage quality.
- Security reviewer: secret handling, dependency hygiene, and risky command/file checks.
- UX reviewer: when UI/UX scope is present, enforce navigation/accessibility/responsive checks.

Review Decision Contract:
- Use REVIEW_DECISION: PASS only when all skill criteria are satisfied.
- Otherwise use REVIEW_DECISION: CHANGES with a short, actionable task list.

Iteration and Escalation:
- Respect max review iteration budget of 5.
- If unresolved within budget, stop and return escalation packet with root-cause summary,
  failed checks, and minimal next tasks.

Issue Context:
- Current issue number: #{self.issue_number}
"""
        return base + "\n" + ralph_overlay.strip() + "\n"
