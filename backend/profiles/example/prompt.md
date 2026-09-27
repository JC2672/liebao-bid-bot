Replace this file with your real resume-tailoring prompt.

Paste it as-is; the job description gets appended below a `---` separator at
generation time. The prompt must instruct the model to return ONLY the JSON
object matching this schema (no prose, no markdown fences):

{
  "name": "{NAME}", "title": "", "location": "{LOCATION}",
  "phone": "{PHONE}", "email": "{EMAIL}", "linkedin": "{LINKEDIN}",
  "summary": "",
  "skills": [{ "category": "", "items": "" }],
  "experience": [{
    "company": "", "location": "", "title": "", "dates": "",
    "project": "", "bullets": []
  }],
  "education": [{ "school": "", "degree": "", "year": "", "details": "" }],
  "certifications": []
}

Leave the {PLACEHOLDER} fields exactly as-is - the app substitutes them from
profile.json after parsing, so they must never be filled in or altered by the
model.
