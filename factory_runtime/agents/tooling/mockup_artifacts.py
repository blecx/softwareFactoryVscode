"""Mockup artifact helpers.

Implements deterministic local mockup artifact output under `.tmp/mockups/issue-<n>/`.
This module is intentionally pure-Python and does not call external APIs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def get_mockup_dir(issue_number: int, *, base_dir: Path | str = ".tmp/mockups") -> Path:
    """Return deterministic mockup artifact directory for an issue."""
    if issue_number <= 0:
        raise ValueError("issue_number must be a positive integer")
    return Path(base_dir) / f"issue-{issue_number}"


def list_mockup_images(directory: Path) -> list[Path]:
    """Return sorted list of image files in the directory."""
    if not directory.exists():
        return []
    images: list[Path] = []
    for path in directory.iterdir():
        if path.is_file() and path.suffix.lower() in _IMAGE_EXTS:
            images.append(path)
    return sorted(images, key=lambda p: p.name)


def write_mockup_index_html(
    directory: Path, *, images: Sequence[Path] | None = None
) -> Path:
    """Write an accessible index.html for a mockup artifact directory.

    - Creates the directory if missing.
    - If `images` is not provided, reads images from `directory`.
    - Uses relative filenames so the folder can be opened directly in a browser.
    """
    directory.mkdir(parents=True, exist_ok=True)

    resolved_images = (
        list(images) if images is not None else list_mockup_images(directory)
    )
    names = [p.name for p in resolved_images]

    no_images_block = ""
    gallery_block = ""

    if not names:
        no_images_block = (
            '<p id="empty"><strong>No images found.</strong> '
            "Add one or more image files (png/jpg/webp) to this folder and reload.</p>"
        )
    else:
        items = "\n".join(
            f'<li><a href="#viewer" onclick="show({i}); return false;">{name}</a></li>'
            for i, name in enumerate(names)
        )
        gallery_block = f"""
        <nav class=\"controls\" aria-label=\"Image navigation\">
          <button type=\"button\" id=\"prev\" aria-label=\"Previous image\">Previous</button>
          <button type=\"button\" id=\"next\" aria-label=\"Next image\">Next</button>
          <a class=\"return\" href=\"#top\">Return to list</a>
        </nav>

        <section id=\"viewer\" class=\"viewer\" aria-live=\"polite\">
          <img id=\"img\" alt=\"\" />
          <p id=\"caption\" class=\"caption\"></p>
        </section>

        <h2>Images</h2>
        <ol class=\"list\">
        {items}
        </ol>
        """

    script_names = ",".join([f'"{n}"' for n in names])

    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Mockups</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 1rem; line-height: 1.4; }}
    header {{ display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }}
    .muted {{ color: #333; }}
    .controls {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 1rem 0; }}
    button {{ padding: 0.5rem 0.75rem; }}
    a.return {{ padding: 0.5rem 0.75rem; }}
    .viewer {{ border: 1px solid #000; padding: 0.75rem; max-width: 1100px; }}
    img {{ max-width: 100%; height: auto; display: block; }}
    .caption {{ margin: 0.5rem 0 0; }}
    .list {{ padding-left: 1.25rem; }}
    #empty {{ border: 1px solid #000; padding: 0.75rem; max-width: 70ch; }}
  </style>
</head>
<body>
  <a id=\"top\"></a>
  <header>
    <h1>Mockups</h1>
    <p class=\"muted\">Open this file directly from the issue folder.</p>
  </header>

  {no_images_block}
  {gallery_block}

  <script>
    const images = [{script_names}];
    let idx = 0;

    function clamp(n) {{
      if (!images.length) return 0;
      return (n + images.length) % images.length;
    }}

    function show(n) {{
      if (!images.length) return;
      idx = clamp(n);
      const name = images[idx];
      const img = document.getElementById('img');
      const caption = document.getElementById('caption');
      img.src = name;
      img.alt = name;
      caption.textContent = name;
    }}

    function bind() {{
      const prev = document.getElementById('prev');
      const next = document.getElementById('next');
      if (!prev || !next || !images.length) return;
      prev.addEventListener('click', () => show(idx - 1));
      next.addEventListener('click', () => show(idx + 1));
      document.addEventListener('keydown', (e) => {{
        if (e.key === 'ArrowLeft') show(idx - 1);
        if (e.key === 'ArrowRight') show(idx + 1);
      }});
      show(0);
    }}

    bind();
  </script>
</body>
</html>
"""

    out_path = directory / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def write_issue_mockup_index(
    issue_number: int, *, base_dir: Path | str = ".tmp/mockups"
) -> Path:
    """Convenience helper: compute folder, scan images, write index.html."""
    directory = get_mockup_dir(issue_number, base_dir=base_dir)
    return write_mockup_index_html(directory)
