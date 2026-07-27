"""
Resume parser — extracts structured sections from LaTeX or Word/plain text input.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Bullet:
    raw: str          # original text as-is
    prefix: str = "" # any LaTeX prefix before the content, e.g. \item


@dataclass
class Section:
    name: str
    raw_content: str            # the full original block, preserved for writing back
    bullets: List[Bullet] = field(default_factory=list)
    plain_text: str = ""        # non-bullet text (summary, skills lines)


@dataclass
class ParsedResume:
    format: str                         # "latex" or "word"
    raw: str                            # the original input verbatim
    preamble: str = ""                  # LaTeX preamble (before \begin{document})
    header: str = ""                    # LaTeX header block (name, contact info)
    sections: Dict[str, Section] = field(default_factory=dict)
    section_order: List[str] = field(default_factory=list)
    trailer: str = ""                   # anything after the last section (\end{document})


# ---------------------------------------------------------------------------
# LaTeX parser
# ---------------------------------------------------------------------------

_LATEX_SECTION = re.compile(r"\\section\*?\{([^}]+)\}")
_LATEX_ITEM = re.compile(r"(\\item\s*)")


def parse_latex(raw: str) -> ParsedResume:
    result = ParsedResume(format="latex", raw=raw)

    # Split preamble / body / trailer
    doc_begin = raw.find(r"\begin{document}")
    doc_end = raw.rfind(r"\end{document}")

    if doc_begin == -1:
        preamble, body, trailer = "", raw, ""
    else:
        preamble = raw[: doc_begin + len(r"\begin{document}")]
        body = raw[doc_begin + len(r"\begin{document}") : doc_end if doc_end != -1 else None]
        trailer = raw[doc_end:] if doc_end != -1 else ""

    result.preamble = preamble
    result.trailer = trailer

    # Header block = everything before the first \section
    first_section = _LATEX_SECTION.search(body)
    if not first_section:
        result.header = body
        return result

    result.header = body[: first_section.start()]
    sections_body = body[first_section.start():]

    # Split into sections
    splits = list(_LATEX_SECTION.finditer(sections_body))
    for i, match in enumerate(splits):
        name = match.group(1).strip()
        start = match.end()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(sections_body)
        raw_content = sections_body[start:end]

        section = Section(name=name, raw_content=raw_content)

        # Extract \item bullets
        items = list(_LATEX_ITEM.finditer(raw_content))
        for j, item_match in enumerate(items):
            bullet_start = item_match.end()
            bullet_end = items[j + 1].start() if j + 1 < len(items) else len(raw_content)
            bullet_text = raw_content[bullet_start:bullet_end].strip().rstrip()
            section.bullets.append(Bullet(raw=bullet_text, prefix=item_match.group(1)))

        # Non-bullet plain text
        section.plain_text = _LATEX_ITEM.sub("", raw_content).strip()

        result.sections[name] = section
        result.section_order.append(name)

    return result


# ---------------------------------------------------------------------------
# Word / plain-text parser
# ---------------------------------------------------------------------------

_WORD_SECTION_HEADERS = {
    "professional summary", "summary", "objective",
    "experience", "work experience", "employment history",
    "education",
    "skills", "core skills", "technical skills",
    "projects", "certifications", "awards", "publications",
}


def parse_word(raw: str) -> ParsedResume:
    result = ParsedResume(format="word", raw=raw)
    lines = raw.splitlines()

    current_name: Optional[str] = None
    current_lines: List[str] = []

    def commit() -> None:
        if current_name is None:
            return
        raw_content = "\n".join(current_lines)
        section = Section(name=current_name, raw_content=raw_content)
        for line in current_lines:
            stripped = line.strip()
            if re.match(r"^[-•*]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
                section.bullets.append(Bullet(raw=stripped))
        section.plain_text = raw_content
        result.sections[current_name] = section
        result.section_order.append(current_name)

    for line in lines:
        if line.strip().lower() in _WORD_SECTION_HEADERS:
            commit()
            current_name = line.strip()
            current_lines = []
        elif current_name is None:
            result.header += line + "\n"
        else:
            current_lines.append(line)

    commit()
    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_resume(raw: str, fmt: str) -> ParsedResume:
    """
    Parse a resume string and return a ParsedResume.
    fmt must be 'latex' or 'word'.
    """
    fmt = fmt.lower().strip()
    if fmt == "latex":
        return parse_latex(raw)
    if fmt in ("word", "plain"):
        return parse_word(raw)
    raise ValueError(f"Unsupported format: {fmt!r}. Use 'latex' or 'word'.")
