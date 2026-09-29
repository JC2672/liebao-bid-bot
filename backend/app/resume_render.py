"""Renders a template's Jinja2 HTML with resume data, and prints that HTML
to PDF via a headless Chromium (Playwright, already a dependency for the
Jobgether/Talent.com sources) - the same "render HTML, print it" approach
those already use, just for a resume instead of a job listing.

Contact fields (name/location/phone/email/linkedin) come from the Profile,
never the LLM - see docs/ARCHITECTURE.md: "Placeholders are substituted by
the app, not the LLM". Everything else (summary/skills/experience/
education/certifications) is `resume_json`, the LLM's structured output.
This module doesn't care which profile or real generation it's for; the
Templates tab uses SAMPLE_RESUME_JSON below purely to preview a template
in isolation, without needing Phase 3's ChatGPT engine to exist yet.
"""
from __future__ import annotations

from jinja2 import Environment
from playwright.sync_api import sync_playwright

SAMPLE_CONTACT = {
    "name": "Jordan Rivera",
    "location": "Austin, TX",
    "phone": "(512) 555-0148",
    "email": "jordan.rivera@example.com",
    "linkedin": "linkedin.com/in/jordan-rivera",
}

SAMPLE_RESUME_JSON = {
    "summary": (
        "Salesforce Developer with 6+ years building and scaling Sales Cloud and "
        "Service Cloud implementations for mid-market and enterprise orgs. Deep in "
        "Apex, LWC, and declarative automation, with a track record of cutting "
        "release cycles and case-resolution time through targeted platform work."
    ),
    "skills": [
        {"category": "Platform", "items": "Apex, LWC, SOQL/SOSL, Flow, OmniStudio"},
        {"category": "Clouds", "items": "Sales Cloud, Service Cloud, Experience Cloud"},
        {"category": "Integration", "items": "REST/SOAP APIs, MuleSoft, Platform Events"},
        {"category": "Tools", "items": "Salesforce DX, Git, Copado, Jira"},
    ],
    "experience": [
        {
            "title": "Senior Salesforce Developer",
            "company": "Northline Systems",
            "location": "Remote",
            "dates": "2022 - Present",
            "project": None,
            "bullets": [
                "Led migration of a legacy case-management process to Service Cloud, cutting average resolution time by 31%.",
                "Built a custom CPQ approval matrix in Apex and Flow, replacing a manual spreadsheet workflow used by 40+ reps.",
                "Mentored two junior developers on LWC and Apex testing patterns; team's release defect rate fell by half.",
            ],
        },
        {
            "title": "Salesforce Developer",
            "company": "Bramwell & Cole",
            "location": "Austin, TX",
            "dates": "2019 - 2022",
            "project": None,
            "bullets": [
                "Implemented a MuleSoft integration syncing order data between Salesforce and NetSuite in near real time.",
                "Rebuilt the opportunity approval process in Flow, removing 200+ lines of unmaintained Apex triggers.",
            ],
        },
    ],
    "education": [
        {"degree": "B.S. Computer Science", "school": "University of Texas at Austin", "year": "2019", "details": ""},
    ],
    "certifications": [
        "Salesforce Platform Developer II",
        "Salesforce Application Architect",
    ],
}

_ENV = Environment(autoescape=True)


def render_html(template_html: str, contact: dict, resume_json: dict) -> str:
    template = _ENV.from_string(template_html)
    return template.render(**contact, **resume_json)


def render_pdf(html: str) -> bytes:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            # margin=0: page spacing is the template's own responsibility
            # (its `body` padding), not this call's - see the default
            # template's CSS comment. That way a plain HTML preview matches
            # the real PDF instead of only getting margins at export time.
            return page.pdf(format="Letter", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        finally:
            browser.close()
