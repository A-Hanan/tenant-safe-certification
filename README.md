# Django Approval Sample
A small multi-tenant approval workflow sample built with Django and Django REST Framework; all data is synthetic.

## PR guard

The PR guard runs on opened, updated, and reopened pull requests. It checks out
the base commit so the agent and rules come from the base branch, not the PR.
It uses Python 3.12's standard library without installing application dependencies.
Findings are advisory; execution failures fail the job. Each run uploads a JSON log.
Runs for one PR are serialized to reduce competing comment updates.

The initial PR introducing the agent has neither the agent nor this workflow in
its base commit. That bootstrap run records `not_evaluated`, not a clear verdict.
The agent starts evaluating subsequent PRs after this PR merges.

For optional Anthropic explanations, configure the repository Actions secret
`LLM_API_KEY` and Actions variables `LLM_MODEL`, `LLM_INPUT_COST_PER_MTOK`, and
`LLM_OUTPUT_COST_PER_MTOK`. Use the selected model's USD-per-million-token rates.
Optional variables `LLM_MAX_INPUT_CHARS` and `LLM_MAX_OUTPUT_TOKENS` default to
6000 and 220. Missing configuration leaves deterministic findings available.

A same-repository PR could still edit the workflow file itself. For production,
branch protection and code owners would cover this. The token grants only
`contents: read`, `pull-requests: read`, and `issues: write`; it has no merge rights.
Fork PR tokens normally cannot write comments and do not receive the LLM secret.
This sample does not grant extra privileges to bypass that restriction; a failed
comment write fails the job. The live demo uses a same-repository PR.

For a local synthetic run without credentials or network requests, rebuild the
Compose image and run:

```bash
docker compose build web
mkdir -p artifacts
docker compose run --rm --no-deps --volume "$PWD/artifacts:/app/artifacts" web python -m tests.agents.run_sample
```

This runs the real orchestration with mocked GitHub responses, checks the flagged
verdict and missing-key fallback, and writes `artifacts/pr-guard.json` locally.
It does not verify real GitHub permissions or Anthropic credentials.
