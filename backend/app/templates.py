"""Templates are managed through the UI (create/update/delete), independent
of Profiles - a profile just references one by id (Profile.template_id).
That's a live reference, not a per-profile copy: editing a template changes
what every profile using it renders on its next generation, with no
per-profile file to keep in sync (the earlier shape - each profile owned
its own template.html, seeded from a shared default - meant a template
improvement had to be manually re-copied into every profile that wanted
it; nothing had actually diverged yet when this changed, so the migration
was lossless).

Each template lives on disk at backend/templates/<id>/ as:
  - template.json  (this module's Template model: id, name)
  - template.html  (Jinja2 source - rendered with resume_json plus the
    profile's own contact fields, then printed to PDF; see resume_render.py)
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .models import Template, TemplateDetail, TemplateInput

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "template"


def _validate_slug(template_id: str) -> None:
    if not SLUG_RE.match(template_id):
        raise ValueError(
            f"Invalid template id '{template_id}': use lowercase letters, digits and hyphens only"
        )


def _dir(template_id: str) -> Path:
    return TEMPLATES_DIR / template_id


def list_templates() -> list[Template]:
    if not TEMPLATES_DIR.exists():
        return []
    templates = []
    for d in sorted(TEMPLATES_DIR.iterdir()):
        f = d / "template.json"
        if d.is_dir() and f.exists():
            templates.append(Template.model_validate(json.loads(f.read_text(encoding="utf-8"))))
    return templates


def get_template(template_id: str) -> Template:
    f = _dir(template_id) / "template.json"
    if not f.exists():
        raise FileNotFoundError(f"No template '{template_id}' at {f}")
    return Template.model_validate(json.loads(f.read_text(encoding="utf-8")))


def get_html(template_id: str) -> str:
    f = _dir(template_id) / "template.html"
    if not f.exists():
        raise FileNotFoundError(f"No template.html for '{template_id}'")
    return f.read_text(encoding="utf-8")


def get_detail(template_id: str) -> TemplateDetail:
    template = get_template(template_id)
    return TemplateDetail(**template.model_dump(), html=get_html(template_id))


def _write(template: Template, html: str) -> None:
    d = _dir(template.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "template.json").write_text(json.dumps(template.model_dump(), indent=2), encoding="utf-8")
    (d / "template.html").write_text(html, encoding="utf-8")


def create_template(data: TemplateInput) -> Template:
    template_id = slugify(data.id or data.name)
    _validate_slug(template_id)
    if _dir(template_id).exists():
        raise FileExistsError(f"Template '{template_id}' already exists")
    template = Template(id=template_id, name=data.name)
    _write(template, data.html)
    return template


def update_template(template_id: str, data: TemplateInput) -> Template:
    if not _dir(template_id).exists():
        raise FileNotFoundError(f"No template '{template_id}'")
    template = Template(id=template_id, name=data.name)
    _write(template, data.html)
    return template


def delete_template(template_id: str) -> None:
    d = _dir(template_id)
    if not d.exists():
        raise FileNotFoundError(f"No template '{template_id}'")
    shutil.rmtree(d)
