"""Mockup image generation.

Generates one or more UI mockup images using OpenAI Images and writes them into a
deterministic local artifact directory under `.tmp/mockups/issue-<n>/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from agents.tooling.mockup_artifacts import get_mockup_dir, write_mockup_index_html
from agents.tooling.openai_images_client import (
    OpenAIAPIKeyMissingError,
    OpenAIImagesClient,
    OpenAIImagesGenerateParams,
)


@dataclass(frozen=True)
class MockupGenerationResult:
    ok: bool
    message: str
    output_dir: Path
    image_paths: Sequence[Path]
    index_html_path: Optional[Path]


def generate_issue_mockup_artifacts(
    issue_number: int,
    *,
    prompt: str,
    image_count: int = 1,
    base_dir: Path | str = ".tmp/mockups",
    api_key: str | None = None,
    model: str = "gpt-image-1",
    size: str = "1024x1024",
    openai_client: OpenAIImagesClient | None = None,
) -> MockupGenerationResult:
    """Generate mockup images and write outputs under `.tmp/mockups/issue-<n>/`.

    This function is designed as a single, workflow-callable entry point.
    """
    if image_count <= 0:
        raise ValueError("image_count must be a positive integer")

    output_dir = get_mockup_dir(issue_number, base_dir=base_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        client = openai_client or OpenAIImagesClient(api_key=api_key)
    except OpenAIAPIKeyMissingError as exc:
        return MockupGenerationResult(
            ok=False,
            message=str(exc),
            output_dir=output_dir,
            image_paths=(),
            index_html_path=None,
        )

    params = OpenAIImagesGenerateParams(model=model, size=size)

    image_paths: list[Path] = []
    for idx in range(image_count):
        png_bytes = client.generate_png_bytes(prompt, params=params)
        out_path = output_dir / f"mockup-{idx + 1:03d}.png"
        out_path.write_bytes(png_bytes)
        image_paths.append(out_path)

    index_html = write_mockup_index_html(output_dir)

    return MockupGenerationResult(
        ok=True,
        message=f"Wrote {len(image_paths)} mockup image(s) to {output_dir}",
        output_dir=output_dir,
        image_paths=tuple(image_paths),
        index_html_path=index_html,
    )
