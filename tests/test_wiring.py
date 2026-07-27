"""
Step 4 tests — full pipeline wiring through FastAPI.
Uses mocked GPT so no API calls are made.
Run: python -m pytest tests/test_wiring.py -v
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

LATEX_RESUME = r"""
\documentclass[10pt, letterpaper]{article}
\begin{document}
\begin{header}
Dhrumil Y Patel — Boston, MA
\end{header}
\section*{Professional Summary}
\begin{onecolentry}
Software Engineer with 3+ years of experience developing scalable applications and APIs.
\end{onecolentry}
\section*{Experience}
\begin{twocolentry}{Aug 2025 – Present}
\textbf{Software Engineer}, IPSER LAB LLC -- Boston, MA\end{twocolentry}
\vspace{0.10 cm}
\begin{onecolentry}
\begin{highlights}
\item Led system design for a real estate application.
\item Collaborated with product and UX teams using gRPC.
\item Engineered CI/CD processes via Jenkins pipelines.
\end{highlights}
\end{onecolentry}
\section*{Skills}
\begin{onecolentry}
\textbf{Languages:} Python, Java, SQL
\end{onecolentry}
\section*{Education}
\begin{twocolentry}{Sep 2023 – May 2025}
\textbf{Northeastern University - Boston, MA}, MS in Data Architecture
\end{twocolentry}
\end{document}
"""

WORD_RESUME = """
Dhrumil Y Patel | Boston, MA

Professional Summary
Software Engineer with 3+ years of experience building scalable applications and APIs.

Experience
IPSER LAB LLC — Software Engineer, Aug 2025 – Present
- Led system design for a real estate application.
- Collaborated with product teams to develop scalable features.
- Engineered CI/CD processes using Jenkins pipelines.

Skills
Python, Java, SQL, FastAPI, AWS

Education
Northeastern University — MS in Data Architecture, May 2025
"""

MOCK_GPT_RESPONSE = {
    "professional_summary": "AI-driven Backend Engineer with expertise in Python and FastAPI on AWS.",
    "experience_bullets": {
        "Software Engineer @ IPSER LAB LLC": [
            "Architected FastAPI microservices and AI pipelines on AWS EC2.",
            "Led Python and gRPC backend services for high-performance delivery.",
            "Automated CI/CD via Jenkins, cutting deploy time by 30%.",
        ]
    },
    "skills": {
        "Languages": "Python, SQL, Java",
    },
    "project_bullets": {},
}

JD = "We need a Python Backend Engineer with FastAPI, AWS, and AI model experience."


def make_mock_gpt():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(MOCK_GPT_RESPONSE)}}]
    }
    mock_post = MagicMock(return_value=mock_resp)
    return mock_post


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_route():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# /tailor (JSON API)
# ---------------------------------------------------------------------------

def test_tailor_api_latex_returns_200(monkeypatch):
    with patch("app.services.gpt_adapter.httpx.post", make_mock_gpt()):
        r = client.post("/tailor", json={
            "jd": JD,
            "resume_code": LATEX_RESUME,
            "additional_information": "Emphasise AI skills.",
            "format": "latex",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["format"] == "latex"
    assert "tailored_code" in data
    assert r"\documentclass" in data["tailored_code"]


def test_tailor_api_latex_rewrites_summary(monkeypatch):
    with patch("app.services.gpt_adapter.httpx.post", make_mock_gpt()):
        r = client.post("/tailor", json={
            "jd": JD,
            "resume_code": LATEX_RESUME,
            "format": "latex",
        })
    assert "AI-driven Backend Engineer" in r.json()["tailored_code"]


def test_tailor_api_latex_preserves_dates(monkeypatch):
    with patch("app.services.gpt_adapter.httpx.post", make_mock_gpt()):
        r = client.post("/tailor", json={
            "jd": JD,
            "resume_code": LATEX_RESUME,
            "format": "latex",
        })
    assert "Aug 2025" in r.json()["tailored_code"]
    assert "Sep 2023" in r.json()["tailored_code"]


def test_tailor_api_latex_preserves_education(monkeypatch):
    with patch("app.services.gpt_adapter.httpx.post", make_mock_gpt()):
        r = client.post("/tailor", json={
            "jd": JD,
            "resume_code": LATEX_RESUME,
            "format": "latex",
        })
    assert "Northeastern University" in r.json()["tailored_code"]


def test_tailor_api_word_returns_200(monkeypatch):
    with patch("app.services.gpt_adapter.httpx.post", make_mock_gpt()):
        r = client.post("/tailor", json={
            "jd": JD,
            "resume_code": WORD_RESUME,
            "format": "word",
        })
    assert r.status_code == 200
    assert r.json()["format"] == "word"
    assert "tailored_code" in r.json()


def test_tailor_api_word_rewrites_summary(monkeypatch):
    with patch("app.services.gpt_adapter.httpx.post", make_mock_gpt()):
        r = client.post("/tailor", json={
            "jd": JD,
            "resume_code": WORD_RESUME,
            "format": "word",
        })
    assert "AI-driven Backend Engineer" in r.json()["tailored_code"]


def test_tailor_api_missing_jd_returns_422():
    r = client.post("/tailor", json={
        "resume_code": LATEX_RESUME,
        "format": "latex",
    })
    assert r.status_code == 422


def test_tailor_api_unsupported_format_returns_422():
    r = client.post("/tailor", json={
        "jd": JD,
        "resume_code": LATEX_RESUME,
        "format": "pdf",
    })
    assert r.status_code == 422
