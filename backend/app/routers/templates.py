from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

from .. import profiles as profiles_module
from .. import templates as templates_module
from ..models import Template, TemplateDetail, TemplateInput
from ..resume_render import SAMPLE_CONTACT, SAMPLE_RESUME_JSON, render_html, render_pdf

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
def list_all() -> list[Template]:
    return templates_module.list_templates()


@router.get("/{template_id}")
def get_one(template_id: str) -> TemplateDetail:
    try:
        return templates_module.get_detail(template_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("")
def create(data: TemplateInput) -> Template:
    try:
        return templates_module.create_template(data)
    except FileExistsError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/{template_id}")
def update(template_id: str, data: TemplateInput) -> Template:
    try:
        return templates_module.update_template(template_id, data)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{template_id}")
def delete(template_id: str) -> dict:
    using = [p.id for p in profiles_module.list_profiles() if p.template_id == template_id]
    if using:
        raise HTTPException(
            409,
            f"Template '{template_id}' is still used by profile(s): {', '.join(using)}. "
            "Switch them to a different template first.",
        )
    try:
        templates_module.delete_template(template_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"ok": True}


@router.get("/{template_id}/preview.html", response_class=HTMLResponse)
def preview_html(template_id: str) -> str:
    """Renders the template against fixed sample data (not a real profile or
    generation) so it can be designed/tweaked without Phase 3's ChatGPT
    engine existing yet."""
    try:
        html = templates_module.get_html(template_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return render_html(html, SAMPLE_CONTACT, SAMPLE_RESUME_JSON)


@router.get("/{template_id}/preview.pdf")
def preview_pdf(template_id: str) -> Response:
    try:
        html = templates_module.get_html(template_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    rendered = render_html(html, SAMPLE_CONTACT, SAMPLE_RESUME_JSON)
    pdf_bytes = render_pdf(rendered)
    return Response(content=pdf_bytes, media_type="application/pdf")
