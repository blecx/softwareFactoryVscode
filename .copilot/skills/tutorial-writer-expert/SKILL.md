<skill>
<name>tutorial-writer-expert</name>
<description>Skill for tutorial writer expert</description>
<file>
# Tutorial Writer Expert Skill

## Objective
Dictates the required steps, tone, and process for authoring and maintaining technical tutorials in the codebase.

## When to Use
- A user asks to create a new tutorial from scratch.
- An existing tutorial needs a major update, rewrite, or expansion.
- The operator mentions different types of tutorials to be drafted (e.g., Quickstart, Deep Dive, API Guide).


## When Not to Use
- Do not use this when not working directly on tutorial writer expert.
## Instructions
1. **Clarify Intent:** If the user hasn't specified, ask what kind of tutorial they want to write.
2. **Gather Context:** Read relevant source code, existing markdown docs, and APIs related to the tutorial subject.
3. **Plan:** Propose a short outline and wait for operator approval if the tutorial spans multiple pages or covers complex topics.
4. **Draft:** 
   - Write clear, accessible Markdown.
   - Use standard codebase conventions.
   - Include valid code examples corresponding to the actual backend/frontend logic.
5. **Review:** Ensure the drafted file matches the planned outline.

## Constraints & Guardrails
- **Write mode:** This skill inherently requires file modification or creation via standard tools.
- Place tutorials in the standard documentation path for the project (e.g., `docs/` or comparable directories based on project structure).
- Do not commit changes yourself; leave the git operations (like PRs) to the appropriate workflow agents unless instructed otherwise.

</file>
</skill>