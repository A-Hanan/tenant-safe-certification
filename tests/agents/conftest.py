import json

import pytest


@pytest.fixture
def anthropic_http(monkeypatch):
    calls = []
    responses = []

    class Connection:
        def __init__(self, host, timeout):
            assert host == "api.anthropic.com"
            assert timeout == 20

        def request(self, method, path, headers, body):
            calls.append((method, path, headers, json.loads(body)))

        def getresponse(self):
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response

            class Response:
                status = response[0]

                def read(self, limit):
                    raw = response[1]
                    if not isinstance(raw, bytes):
                        raw = json.dumps(raw).encode()
                    return raw[:limit]

            return Response()

        def close(self):
            pass

    monkeypatch.setattr("agents.explain.HTTPSConnection", Connection)
    return responses, calls


@pytest.fixture
def llm_env():
    return {
        "LLM_API_KEY": "synthetic-key",
        "LLM_MODEL": "synthetic-model",
        "LLM_INPUT_COST_PER_MTOK": "1",
        "LLM_OUTPUT_COST_PER_MTOK": "5",
    }


@pytest.fixture
def provider_response():
    return {
        "content": [{"type": "text", "text": "Add a matching permission test."}],
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }
