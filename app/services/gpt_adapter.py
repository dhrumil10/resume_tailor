"""
GPT adapter — sends parsed resume sections to OpenAI GPT and returns
structured tailored content as a dictionary.

Returned schema:
{
    "professional_summary": "<rewritten 2-4 sentence summary>",
    "experience_bullets": {
        "<Job Title @ Company>": ["bullet 1", "bullet 2", ...],
        ...
    },
    "skills": {
        "<Category label exactly as in original>": "<rewritten comma-separated skills>",
        ...
    },
    "project_bullets": {
        "<Project Name>": ["bullet 1", ...],
        ...
    }
}
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


# ---------------------------------------------------------------------------
# System prompt — aggressive, placement-focused
# ---------------------------------------------------------------------------

# SYSTEM_PROMPT = """
# You are an elite resume strategist and placement specialist.
# Your ONLY goal is to maximise the candidate's chances of being shortlisted for
# the exact job described in the Job Description.

# You MUST follow every rule below without exception:
# If ADDITIONAL INSTRUCTIONS conflict with a default rule below, follow
# ADDITIONAL INSTRUCTIONS first.

# WHAT YOU MUST CHANGE
# - Professional Summary: rewrite completely to mirror the JD's language, role
#   expectations, and top required skills. 2-4 sentences. Same length as original.
# - Experience bullets: rewrite every bullet to reflect JD keywords, required
#     skills, and responsibilities. Keep the same number of bullets per job unless
#     ADDITIONAL INSTRUCTIONS explicitly ask to add/remove bullets for a role.
#   Keep the same approximate length per bullet.
#   Use strong action verbs. Add quantified impact where the original has metrics
#   or where a reasonable estimate can be inferred from context.
#   Wrap the 2-3 most important JD-required skills or tools in each bullet with
#   \\textbf{...} so they stand out to the recruiter. Example:
#     Engineered \\textbf{C++ edge computing} pipelines achieving \\textbf{99\\%} uptime.
# - Skills section: reorder and rewrite to put JD-required skills first.
#   Add any JD-required skills that are plausibly supported by the resume context.
#   Keep the same category labels.

# WHAT YOU MUST NEVER CHANGE
# - Employment dates (e.g. Aug 2025 – Present)
# - Job titles (e.g. Software Engineer)
# - Company names and locations
# - Education degrees, institutions, dates
# - Certifications

# LATEX ESCAPING RULES (critical — violations break the PDF)
# - Percent sign: always write \\% not %. Example: 40\\%, 99\\%, 35\\%.
# - Ampersand in text: always write \\& not &.
# - All bullets must be complete sentences ending with a period.
# - Never end a bullet mid-sentence.

# JSON OUTPUT ESCAPING (critical)
# In JSON string values, a backslash must be written as two backslashes.
# So to produce \\textbf{term} in LaTeX, write \\textbf{term} inside your JSON string.
# To produce \\%, write \\% inside your JSON string.

# OUTPUT FORMAT
# Return a single JSON object with exactly these keys:
# {
#   "professional_summary": "<string>",
#   "experience_bullets": {
#     "<Job Title @ Company>": ["<bullet>", ...]
#   },
#   "skills": {
#     "<Category label>": "<comma-separated skills string>"
#   },
#   "project_bullets": {
#     "<Project Name>": ["<bullet>", ...]
#   }
# }

# No extra keys. No markdown. No explanation. JSON only.
# """.strip()
SYSTEM_PROMPT = """
You are a resume strategist.
Your ONLY goal is to maximise the candidate's chances of being shortlisted for
the exact job described in the Job Description.
Add context from job description skills if not there in resume add that to achieve alignment with the Job Description.

You MUST follow every rule below without exception:
If ADDITIONAL INSTRUCTIONS conflict with a default rule below, follow
ADDITIONAL INSTRUCTIONS first.

WHAT YOU MUST CHANGE
- Professional Summary: rewrite completely to mirror the JD's language, role
  expectations, and top required skills. 2-4 sentences. Same length as original.
- Experience bullets: rewrite every bullet to reflect Job Description (JD) keywords, required
    skills, and responsibilities. Keep the same number of bullets per job unless
    ADDITIONAL INSTRUCTIONS explicitly ask to add/remove bullets for a role or modify bullet points.
  Keep the same approximate length per bullet.
  
  Use strong action verbs. Add quantified impact where the original has metrics
  or where a reasonable estimate can be inferred from context.
  Wrap the most important JD-required skills or tools in each bullet with
  \\textbf{...} so they stand out to the recruiter. Example:
    Engineered \\textbf{C++ edge computing} pipelines achieving \\textbf{99\\%} uptime.
- Skills section: reorder and rewrite to put JD-required skills first.
  Add all necessary JD-required skills that are plausibly supported by the resume context.
  Keep the same category labels.

WHAT YOU MUST NEVER CHANGE
- Employment dates (e.g. Aug 2025 – Present)
- Job titles (e.g. Software Engineer)
- Company names and locations
- Education degrees, institutions, dates
- Certifications

Key Pitfalls to Avoid while rewriting experience bullets:
  - Listing Too Many Tools Without Context: Don't just dump 30 technologies in a skills block. Ensure the heavy-hitting languages are highlighted with context.
  - Vague Quantifications: Avoid filler metrics like "increased productivity by 100%" without explaining how it was measured or achieved.
  - Ignoring Core CS Fundamentals: Make sure your language proficiency (e.g., Python, C++, Java, Go) and system design/architecture strengths are instantly recognizable within 3 seconds.

LATEX ESCAPING RULES (critical — violations break the PDF)
- Percent sign: always write \\% not %. Example: 40\\%, 99\\%, 35\\%.
- Ampersand in text: always write \\& not &.
- All bullets must be complete sentences ending with a period.
- Never end a bullet mid-sentence.

JSON OUTPUT ESCAPING (critical)
In JSON string values, a backslash must be written as two backslashes.
So to produce \\textbf{term} in LaTeX, write \\textbf{term} inside your JSON string.
To produce \\%, write \\% inside your JSON string.

OUTPUT FORMAT
Return a single JSON object with exactly these keys:
{
  "professional_summary": "<string>",
  "experience_bullets": {
    "<Job Title @ Company>": ["<bullet>", ...]
  },
  "skills": {
    "<Category label>": "<comma-separated skills string>"
  },
  "project_bullets": {
    "<Project Name>": ["<bullet>", ...]
  }
}

No extra keys. No markdown. No explanation. JSON only.
""".strip()

# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_user_prompt(
    jd: str,
    summary: str,
    experience_blocks: List[Dict[str, Any]],
    skills_blocks: List[Dict[str, str]],
    project_blocks: List[Dict[str, Any]],
    additional_information: Optional[str],
) -> str:
    parts = ["=== JOB DESCRIPTION ===", jd.strip(), ""]

    if additional_information and additional_information.strip():
        parts += ["=== ADDITIONAL INSTRUCTIONS FROM USER ===",
                  additional_information.strip(), ""]

    parts += ["=== CURRENT RESUME SECTIONS ===", ""]

    parts += ["--- Professional Summary ---", summary.strip(), ""]

    for block in experience_blocks:
        label = block["label"]
        bullets = block["bullets"]
        parts.append(f"--- Experience: {label} ---")
        for b in bullets:
            parts.append(f"  • {b}")
        parts.append("")

    for block in skills_blocks:
        label = block["label"]
        content = block["content"]
        parts.append(f"--- Skills: {label} ---")
        parts.append(f"  {content}")
        parts.append("")

    for block in project_blocks:
        label = block["label"]
        bullets = block["bullets"]
        parts.append(f"--- Project: {label} ---")
        for b in bullets:
            parts.append(f"  • {b}")
        parts.append("")

    parts.append("Return the JSON object now.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class GPTAdapter:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1")
        self.timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "360"))

        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to your .env file."
            )

    def tailor(
        self,
        jd: str,
        summary: str,
        experience_blocks: List[Dict[str, Any]],
        skills_blocks: List[Dict[str, str]],
        project_blocks: Optional[List[Dict[str, Any]]] = None,
        additional_information: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send the resume sections + JD to GPT and return a structured dict.
        Raises RuntimeError on API failure or invalid JSON response.
        """
        user_prompt = _build_user_prompt(
            jd=jd,
            summary=summary,
            experience_blocks=experience_blocks,
            skills_blocks=skills_blocks,
            project_blocks=project_blocks or [],
            additional_information=additional_information,
        )

        payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }

        primary_token_param = (
            "max_completion_tokens"
            if self.model.startswith("gpt-5")
            else "max_tokens"
        )
        fallback_token_param = (
            "max_tokens"
            if primary_token_param == "max_completion_tokens"
            else "max_completion_tokens"
        )

        timeout = httpx.Timeout(
            connect=30.0,
            read=self.timeout_seconds,
            write=30.0,
            pool=30.0,
        )

        def _send_request(user_content: str) -> str:
            for token_param in (primary_token_param, fallback_token_param):
                local_payload = dict(payload)
                local_payload["messages"] = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ]
                local_payload[token_param] = 32768

                response = None
                for attempt in range(2):
                    try:
                        response = httpx.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json",
                            },
                            json=local_payload,
                            timeout=timeout,
                        )
                        break
                    except httpx.ReadTimeout as exc:
                        # Retry once for transient slow responses on long generations.
                        if attempt == 0:
                            continue
                        raise RuntimeError(
                            "OpenAI request timed out while waiting for model output. "
                            f"Increase OPENAI_TIMEOUT_SECONDS (current={self.timeout_seconds:.0f}) "
                            "or reduce response size."
                        ) from exc
                    except httpx.RequestError as exc:
                        raise RuntimeError(f"OpenAI request failed: {exc}") from exc

                if response is None:
                    raise RuntimeError("OpenAI request failed before receiving a response.")

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    body = exc.response.text or ""
                    if (
                        exc.response.status_code == 400
                        and "Unsupported parameter" in body
                        and token_param in body
                        and token_param == primary_token_param
                    ):
                        # This model expects the alternate token parameter.
                        continue
                    raise RuntimeError(
                        f"OpenAI API error {exc.response.status_code}: "
                        f"{body[:400]}"
                    ) from exc

                try:
                    return response.json()["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as exc:
                    raise RuntimeError("OpenAI response format was unexpected.") from exc

            raise RuntimeError("OpenAI request failed due to token parameter incompatibility.")

        def _parse_json_safely(raw_text: str) -> Dict[str, Any]:
            # GPT sometimes writes bare LaTeX backslashes (e.g. \textbf) instead
            # of JSON-required escaped backslashes (\\textbf). In JSON, \t is a
            # tab, \n is newline, etc., so bare LaTeX commands get mangled.
            fixed_text = re.sub(r'(?<!\\)\\(?=[a-zA-Z%&_^#{}])', r'\\\\', raw_text)
            return json.loads(fixed_text)

        raw_text = _send_request(user_prompt)
        try:
            return _parse_json_safely(raw_text)
        except json.JSONDecodeError:
            # One automatic regeneration attempt with tighter size constraints.
            retry_prompt = (
                user_prompt
                + "\n\nIMPORTANT RETRY RULES:\n"
                  "- Your previous output was invalid/truncated JSON.\n"
                  "- Regenerate from scratch and return ONLY compact valid JSON.\n"
                  "- Keep professional_summary <= 320 characters.\n"
                  "- Keep each bullet concise (target <= 220 characters).\n"
                                    "- Preserve requested bullet-count changes from ADDITIONAL INSTRUCTIONS."
            )
            retry_raw_text = _send_request(retry_prompt)
            try:
                return _parse_json_safely(retry_raw_text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"GPT returned invalid JSON: {retry_raw_text[:300]}"
                ) from exc
