"""
Step 1 tests — resume parser only.
Run: python -m pytest tests/test_parser.py -v
"""

import pytest
from app.services.parser import parse_resume, ParsedResume

LATEX_SAMPLE = r"""
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
\textbf{Software Engineer}, IPSER LAB LLC -- Boston, MA
\end{twocolentry}
\begin{onecolentry}
\begin{highlights}
\item Led high-level system design and maintained technical documentation for a React and JavaScript/TypeScript-based real estate application.
\item Collaborated cross-functionally with product and UX teams to develop scalable React and Python-based application features using gRPC.
\item Engineered CI/CD processes by deploying AI Agents through Python-driven Jenkins pipelines.
\end{highlights}
\end{onecolentry}

\begin{twocolentry}{Jan 2021 – Jul 2023}
\textbf{Software Engineer}, Enertech Technology -- Vadodara, India
\end{twocolentry}
\begin{onecolentry}
\begin{highlights}
\item Spearheaded development of highly scalable distributed systems for a finance data team.
\item Led robust API design by engineering efficient gRPC/Protobuf APIs alongside RESTful services.
\end{highlights}
\end{onecolentry}

\section*{Skills}
\begin{onecolentry}
\textbf{Languages:} Python, Java, SQL, JavaScript
\textbf{Frameworks \& Tools:} FastAPI, Spring Boot, React, Node.js
\textbf{Cloud \& Data:} AWS (EC2, S3, RDS), Docker, Kubernetes
\end{onecolentry}

\section*{Education}
\begin{twocolentry}{Sep 2023 – May 2025}
\textbf{Northeastern University - Boston, MA}, MS in Data Architecture
\end{twocolentry}

\end{document}
"""

WORD_SAMPLE = """
Dhrumil Y Patel | Boston, MA

Professional Summary
Software Engineer with 3+ years of experience building scalable applications and APIs.

Experience
- Led system design and technical documentation for a real estate application.
- Collaborated with product and UX teams to develop scalable features.
- Engineered CI/CD processes using Jenkins pipelines.

Skills
Python, Java, SQL, JavaScript, FastAPI, Spring Boot, AWS, Docker

Education
Northeastern University — MS in Data Architecture, May 2025
"""


# --- LaTeX tests ---

def test_parse_latex_returns_parsed_resume():
    r = parse_resume(LATEX_SAMPLE, "latex")
    assert isinstance(r, ParsedResume)
    assert r.format == "latex"

def test_parse_latex_extracts_expected_sections():
    r = parse_resume(LATEX_SAMPLE, "latex")
    assert "Professional Summary" in r.sections
    assert "Experience" in r.sections
    assert "Skills" in r.sections
    assert "Education" in r.sections

def test_parse_latex_section_order_preserved():
    r = parse_resume(LATEX_SAMPLE, "latex")
    assert r.section_order[0] == "Professional Summary"
    assert r.section_order[1] == "Experience"

def test_parse_latex_extracts_bullets():
    r = parse_resume(LATEX_SAMPLE, "latex")
    bullets = r.sections["Experience"].bullets
    assert len(bullets) >= 3
    assert "system design" in bullets[0].raw.lower()

def test_parse_latex_bullet_count():
    r = parse_resume(LATEX_SAMPLE, "latex")
    # 3 IPSER + 2 Enertech = 5 total
    assert len(r.sections["Experience"].bullets) == 5

def test_parse_latex_preserves_preamble():
    r = parse_resume(LATEX_SAMPLE, "latex")
    assert r"\documentclass" in r.preamble
    assert r"\begin{document}" in r.preamble

def test_parse_latex_preserves_trailer():
    r = parse_resume(LATEX_SAMPLE, "latex")
    assert r"\end{document}" in r.trailer

def test_parse_latex_skills_plain_text():
    r = parse_resume(LATEX_SAMPLE, "latex")
    assert "Python" in r.sections["Skills"].plain_text


# --- Word tests ---

def test_parse_word_returns_parsed_resume():
    r = parse_resume(WORD_SAMPLE, "word")
    assert isinstance(r, ParsedResume)
    assert r.format == "word"

def test_parse_word_extracts_sections():
    r = parse_resume(WORD_SAMPLE, "word")
    assert "Professional Summary" in r.sections
    assert "Experience" in r.sections
    assert "Skills" in r.sections
    assert "Education" in r.sections

def test_parse_word_extracts_bullets():
    r = parse_resume(WORD_SAMPLE, "word")
    bullets = r.sections["Experience"].bullets
    assert len(bullets) == 3
    assert "system design" in bullets[0].raw.lower()

def test_parse_word_section_order_preserved():
    r = parse_resume(WORD_SAMPLE, "word")
    assert r.section_order[0] == "Professional Summary"
    assert r.section_order[1] == "Experience"


# --- Edge cases ---

def test_unsupported_format_raises():
    with pytest.raises(ValueError, match="Unsupported format"):
        parse_resume("anything", "pdf")

def test_latex_without_document_tags():
    minimal = r"\section*{Summary}" + "\nSoftware engineer.\n" + r"\section*{Skills}" + "\nPython"
    r = parse_resume(minimal, "latex")
    assert "Summary" in r.sections
    assert "Skills" in r.sections
