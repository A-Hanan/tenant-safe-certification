from decimal import Decimal

import pytest

from agents.explain import (
    MAX_EXPLANATION_CHARS,
    SYSTEM_PROMPT,
    build_input,
    explain_findings,
    sanitize_output,
)
from agents.github import COMMENT_MARKER
from agents.rules import ChangedFile, Finding

FILES = (ChangedFile("approvals/services.py", "modified", patch="+synthetic change"),)
FINDINGS = (
    Finding("approval-logic", ("approvals/services.py",), ("tests/example.py",)),
)


def test_request_is_single_bounded_call(llm_env, anthropic_http, provider_response):
    responses, calls = anthropic_http
    responses.append((200, provider_response))

    result = explain_findings(files=FILES, findings=FINDINGS, env=llm_env)

    assert len(calls) == 1
    method, path, headers, body = calls[0]
    assert (method, path) == ("POST", "/v1/messages")
    assert headers["x-api-key"] == "synthetic-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert set(body) == {"model", "max_tokens", "thinking", "system", "messages"}
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] == 220
    assert body["model"] == "synthetic-model"
    assert "untrusted" in body["system"]
    assert len(body["system"] + body["messages"][0]["content"]) <= 6000
    assert result.called is True
    assert result.fallback_reason is None
    assert (result.input_tokens, result.output_tokens) == (100, 20)
    assert Decimal(result.estimated_cost_usd) == Decimal("0.0002")


@pytest.mark.parametrize(
    ("env", "findings", "reason"),
    [
        ({}, FINDINGS, "missing_api_key"),
        ({"LLM_API_KEY": "key"}, FINDINGS, "missing_model"),
        ({}, (), None),
    ],
)
def test_no_call_when_unneeded_or_unconfigured(anthropic_http, env, findings, reason):
    _, calls = anthropic_http

    result = explain_findings(files=FILES, findings=findings, env=env)

    assert calls == []
    assert result.called is False
    assert result.fallback_reason == reason
    assert result.estimated_cost_usd == "0"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LLM_MAX_INPUT_CHARS", "1"),
        ("LLM_MAX_OUTPUT_TOKENS", "0"),
        ("LLM_MAX_OUTPUT_TOKENS", "invalid"),
        ("LLM_INPUT_COST_PER_MTOK", ""),
        ("LLM_INPUT_COST_PER_MTOK", "NaN"),
        ("LLM_OUTPUT_COST_PER_MTOK", "Infinity"),
        ("LLM_OUTPUT_COST_PER_MTOK", "-1"),
    ],
)
def test_invalid_configuration_skips_call(llm_env, anthropic_http, name, value):
    _, calls = anthropic_http
    llm_env[name] = value

    result = explain_findings(files=FILES, findings=FINDINGS, env=llm_env)

    assert result.fallback_reason == "invalid_llm_configuration"
    assert calls == []


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (TimeoutError(), "timeout"),
        (OSError("secret error detail"), "provider_error"),
        ((429, {}), "provider_http_429"),
        ((500, {}), "provider_http_500"),
        ((302, {}), "provider_http_302"),
        ((200, b"not JSON"), "invalid_provider_response"),
        ((200, b"x" * 65537), "invalid_provider_response"),
        ((200, {}), "invalid_provider_response"),
    ],
)
def test_provider_failures_do_not_retry(llm_env, anthropic_http, response, reason):
    responses, calls = anthropic_http
    responses.append(response)

    result = explain_findings(files=FILES, findings=FINDINGS, env=llm_env)

    assert len(calls) == 1
    assert result.called is True
    assert result.text is None
    assert result.fallback_reason == reason
    assert result.estimated_cost_usd is None
    assert "secret" not in repr(result)


@pytest.mark.parametrize("value", [-1, True, "100"])
def test_invalid_usage_falls_back(llm_env, anthropic_http, provider_response, value):
    responses, _ = anthropic_http
    provider_response["usage"]["input_tokens"] = value
    responses.append((200, provider_response))

    result = explain_findings(files=FILES, findings=FINDINGS, env=llm_env)

    assert result.fallback_reason == "invalid_provider_response"
    assert result.estimated_cost_usd is None


def test_empty_explanation_keeps_known_cost(llm_env, anthropic_http, provider_response):
    responses, _ = anthropic_http
    provider_response["content"] = []
    responses.append((200, provider_response))

    result = explain_findings(files=FILES, findings=FINDINGS, env=llm_env)

    assert result.fallback_reason == "invalid_provider_response"
    assert Decimal(result.estimated_cost_usd) == Decimal("0.0002")


def test_input_cap_includes_prompt_and_all_file_data():
    files = tuple(
        ChangedFile(f"file-{i}.py", "modified", patch="x" * 10000) for i in range(3)
    )

    content = build_input(files, FINDINGS, max_chars=6000)

    assert len(SYSTEM_PROMPT + content) == 6000
    assert content.startswith("UNTRUSTED PR DATA")
    assert "approval-logic" in content
    assert "status" not in content


def test_output_sanitizes_marker_mentions_html_and_length():
    result = sanitize_output(COMMENT_MARKER + "@team <script>" + "x" * 3000)

    assert COMMENT_MARKER not in result
    assert "@" not in result
    assert "<script>" not in result
    assert "＠team &lt;script&gt;" in result
    assert len(result) == MAX_EXPLANATION_CHARS


def test_custom_caps_are_used(llm_env, anthropic_http, provider_response):
    responses, calls = anthropic_http
    llm_env.update(LLM_MAX_INPUT_CHARS="1000", LLM_MAX_OUTPUT_TOKENS="50")
    responses.append((200, provider_response))

    explain_findings(files=FILES, findings=FINDINGS, env=llm_env)

    body = calls[0][3]
    assert body["max_tokens"] == 50
    assert len(body["system"] + body["messages"][0]["content"]) <= 1000
