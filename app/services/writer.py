"""
Resume writer — takes the ParsedResume template + GPT tailored dict and
reconstructs the full document with new content written back into the
original structure.

Protected (never touched):
  - Employment dates
  - Job titles and company names / locations
  - Education, certifications, preamble, header, trailer
"""

import re
from typing import Any, Dict, List

from app.services.parser import ParsedResume


# ---------------------------------------------------------------------------
# LaTeX safety: escape bare % signs that would break the PDF
# ---------------------------------------------------------------------------

def _escape_latex_percent(text: str) -> str:
    r"""Replace any % not already preceded by \ with \%."""
    return re.sub(r"(?<!\\)%", r"\\%", text)


def _sanitise_latex_bullet(text: str) -> str:
    """Ensure a bullet is safe for LaTeX output."""
    return _escape_latex_percent(text)

def _normalize(text: str) -> str:
    """Lower-case, collapse whitespace, strip punctuation for fuzzy matching."""
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()


def _token_overlap(a: str, b: str) -> float:
    """Fraction of tokens in `a` that appear in `b`."""
    ta = set(_normalize(a))
    tb = set(_normalize(b))
    if not ta:
        return 0.0
    return len(ta & tb) / len(ta)


def _best_match(label: str, candidates: List[str]) -> str | None:
    """Return the candidate with highest token overlap with label, or None."""
    if not candidates:
        return None
    scored = [(c, _token_overlap(label, c)) for c in candidates]
    best_key, best_score = max(scored, key=lambda x: x[1])
    return best_key if best_score > 0.3 else None


# ---------------------------------------------------------------------------
# LaTeX writer
# ---------------------------------------------------------------------------

# Matches \begin{highlights}...\end{highlights} (or itemize / highlightsforbulletentries)
_HIGHLIGHTS_BLOCK = re.compile(
    r"(\\begin\{(?:highlights|itemize|highlightsforbulletentries)\})"
    r"(.*?)"
    r"(\\end\{(?:highlights|itemize|highlightsforbulletentries)\})",
    re.S,
)

# Matches \item <content until next \item or end of block>
_ITEM = re.compile(r"\\item\s+")

# Matches the job identifier line: \textbf{Title}, Company\end{twocolentry}
_JOB_ID_LINE = re.compile(
    r"\\textbf\{([^}]+)\}[^\\]*?([\w][^\n\\]*?)\\end\{twocolentry\}",
    re.I,
)

# Matches \textbf{Category:} or \textbf{Category \& Sub:}
_SKILL_LABEL = re.compile(r"\\textbf\{([^}]+?):?\}")


def _replace_highlights_bullets(block_content: str, new_bullets: List[str]) -> str:
    r"""Replace \item lines inside a highlights block with new_bullets."""
    item_positions = [m.start() for m in _ITEM.finditer(block_content)]
    if not item_positions or not new_bullets:
        return block_content

    # Sanitise every incoming bullet before writing it
    safe_bullets = [_sanitise_latex_bullet(b) for b in new_bullets]

    # Determine the indentation used by the original \item lines
    first_item_pos = item_positions[0]
    indent = ""
    sol = block_content.rfind("\n", 0, first_item_pos)
    if sol != -1:
        indent = re.match(r"[ \t]*", block_content[sol + 1 :])[0]

    # Build replacement from all generated bullets. This allows explicit
    # user requests (via additional instructions) to add/remove bullets.
    lines = [f"{indent}\\item {b.strip()}" for b in safe_bullets]

    # Content before first \item
    prefix = block_content[: item_positions[0]]

    # Content after last \item's text
    last_item_end = item_positions[-1]
    remaining = block_content[last_item_end:]
    # Skip past the last \item text (everything up to next \item, which doesn't exist here)
    after_last_item = re.search(r"\\item\s+(.+?)(?=\n\s*\\(?:item|end)|\Z)", remaining, re.S)
    if after_last_item:
        suffix = remaining[after_last_item.end() :]
    else:
        suffix = ""

    return prefix + "\n".join(lines) + "\n" + suffix


def _write_latex_experience(section_raw: str, experience_bullets: Dict[str, List[str]]) -> str:
    """Rewrite bullets in the Experience section; leave all other content intact."""
    if not experience_bullets:
        return section_raw

    gpt_labels = list(experience_bullets.keys())

    result = section_raw
    # Find every job identifier line in order
    for job_match in _JOB_ID_LINE.finditer(section_raw):
        job_title = job_match.group(1).strip()
        company = job_match.group(2).strip()
        raw_label = f"{job_title} @ {company}"

        matched_key = _best_match(raw_label, gpt_labels)
        if matched_key is None:
            continue
        new_bullets = experience_bullets[matched_key]

        # Find the highlights block that immediately follows this job line
        after_job = section_raw[job_match.end() :]
        block_match = _HIGHLIGHTS_BLOCK.search(after_job)
        if not block_match:
            continue

        # Find the absolute position of this block in `result`
        abs_block_start = result.find(block_match.group(0))
        if abs_block_start == -1:
            continue

        # Replace just the inner content of the block
        open_tag = block_match.group(1)
        inner = block_match.group(2)
        close_tag = block_match.group(3)
        new_inner = _replace_highlights_bullets(inner, new_bullets)
        new_block = open_tag + new_inner + close_tag

        result = result[:abs_block_start] + new_block + result[abs_block_start + len(block_match.group(0)) :]

    return result


def _write_latex_skills(section_raw: str, skills: Dict[str, str]) -> str:
    """Replace skill list content after each \textbf{Category:} while keeping the label."""
    if not skills:
        return section_raw

    gpt_labels = list(skills.keys())
    lines = section_raw.splitlines(keepends=True)
    new_lines = []
    for line in lines:
        label_match = _SKILL_LABEL.search(line)
        if label_match:
            raw_label = label_match.group(1).strip().rstrip(":")
            matched_key = _best_match(raw_label, gpt_labels)
            if matched_key:
                new_content = skills[matched_key]
                # Rebuild line: keep everything up to and including the closing }
                # then replace the rest with new content
                after_brace = line[label_match.end() :]
                # Strip old content (may start with : or space)
                stripped = after_brace.lstrip(": ")
                line_ending = "\n" if line.endswith("\n") else ""
                line = (
                    line[: label_match.end()]
                    + ": "
                    + new_content
                    + line_ending
                )
        new_lines.append(line)
    return "".join(new_lines)


def _write_latex_summary(section_raw: str, new_summary: str) -> str:
    """Replace plain text content inside the Professional Summary section."""
    if not new_summary:
        return section_raw

    # Try to replace content inside \begin{onecolentry}...\end{onecolentry}
    one_col = re.compile(
        r"(\\begin\{onecolentry\}\s*(?:\\justify\s*)?)(.*?)(\\end\{onecolentry\})",
        re.S,
    )
    match = one_col.search(section_raw)
    if match:
        return (
            section_raw[: match.start()]
            + match.group(1)
            + "\n"
            + new_summary.strip()
            + "\n"
            + match.group(3)
            + section_raw[match.end() :]
        )

    # Fallback: replace all non-command text in the section
    # Keep lines that start with \ but replace plain text lines
    lines = section_raw.splitlines(keepends=True)
    new_lines = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("\\") and not replaced:
            new_lines.append(new_summary.strip() + "\n")
            replaced = True
        else:
            new_lines.append(line)
    return "".join(new_lines)


def _write_latex_projects(section_raw: str, project_bullets: Dict[str, List[str]]) -> str:
    """Same logic as experience writer — replace bullets per project block."""
    return _write_latex_experience(section_raw, project_bullets)


def _write_section(raw: str, section_heading: str, transformer) -> str:
    r"""
    Find \section*{heading} in raw, extract its content block,
    apply transformer, and stitch it back.
    """
    pattern = re.compile(
        rf"(\\section\*?\{{{re.escape(section_heading)}\}})(.*?)"
        rf"(?=\\section\*?\{{|\\end\{{document\}}|\Z)",
        re.S,
    )
    match = pattern.search(raw)
    if not match:
        return raw
    heading_text = match.group(1)
    section_content = match.group(2)
    new_content = transformer(section_content)
    return raw[: match.start()] + heading_text + new_content + raw[match.end() :]


def write_latex(parsed: ParsedResume, tailored: Dict[str, Any]) -> str:
    raw = parsed.raw
    summary = _escape_latex_percent(tailored.get("professional_summary", ""))
    exp_bullets = tailored.get("experience_bullets", {})
    skills = tailored.get("skills", {})
    proj_bullets = tailored.get("project_bullets", {})

    if summary:
        raw = _write_section(raw, "Professional Summary", lambda s: _write_latex_summary(s, summary))
    if exp_bullets:
        raw = _write_section(raw, "Experience", lambda s: _write_latex_experience(s, exp_bullets))
    if skills:
        for section_name in ("Skills", "Core Skills", "Technical Skills"):
            new_raw = _write_section(raw, section_name, lambda s: _write_latex_skills(s, skills))
            if new_raw != raw:
                raw = new_raw
                break
    if proj_bullets:
        raw = _write_section(raw, "Projects", lambda s: _write_latex_projects(s, proj_bullets))

    return raw


# ---------------------------------------------------------------------------
# Word / plain-text writer
# ---------------------------------------------------------------------------

_BULLET_PREFIX = re.compile(r"^[-•*]\s+")


def write_word(parsed: ParsedResume, tailored: Dict[str, Any]) -> str:
    summary = tailored.get("professional_summary", "")
    exp_bullets = tailored.get("experience_bullets", {})
    skills = tailored.get("skills", {})
    proj_bullets = tailored.get("project_bullets", {})

    output_parts: List[str] = [parsed.header.rstrip()]
    gpt_exp_labels = list(exp_bullets.keys())
    gpt_proj_labels = list(proj_bullets.keys())

    for section_name in parsed.section_order:
        section = parsed.sections[section_name]
        output_parts.append(section_name)
        lower = section_name.lower()

        if "summary" in lower or "objective" in lower:
            output_parts.append(summary or section.plain_text)

        elif "experience" in lower or "employment" in lower:
            lines = section.raw_content.splitlines()
            current_job_label: str | None = None
            pending_non_bullets: List[str] = []

            def flush_pending():
                if pending_non_bullets:
                    output_parts.extend(pending_non_bullets)
                    pending_non_bullets.clear()

            i = 0
            while i < len(lines):
                line = lines[i]
                stripped = line.strip()
                if _BULLET_PREFIX.match(stripped):
                    # Collect contiguous bullets for this block
                    block_bullets = []
                    while i < len(lines) and _BULLET_PREFIX.match(lines[i].strip()):
                        block_bullets.append(lines[i].strip())
                        i += 1

                    matched_key = _best_match(current_job_label or "", gpt_exp_labels)
                    if matched_key and matched_key in exp_bullets:
                        new_b = exp_bullets[matched_key]
                        flush_pending()
                        for b in new_b:
                            b_clean = _BULLET_PREFIX.sub("", b.strip())
                            output_parts.append(f"- {b_clean}")
                    else:
                        flush_pending()
                        output_parts.extend(block_bullets)
                    continue
                else:
                    if stripped:
                        current_job_label = stripped
                    pending_non_bullets.append(line)
                    i += 1

            flush_pending()

        elif "skill" in lower:
            if skills:
                all_skills = []
                for v in skills.values():
                    all_skills.append(v)
                output_parts.append(", ".join(all_skills))
            else:
                output_parts.append(section.plain_text)

        elif "project" in lower:
            lines = section.raw_content.splitlines()
            current_proj_label: str | None = None
            pending: List[str] = []

            j = 0
            while j < len(lines):
                line = lines[j]
                stripped = line.strip()
                if _BULLET_PREFIX.match(stripped):
                    block = []
                    while j < len(lines) and _BULLET_PREFIX.match(lines[j].strip()):
                        block.append(lines[j].strip())
                        j += 1
                    matched_key = _best_match(current_proj_label or "", gpt_proj_labels)
                    if matched_key and matched_key in proj_bullets:
                        new_b = proj_bullets[matched_key]
                        output_parts.extend(pending)
                        pending.clear()
                        for b in new_b:
                            b_clean = _BULLET_PREFIX.sub("", b.strip())
                            output_parts.append(f"- {b_clean}")
                    else:
                        output_parts.extend(pending)
                        pending.clear()
                        output_parts.extend(block)
                    continue
                else:
                    if stripped:
                        current_proj_label = stripped
                    pending.append(line)
                    j += 1
            output_parts.extend(pending)

        else:
            # Education, certifications — copy verbatim
            output_parts.append(section.raw_content)

        output_parts.append("")

    return "\n".join(output_parts).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def write_resume(parsed: ParsedResume, tailored: Dict[str, Any]) -> str:
    """
    Reconstruct the full resume document with tailored content.
    Returns the complete string ready for display or download.
    """
    if parsed.format == "latex":
        return write_latex(parsed, tailored)
    return write_word(parsed, tailored)
