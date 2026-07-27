"""
Step 2 tests — GPT adapter.
All tests use mocks so no real API calls are made.
Run: python -m pytest tests/test_gpt_adapter.py -v
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from app.services.gpt_adapter import GPTAdapter, SYSTEM_PROMPT, _build_user_prompt

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_JD = """
We are looking for a Backend Engineer with strong Python and FastAPI skills.
Must have experience with AI models, prompt engineering, system design,
and cloud deployments on AWS.
"""

SAMPLE_SUMMARY = (
    "Software Engineer with 3+ years of experience developing scalable "
    "applications, APIs, and enterprise integrations."
)

SAMPLE_EXPERIENCE = [
    {
        "label": "Software Engineer @ IPSER LAB LLC",
        "bullets": [
            "Led system design for a real estate application.",
            "Collaborated with product and UX teams using gRPC.",
            "Engineered CI/CD processes via Jenkins pipelines.",
        ],
    },
    {
        "label": "Software Engineer @ Enertech Technology",
        "bullets": [
            "Spearheaded development of distributed systems.",
            "Designed gRPC/Protobuf APIs alongside RESTful services.",
        ],
    },
]

SAMPLE_SKILLS = [
    {"label": "Languages", "content": "Python, Java, SQL, JavaScript"},
    {"label": "Frameworks & Tools", "content": "FastAPI, Spring Boot, React"},
    {"label": "Cloud & Data", "content": "AWS, Docker, Kubernetes"},
]

SAMPLE_GPT_RESPONSE = {
    "professional_summary": (
        "Results-driven Backend Engineer with 3+ years of experience "
        "building scalable Python/FastAPI applications and AI-powered services "
        "on AWS. Expert in system design, prompt engineering, and cloud deployments."
    ),
    "experience_bullets": {
        "Software Engineer @ IPSER LAB LLC": [
            "Architected FastAPI-based microservices and AI agent pipelines on AWS EC2.",
            "Led cross-functional teams using Python and gRPC for high-performance backends.",
            "Automated CI/CD workflows via Jenkins, reducing deployment time by 30%.",
        ],
        "Software Engineer @ Enertech Technology": [
            "Designed distributed Python backend systems processing 35% faster.",
            "Built gRPC/Protobuf APIs serving 10,000+ daily financial transactions.",
        ],
    },
    "skills": {
        "Languages": "Python, SQL, Java, JavaScript",
        "Frameworks & Tools": "FastAPI, gRPC, Spring Boot, React, Pytest",
        "Cloud & Data": "AWS (EC2, S3, Lambda), Docker, Kubernetes",
    },
    "project_bullets": {},
}


def make_mock_response(data: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(data)}}]
    }
    return mock_resp


# ---------------------------------------------------------------------------
# Prompt builder tests (no network needed)
# ---------------------------------------------------------------------------

def test_user_prompt_contains_jd():
    prompt = _build_user_prompt(
        jd=SAMPLE_JD,
        summary=SAMPLE_SUMMARY,
        experience_blocks=SAMPLE_EXPERIENCE,
        skills_blocks=SAMPLE_SKILLS,
        project_blocks=[],
        additional_information=None,
    )
    assert "FastAPI" in prompt
    assert "Python" in prompt
    assert "AWS" in prompt


def test_user_prompt_contains_summary():
    prompt = _build_user_prompt(
        jd=SAMPLE_JD,
        summary=SAMPLE_SUMMARY,
        experience_blocks=SAMPLE_EXPERIENCE,
        skills_blocks=SAMPLE_SKILLS,
        project_blocks=[],
        additional_information=None,
    )
    assert SAMPLE_SUMMARY[:30] in prompt


def test_user_prompt_contains_experience_labels():
    prompt = _build_user_prompt(
        jd=SAMPLE_JD,
        summary=SAMPLE_SUMMARY,
        experience_blocks=SAMPLE_EXPERIENCE,
        skills_blocks=SAMPLE_SKILLS,
        project_blocks=[],
        additional_information=None,
    )
    assert "IPSER LAB LLC" in prompt
    assert "Enertech Technology" in prompt


def test_user_prompt_includes_additional_information():
    prompt = _build_user_prompt(
        jd=SAMPLE_JD,
        summary=SAMPLE_SUMMARY,
        experience_blocks=SAMPLE_EXPERIENCE,
        skills_blocks=SAMPLE_SKILLS,
        project_blocks=[],
        additional_information="Emphasize AI and prompt engineering experience.",
    )
    assert "Emphasize AI" in prompt


def test_user_prompt_skips_empty_additional_information():
    prompt = _build_user_prompt(
        jd=SAMPLE_JD,
        summary=SAMPLE_SUMMARY,
        experience_blocks=SAMPLE_EXPERIENCE,
        skills_blocks=SAMPLE_SKILLS,
        project_blocks=[],
        additional_information="",
    )
    assert "ADDITIONAL INSTRUCTIONS" not in prompt


def test_system_prompt_contains_key_rules():
    assert "NEVER CHANGE" in SYSTEM_PROMPT
    assert "Employment dates" in SYSTEM_PROMPT
    assert "professional_summary" in SYSTEM_PROMPT
    assert "experience_bullets" in SYSTEM_PROMPT
    assert "JSON only" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Adapter tests (mocked HTTP)
# ---------------------------------------------------------------------------

def test_adapter_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        GPTAdapter(api_key=None)


def test_adapter_returns_structured_dict(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    adapter = GPTAdapter()
    with patch("app.services.gpt_adapter.httpx.post") as mock_post:
        mock_post.return_value = make_mock_response(SAMPLE_GPT_RESPONSE)
        result = adapter.tailor(
            jd=SAMPLE_JD,
            summary=SAMPLE_SUMMARY,
            experience_blocks=SAMPLE_EXPERIENCE,
            skills_blocks=SAMPLE_SKILLS,
        )
    assert "professional_summary" in result
    assert "experience_bullets" in result
    assert "skills" in result
    assert "project_bullets" in result


def test_adapter_summary_is_string(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    adapter = GPTAdapter()
    with patch("app.services.gpt_adapter.httpx.post") as mock_post:
        mock_post.return_value = make_mock_response(SAMPLE_GPT_RESPONSE)
        result = adapter.tailor(
            jd=SAMPLE_JD,
            summary=SAMPLE_SUMMARY,
            experience_blocks=SAMPLE_EXPERIENCE,
            skills_blocks=SAMPLE_SKILLS,
        )
    assert isinstance(result["professional_summary"], str)
    assert len(result["professional_summary"]) > 20


def test_adapter_experience_bullets_per_job(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    adapter = GPTAdapter()
    with patch("app.services.gpt_adapter.httpx.post") as mock_post:
        mock_post.return_value = make_mock_response(SAMPLE_GPT_RESPONSE)
        result = adapter.tailor(
            jd=SAMPLE_JD,
            summary=SAMPLE_SUMMARY,
            experience_blocks=SAMPLE_EXPERIENCE,
            skills_blocks=SAMPLE_SKILLS,
        )
    bullets = result["experience_bullets"]
    # First job had 3 original bullets — GPT must return 3
    first_job_key = list(bullets.keys())[0]
    assert len(bullets[first_job_key]) == 3
    # Second job had 2 original bullets — GPT must return 2
    second_job_key = list(bullets.keys())[1]
    assert len(bullets[second_job_key]) == 2


def test_adapter_sends_json_format_request(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")
    adapter = GPTAdapter()
    with patch("app.services.gpt_adapter.httpx.post") as mock_post:
        mock_post.return_value = make_mock_response(SAMPLE_GPT_RESPONSE)
        adapter.tailor(
            jd=SAMPLE_JD,
            summary=SAMPLE_SUMMARY,
            experience_blocks=SAMPLE_EXPERIENCE,
            skills_blocks=SAMPLE_SKILLS,
        )
    call_payload = mock_post.call_args.kwargs["json"]
    assert call_payload["response_format"] == {"type": "json_object"}
    assert call_payload["model"] == "gpt-4.1"


def test_adapter_raises_on_invalid_json(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    adapter = GPTAdapter()
    bad_response = MagicMock()
    bad_response.raise_for_status = MagicMock()
    bad_response.json.return_value = {
        "choices": [{"message": {"content": "not valid json {"}}]
    }
    with patch("app.services.gpt_adapter.httpx.post", return_value=bad_response):
        with pytest.raises(RuntimeError, match="invalid JSON"):
            adapter.tailor(
                jd=SAMPLE_JD,
                summary=SAMPLE_SUMMARY,
                experience_blocks=SAMPLE_EXPERIENCE,
                skills_blocks=SAMPLE_SKILLS,
            )
