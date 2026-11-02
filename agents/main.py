import json
import os
import sys
from collections.abc import Mapping
from fnmatch import fnmatchcase
from pathlib import Path

from agents.explain import explain_findings, sanitize_output
from agents.github import GitHubClient, GitHubError
from agents.rules import Finding, evaluate_rules, load_rules


def finding_comment(findings: tuple[Finding, ...]) -> str:
    lines = [
        "## PR guard: matching test changes missing",
        "",
        "This is a deterministic, advisory finding. A matching test change "
        "does not prove the test is adequate.",
    ]
    for finding in findings:
        lines.extend(
            [
                "",
                f"Rule: {finding.rule_id}",
                "Guarded paths changed:",
                *[f"- {sanitize_output(path)}" for path in finding.guarded_files],
                "Expected a change to at least one of:",
                *[f"- {sanitize_output(path)}" for path in finding.expected_tests],
            ]
        )
    return "\n".join(lines)


def run(
    *, env: Mapping[str, str], log_path: Path = Path("artifacts/pr-guard.json")
) -> dict:
    log = {
        "run_id": env.get("GITHUB_RUN_ID", "local"),
        "pr_number": None,
        "files_checked": [],
        "rules_fired": [],
        "test_matches": {},
        "llm_called": False,
        "tokens": {"input": 0, "output": 0},
        "estimated_cost_usd": "0",
        "fallback_reason": None,
        "verdict": "error",
        "error": None,
    }
    try:
        pr_number = int(env["PR_NUMBER"])
        log["pr_number"] = pr_number
        client = GitHubClient(
            token=env["GITHUB_TOKEN"], repository=env["GITHUB_REPOSITORY"]
        )
        rules = load_rules()
        files = client.list_pr_files(pr_number)
        log["files_checked"] = [file.filename for file in files]
        findings = evaluate_rules(files, rules=rules)
        log["rules_fired"] = [finding.rule_id for finding in findings]
        log["test_matches"] = {
            rule.id: any(
                file.status != "removed" and fnmatchcase(file.filename, pattern)
                for file in files
                for pattern in rule.tests
            )
            for rule in rules
        }
        explanation = explain_findings(files=files, findings=findings, env=env)
        log.update(
            {
                "llm_called": explanation.called,
                "tokens": {
                    "input": explanation.input_tokens,
                    "output": explanation.output_tokens,
                },
                "estimated_cost_usd": explanation.estimated_cost_usd,
                "fallback_reason": explanation.fallback_reason,
            }
        )
        body = finding_comment(findings) if findings else None
        if body is not None and explanation.text:
            body += "\n\n### AI explanation (advisory)\n\n"
            body += "\n".join(f"> {line}" for line in explanation.text.splitlines())
        log["comment_action"] = client.upsert_comment(pr_number, finding_body=body)
        log["verdict"] = "flagged" if findings else "clear"
        return log
    except Exception as error:
        # Exception text may contain credentials or response bodies; never log it.
        log["error"] = "agent_run_failed"
        log["error_type"] = type(error).__name__
        if isinstance(error, GitHubError):
            log["github_http_status"] = error.status
            log["github_method"] = error.method
        raise
    finally:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    try:
        run(env=os.environ)
    except Exception:
        print("PR guard failed; inspect the run log.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
