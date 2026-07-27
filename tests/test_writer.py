"""
Step 3 tests — resume writer.
Run: python -m pytest tests/test_writer.py -v
"""

import pytest
from app.services.parser import parse_resume
from app.services.writer import write_resume

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

LATEX_RESUME = r"""
\documentclass[10pt, letterpaper]{article}
\begin{document}

\begin{header}
Dhrumil Y Patel — Boston, MA
\end{header}

\section*{Professional Summary}
\begin{onecolentry}
Software Engineer with 3+ years of experience developing scalable applications, Python-based features, automation scripts, APIs, and enterprise integrations.
\end{onecolentry}

\section*{Experience}
\begin{twocolentry}{Aug 2025 – Present}
\textbf{Software Engineer}, IPSER LAB LLC -- Boston, MA\end{twocolentry}
\vspace{0.10 cm}
\begin{onecolentry}
\begin{highlights}
\item Led high-level system design for a real estate application.
\item Collaborated with product and UX teams using gRPC.
\item Engineered CI/CD processes via Jenkins pipelines.
\end{highlights}
\end{onecolentry}

\begin{twocolentry}{Jan 2021 – Jul 2023}
\textbf{Software Engineer}, Enertech Technology -- Vadodara, India\end{twocolentry}
\vspace{0.10 cm}
\begin{onecolentry}
\begin{highlights}
\item Spearheaded development of distributed systems for finance.
\item Designed gRPC/Protobuf APIs alongside RESTful services.
\end{highlights}
\end{onecolentry}

\section*{Skills}
\begin{onecolentry}
\textbf{Languages:} Python, Java, SQL, JavaScript
\end{onecolentry}
\begin{onecolentry}
\textbf{Frameworks \& Tools:} FastAPI, Spring Boot, React
\end{onecolentry}
\begin{onecolentry}
\textbf{Cloud \& Data:} AWS, Docker, Kubernetes
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
- Collaborated with product and UX teams to develop scalable features.
- Engineered CI/CD processes using Jenkins pipelines.

Skills
Python, Java, SQL, JavaScript, FastAPI, Spring Boot, AWS, Docker

Education
Northeastern University — MS in Data Architecture, May 2025
"""

TAILORED = {
    "professional_summary": (
        "Results-driven Backend Engineer with 3+ years of experience building "
        "AI-powered Python/FastAPI services on AWS. Expert in system design, "
        "prompt engineering, and scalable cloud deployments."
    ),
    "experience_bullets": {
        "Software Engineer @ IPSER LAB LLC": [
            "Architected FastAPI microservices and AI agent pipelines deployed on AWS EC2, improving uptime by 99.9%.",
            "Led cross-functional teams leveraging Python and gRPC for high-performance, low-latency backend services.",
            "Automated CI/CD workflows via Jenkins, reducing deployment time by 30% and eliminating manual errors.",
        ],
        "Software Engineer @ Enertech Technology": [
            "Engineered distributed Python backend systems handling 35% higher financial data throughput.",
            "Designed gRPC/Protobuf APIs processing 10,000+ daily transactions with zero downtime.",
        ],
    },
    "skills": {
        "Languages": "Python, SQL, Java, JavaScript",
        "Frameworks & Tools": "FastAPI, gRPC, Spring Boot, React, Pytest",
        "Cloud & Data": "AWS (EC2, S3, Lambda), Docker, Kubernetes",
    },
    "project_bullets": {},
}


# ---------------------------------------------------------------------------
# LaTeX writer tests
# ---------------------------------------------------------------------------

def test_write_latex_returns_string():
    parsed = parse_resume(LATEX_RESUME, "latex")
    result = write_resume(parsed, TAILORED)
    assert isinstance(result, str)


def test_write_latex_preserves_preamble():
    parsed = parse_resume(LATEX_RESUME, "latex")
    result = write_resume(parsed, TAILORED)
    assert r"\documentclass[10pt, letterpaper]{article}" in result
    assert r"\begin{document}" in result


def test_write_latex_preserves_end_document():
    parsed = parse_resume(LATEX_RESUME, "latex")
    result = write_resume(parsed, TAILORED)
    assert r"\end{document}" in result


def test_write_latex_rewrites_professional_summary():
    parsed = parse_resume(LATEX_RESUME, "latex")
    result = write_resume(parsed, TAILORED)
    assert "Backend Engineer" in result
    assert "AI-powered" in result


def test_write_latex_original_summary_replaced():
    parsed = parse_resume(LATEX_RESUME, "latex")
    result = write_resume(parsed, TAILORED)
    assert "Python-based features, automation scripts" not in result


def test_write_latex_rewrites_experience_bullets():
    parsed = parse_resume(LATEX_RESUME, "latex")
    result = write_resume(parsed, TAILORED)
    assert "AI agent pipelines" in result
    assert r"30\% and eliminating manual errors" in result or "30% and eliminating" in result or "30" in result


def test_write_latex_original_bullets_replaced():
    parsed = parse_resume(LATEX_RESUME, "latex")
    result = write_resume(parsed, TAILORED)
    assert "Led high-level system design for a real estate application" not in result


def test_write_latex_preserves_bullet_count_first_job():
    parsed = parse_resume(LATEX_RESUME, "latex")
    result = write_resume(parsed, TAILORED)
    # 3 new bullets for IPSER should appear — % is now safely escaped as \%
    assert "reducing deployment time by 30" in result
    assert "AI agent pipelines" in result
    assert "low-latency backend services" in result


def test_write_latex_allows_added_bullets_for_job():
    parsed = parse_resume(LATEX_RESUME, "latex")
    tailored = dict(TAILORED)
    tailored["experience_bullets"] = dict(TAILORED["experience_bullets"])
    tailored["experience_bullets"]["Software Engineer @ IPSER LAB LLC"] = [
        *TAILORED["experience_bullets"]["Software Engineer @ IPSER LAB LLC"],
        (
            "Scaled Kafka-backed RAG ingestion to handle 200000+ requests, "
            "scheduled ETL jobs with Airflow, and deployed Kubernetes HPA "
            "autoscaling to reduce latency."
        ),
    ]

    result = write_resume(parsed, tailored)
    assert "Kafka-backed RAG ingestion" in result
    assert "200000+ requests" in result
    assert "Kubernetes HPA autoscaling" in result


def test_write_latex_rewrites_skills():
    parsed = parse_resume(LATEX_RESUME, "latex")
    result = write_resume(parsed, TAILORED)
    assert "gRPC" in result
    assert "Pytest" in result
    assert "Lambda" in result


def test_write_latex_preserves_employment_dates():
    parsed = parse_resume(LATEX_RESUME, "latex")
    result = write_resume(parsed, TAILORED)
    assert "Aug 2025" in result
    assert "Jan 2021" in result


def test_write_latex_preserves_job_titles():
    parsed = parse_resume(LATEX_RESUME, "latex")
    result = write_resume(parsed, TAILORED)
    assert r"\textbf{Software Engineer}, IPSER LAB LLC" in result
    assert r"\textbf{Software Engineer}, Enertech Technology" in result


def test_write_latex_preserves_education():
    parsed = parse_resume(LATEX_RESUME, "latex")
    result = write_resume(parsed, TAILORED)
    assert "Northeastern University" in result
    assert "MS in Data Architecture" in result


def test_write_latex_preserves_section_structure():
    parsed = parse_resume(LATEX_RESUME, "latex")
    result = write_resume(parsed, TAILORED)
    assert r"\section*{Professional Summary}" in result
    assert r"\section*{Experience}" in result
    assert r"\section*{Skills}" in result
    assert r"\section*{Education}" in result


# ---------------------------------------------------------------------------
# Word writer tests
# ---------------------------------------------------------------------------

def test_write_word_returns_string():
    parsed = parse_resume(WORD_RESUME, "word")
    result = write_resume(parsed, TAILORED)
    assert isinstance(result, str)


def test_write_word_rewrites_summary():
    parsed = parse_resume(WORD_RESUME, "word")
    result = write_resume(parsed, TAILORED)
    assert "Backend Engineer" in result


def test_write_word_rewrites_bullets():
    parsed = parse_resume(WORD_RESUME, "word")
    result = write_resume(parsed, TAILORED)
    assert "AI agent pipelines" in result


def test_write_word_allows_added_bullets_for_job():
    parsed = parse_resume(WORD_RESUME, "word")
    tailored = dict(TAILORED)
    tailored["experience_bullets"] = dict(TAILORED["experience_bullets"])
    tailored["experience_bullets"]["Software Engineer @ IPSER LAB LLC"] = [
        *TAILORED["experience_bullets"]["Software Engineer @ IPSER LAB LLC"],
        (
            "Scaled Kafka-backed RAG ingestion to handle 200000+ requests, "
            "scheduled ETL jobs with Airflow, and deployed Kubernetes HPA "
            "autoscaling to reduce latency."
        ),
    ]

    result = write_resume(parsed, tailored)
    assert "Kafka-backed RAG ingestion" in result
    assert "200000+ requests" in result
    assert "Kubernetes HPA autoscaling" in result


def test_write_word_preserves_section_headings():
    parsed = parse_resume(WORD_RESUME, "word")
    result = write_resume(parsed, TAILORED)
    assert "Professional Summary" in result
    assert "Experience" in result
    assert "Skills" in result
    assert "Education" in result


def test_write_word_preserves_education_content():
    parsed = parse_resume(WORD_RESUME, "word")
    result = write_resume(parsed, TAILORED)
    assert "Northeastern University" in result


def test_write_word_replaces_original_summary():
    parsed = parse_resume(WORD_RESUME, "word")
    result = write_resume(parsed, TAILORED)
    assert "3+ years of experience building scalable applications and APIs" not in result
