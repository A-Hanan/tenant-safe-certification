import json
from pathlib import Path
from unittest.mock import patch

from agents.main import run


def main() -> None:
    payload = json.loads(
        Path(__file__).with_name("sample_pr.json").read_text(encoding="utf-8")
    )
    number = payload["pr_number"]
    files = payload["files"]
    metadata = {
        "changed_files": len(files),
        "head": {"sha": "synthetic-head"},
        "base": {"sha": "synthetic-base"},
    }
    requests = [
        ("GET", f"/pulls/{number}", metadata),
        ("GET", f"/pulls/{number}/files?per_page=100&page=1", files),
        ("GET", f"/pulls/{number}", metadata),
        ("GET", f"/issues/{number}/comments?per_page=100&page=1", []),
        ("POST", f"/issues/{number}/comments", {"id": 1}),
    ]
    comments = []

    def request(method, path, body=None):
        expected_method, expected_path, response = requests.pop(0)
        assert (method, path) == (expected_method, expected_path)
        if method == "POST":
            comments.append(body["body"])
        return response

    env = {
        "PR_NUMBER": str(number),
        "GITHUB_RUN_ID": "local-sample",
        "GITHUB_TOKEN": "synthetic-unused-token",
        "GITHUB_REPOSITORY": "example/sample",
    }
    with (
        patch("agents.github.GitHubClient._request", side_effect=request),
        patch(
            "agents.explain.HTTPSConnection", side_effect=AssertionError("No network")
        ),
    ):
        result = run(env=env)

    assert requests == []
    assert result["verdict"] == "flagged"
    assert result["rules_fired"] == ["approval-logic"]
    assert result["fallback_reason"] == "missing_api_key"
    assert result["llm_called"] is False
    assert result["comment_action"] == "created"
    assert len(comments) == 1
    assert "approval-logic" in comments[0]
    print("Sample verified: flagged, deterministic comment, no LLM call.")
    print(comments[0])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
