"""Shared list of real Salesforce-ecosystem job titles, used by any source
whose own search ranks a bare "Salesforce" query poorly (confirmed so far:
Jobright and Indeed both do - see their own modules' docstrings for the
live evidence). Not Jobright-specific despite where it was first built:
this is a general taxonomy of how Salesforce roles are actually titled in
the wild, checked against real search results rather than guessed, and
worth reusing anywhere the same problem shows up.
"""
from __future__ import annotations

SALESFORCE_TITLES = [
    "Salesforce Administrator",
    "Salesforce Developer",
    "Salesforce Consultant",
    "Salesforce Business Analyst",
    "Salesforce Architect",
    "Salesforce Solution Architect",
    "Salesforce Solutions Architect",  # distinct phrasing, real matches on its own
    "Salesforce Technical Architect",
    "Salesforce Engineer",
    "Salesforce Technical Lead",
    "Salesforce Technical Consultant",
    "Salesforce Functional Consultant",
    "Salesforce QA Engineer",
    "Salesforce Quality Assurance",
    "Salesforce Testing",
    "Salesforce DevOps Engineer",
    "Salesforce Support Engineer",
    "Salesforce Integration",
    "Salesforce Product Owner",
    "Salesforce Project Manager",
    "Salesforce Marketing Cloud",
    "Marketing Cloud Developer",
    "MuleSoft Developer",
    "Salesforce CPQ",
    "Salesforce CPQ Developer",
    "Health Cloud",
    "Data Cloud",
    "Service Cloud",
    "Revenue Cloud",
    "Financial Services Cloud",
    "OmniStudio",
    "Agentforce",
]
