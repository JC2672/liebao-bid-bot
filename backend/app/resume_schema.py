"""The LLM output contract - see docs/ARCHITECTURE.md's "Resume JSON schema"
section, which this mirrors exactly. Real structural (Pydantic) validation,
not the string-heuristic approach ("starts with <html>, length > 500, no
refusal phrases") a sibling project uses for its own free-form HTML output -
we can do better here because we ask ChatGPT for JSON matching a schema we
already use everywhere else in this project, not a raw document.
"""
from __future__ import annotations

from pydantic import BaseModel


class SkillGroup(BaseModel):
    category: str
    items: str


class ExperienceEntry(BaseModel):
    company: str
    location: str = ""
    title: str
    dates: str = ""
    project: str = ""
    bullets: list[str] = []


class EducationEntry(BaseModel):
    school: str
    degree: str
    year: str = ""
    details: str = ""


class ResumeJson(BaseModel):
    # Contact fields are always overwritten from the profile after parsing
    # (see generation.py) regardless of what the LLM actually returned here
    # - it's asked to leave them as literal placeholder tokens, but nothing
    # downstream trusts that it complied.
    name: str = ""
    title: str = ""
    location: str = ""
    phone: str = ""
    email: str = ""
    linkedin: str = ""
    summary: str = ""
    skills: list[SkillGroup] = []
    experience: list[ExperienceEntry] = []
    education: list[EducationEntry] = []
    certifications: list[str] = []
