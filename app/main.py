import sys
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import html as _html

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Ensure project root is on path and .env is loaded
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from app.services.parser import ParsedResume, parse_resume          # noqa: E402
from app.services.gpt_adapter import GPTAdapter                     # noqa: E402
from app.services.writer import write_resume                        # noqa: E402

app = FastAPI(title="Resume Tailor")

HTML_TEMPLATE = (Path(__file__).parent / "templates" / "index.html").read_text(encoding="utf-8")


def _render(jd="", resume_code="", additional_information="", fmt="latex", result=None, error=None) -> str:
    """Render the index.html template by simple string substitution."""
    out_html = ""
    if error:
        out_html = f'<div class="error"><strong>Error:</strong> {_html.escape(error)}</div>'
    elif result:
        code = _html.escape(result["tailored_code"])
        out_html = (
            '<button class="copy-btn" onclick="copyOutput()">Copy to clipboard</button>'
            f'<pre id="output-code">{code}</pre>'
        )
    else:
        out_html = '<p style="color:#888;">No output yet. Fill in the fields above and click Generate.</p>'

    lat_sel = 'selected' if fmt != 'word' else ''
    wrd_sel = 'selected' if fmt == 'word' else ''

    page = (
        HTML_TEMPLATE
        .replace('{{ jd or "" }}', _html.escape(jd))
        .replace('{{ resume_code or "" }}', _html.escape(resume_code))
        .replace('{{ additional_information or "" }}', _html.escape(additional_information))
        .replace('{% if format == "latex" or not format %}selected{% endif %}', lat_sel)
        .replace('{% if format == "word" %}selected{% endif %}', wrd_sel)
        .replace(
            '{% if error %}\n        <div class="error"><strong>Error:</strong> {{ error }}</div>\n      {% elif result %}\n        <button class="copy-btn" onclick="copyOutput()">Copy to clipboard</button>\n        <pre id="output-code">{{ result.tailored_code }}</pre>\n      {% else %}\n        <p style="color:#888;">No output yet. Fill in the fields above and click Generate.</p>\n      {% endif %}',
            out_html,
        )
    )
    return page


class TailorRequest(BaseModel):
    jd: str
    resume_code: str
    additional_information: Optional[str] = None
    format: Literal["latex", "word"] = "latex"


# ---------------------------------------------------------------------------
# Helper — convert ParsedResume into GPT adapter input blocks
# ---------------------------------------------------------------------------

def _build_gpt_inputs(parsed: ParsedResume) -> Dict[str, Any]:
    """Extract experience blocks, skills blocks, and project blocks from parsed resume."""
    experience_blocks: List[Dict[str, Any]] = []
    skills_blocks: List[Dict[str, str]] = []
    project_blocks: List[Dict[str, Any]] = []
    summary = ""

    for name in parsed.section_order:
        section = parsed.sections[name]
        lower = name.lower()

        if "summary" in lower or "objective" in lower:
            summary = section.plain_text.strip()

        elif "experience" in lower or "employment" in lower:
            if section.bullets:
                # For LaTeX: attempt to split bullets into per-job groups
                # using the job title lines in plain_text as separators
                # Simple approach: all bullets under one block per section
                # (the writer matches by fuzzy label)
                import re
                # Find job title lines in the raw section content
                job_pattern = re.compile(
                    r"\\textbf\{([^}]+)\}[^\\]*?([\w][^\n\\]*?)\\end\{twocolentry\}",
                    re.I,
                )
                job_matches = list(job_pattern.finditer(section.raw_content))

                if job_matches and parsed.format == "latex":
                    # Split bullets across jobs
                    # Find highlight blocks in order
                    highlights_pattern = re.compile(
                        r"\\begin\{(?:highlights|itemize|highlightsforbulletentries)\}"
                        r"(.*?)"
                        r"\\end\{(?:highlights|itemize|highlightsforbulletentries)\}",
                        re.S,
                    )
                    item_pattern = re.compile(r"\\item\s+(.+?)(?=\\item|\Z)", re.S)
                    highlight_blocks = list(highlights_pattern.finditer(section.raw_content))

                    for i, jm in enumerate(job_matches):
                        title = jm.group(1).strip()
                        company_raw = jm.group(2).strip()
                        label = f"{title} @ {company_raw}"
                        bullets = []
                        if i < len(highlight_blocks):
                            inner = highlight_blocks[i].group(1)
                            bullets = [m.group(1).strip() for m in item_pattern.finditer(inner)]
                        experience_blocks.append({"label": label, "bullets": bullets})
                else:
                    # Word or simple LaTeX — one block
                    experience_blocks.append({
                        "label": "Experience",
                        "bullets": [b.raw for b in section.bullets],
                    })

        elif "skill" in lower:
            if parsed.format == "latex":
                import re
                label_pattern = re.compile(r"\\textbf\{([^}]+?):?\}:?\s*(.+?)(?=\\textbf|\Z|\n\s*\\)", re.S)
                for m in label_pattern.finditer(section.raw_content):
                    cat = m.group(1).strip().rstrip(":")
                    content = m.group(2).strip()
                    skills_blocks.append({"label": cat, "content": content})
                if not skills_blocks:
                    skills_blocks.append({"label": "Skills", "content": section.plain_text})
            else:
                skills_blocks.append({"label": "Skills", "content": section.plain_text})

        elif "project" in lower:
            if section.bullets:
                project_blocks.append({
                    "label": name,
                    "bullets": [b.raw for b in section.bullets],
                })

    return {
        "summary": summary,
        "experience_blocks": experience_blocks,
        "skills_blocks": skills_blocks,
        "project_blocks": project_blocks,
    }


# ---------------------------------------------------------------------------
# Core tailoring function (shared by JSON API and form route)
# ---------------------------------------------------------------------------

def run_tailor(jd: str, resume_code: str, additional_information: Optional[str], fmt: str) -> Dict[str, Any]:
    # 1 — Parse
    try:
        parsed = parse_resume(resume_code, fmt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 2 — Build GPT inputs
    gpt_inputs = _build_gpt_inputs(parsed)

    if not gpt_inputs["experience_blocks"] and not gpt_inputs["summary"]:
        raise HTTPException(
            status_code=422,
            detail="Resume does not contain recognisable sections. "
                   "Make sure it includes Professional Summary and Experience sections.",
        )

    # 3 — Call GPT
    try:
        adapter = GPTAdapter()
        tailored_fields = adapter.tailor(
            jd=jd,
            summary=gpt_inputs["summary"],
            experience_blocks=gpt_inputs["experience_blocks"],
            skills_blocks=gpt_inputs["skills_blocks"],
            project_blocks=gpt_inputs["project_blocks"],
            additional_information=additional_information,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    # 4 — Write back into template
    tailored_code = write_resume(parsed, tailored_fields)

    return {
        "format": fmt,
        "tailored_code": tailored_code,
        "tailored_fields": tailored_fields,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return _render()


@app.post("/tailor")
def tailor(request: TailorRequest):
    return run_tailor(
        jd=request.jd,
        resume_code=request.resume_code,
        additional_information=request.additional_information,
        fmt=request.format,
    )


@app.post("/tailor-form", response_class=HTMLResponse)
def tailor_form(
    request: Request,
    jd: str = Form(...),
    resume_code: str = Form(...),
    additional_information: str = Form(""),
    format: Literal["latex", "word"] = Form("latex"),
):
    error = None
    result = None
    try:
        result = run_tailor(
            jd=jd,
            resume_code=resume_code,
            additional_information=additional_information or None,
            fmt=format,
        )
    except HTTPException as exc:
        error = exc.detail

    return _render(
        jd=jd,
        resume_code=resume_code,
        additional_information=additional_information,
        fmt=format,
        result=result,
        error=error,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
