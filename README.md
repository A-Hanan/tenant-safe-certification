# Django Approval Sample

A small multi-tenant approval API built with Django, DRF, and PostgreSQL, plus a
Python PR guard running in GitHub Actions. All data is synthetic. This is a sample,
not a production-ready platform.

**An agent is another principal in the permission model.** Humans cannot review
their own requests or requests they previously acted on. Agent principals cannot
create, submit, approve, or reject requests, even with the corresponding role.
The [human and agent refusal tests](tests/approvals/test_separation_of_duties.py)
show these checks side by side. The PR guard has separate GitHub credentials,
no application credentials, and no merge rights.

## Quick start

Requires Git, Docker Compose v2, and Bash with OpenSSL and curl. On Windows, use
PowerShell for Git and WSL for Docker and Bash commands. Python 3.12, PostgreSQL 16,
and pinned Python dependencies run in containers.

Clone with Git (PowerShell on Windows):

```text
git clone https://github.com/A-Hanan/tenant-safe-certification.git
```

In Bash/WSL, enter the cloned directory, then run:

```bash
cp .env.example .env
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
docker compose up --build -d
docker compose ps
docker compose exec web python manage.py check
docker compose exec web python manage.py seed_demo
```

Wait for startup migrations before using the API. If it is not ready, inspect
`docker compose logs web` and retry the last two commands. The example environment
enables debug mode and local development credentials; do not use it publicly.
Settings otherwise default to debug off and require a secret and database URL.

The idempotent seed command requires debug mode. It creates two schools, one lender,
role users, and an agent, and prints local tokens. It creates no approval requests.
Copy the token for `demo-school-a-submitter` when prompted:

```bash
read -r -s -p 'Demo School A submitter token: ' DEMO_TOKEN
printf '\n'
curl --fail-with-body -sS \
  -H "Authorization: Token $DEMO_TOKEN" \
  "http://127.0.0.1:${WEB_PORT:-8000}/api/v1/institutions/00000000-0000-4000-8000-000000000001/approvals/"
unset DEMO_TOKEN
```

A fresh database returns a paginated response with `count: 0` and `results: []`.
There is no frontend or root-page endpoint.
Stop with `docker compose down`; the named database volume persists.
For a second checkout, export a distinct `COMPOSE_PROJECT_NAME` and unused
`WEB_PORT` before starting Compose.

## Tests and checks

Compose copies source into the image: rebuild after edits. Tests use PostgreSQL.

```bash
docker compose build web
docker compose run --rm web ruff check .
docker compose run --rm web ruff format --check .
docker compose run --rm web python manage.py makemigrations --check --dry-run
docker compose run --rm web sh -c 'coverage run --source=approvals,institutions -m pytest && coverage report'
docker compose run --rm web bandit -r accounts agents approvals config institutions manage.py
docker compose run --rm web python -m pip_audit -r requirements-dev.txt
docker compose run --rm web python -m pip check
```

Run the core human/agent refusal tests alone:

```bash
docker compose run --rm web pytest tests/approvals/test_separation_of_duties.py -v
```

Formatting or migration generation requires a workspace mount to preserve output,
for example `docker compose run --rm --volume "$PWD:/app" web ruff format .`.

## Workflow and API

| From | Action | To | Required actor |
|---|---|---|---|
| draft | submit | pending | Human creator with active submitter membership |
| pending | approve | approved | Human active approver with no prior involvement |
| pending | reject | rejected | Human active approver with no prior involvement |

Authorized actors attempting other transitions receive `409`; permission checks
run first. Refusals do not change status or write audit events. Human active
submitters can create drafts. Money is integer cents.

Under `/api/v1/institutions/<institution_id>/approvals/`, the collection supports
`GET` and `POST`; detail supports `GET`; detail actions `submit/`, `approve/`,
and `reject/` support `POST`. `PUT`, `PATCH`, and `DELETE` return `405` for
accessible records. Authentication uses DRF tokens. Non-members and cross-tenant
lookups receive `404`, unauthenticated requests `401`, permission refusals `403`,
invalid transitions `409`, and invalid input `400`.

## Where the five goals are demonstrated

| Goal | Implementation and evidence |
|---|---|
| Institution isolation | [Scoped views](approvals/api/views.py), [membership lookup](institutions/models.py), [tenant isolation and route inventory tests](tests/approvals/test_tenant_isolation.py) |
| Permissions on approval actions | [Guarded services](approvals/services.py), [permission matrix](tests/approvals/test_transition_matrix.py), [human and agent refusals](tests/approvals/test_separation_of_duties.py) |
| No skipped steps | [Transition table](approvals/transitions.py), [state matrix tests](tests/approvals/test_transition_matrix.py) |
| Tests prove the boundaries | [Approval tests](tests/approvals), [institution tests](tests/institutions), [CI](.github/workflows/ci.yml) |
| Flag guarded PR changes without mapped tests | [Mappings](agents/guarded_paths.toml), [pure evaluator](agents/rules.py), [agent tests](tests/agents), [PR workflow](.github/workflows/pr-guard.yml) |

## Key decisions

- A shared base view resolves active membership, then scopes querysets, including
  lists. Object permissions alone would not scope a list.
- Services own permissions and state changes for HTTP and non-HTTP callers.
  Institution, status, creator, and audit actor come from the server.
- A transition locks the request before checking its state. Status and audit writes
  share a transaction, so an audit failure rolls back the status change.
- Separation of duties checks the creator and audit history. Changing someone's
  current role cannot erase prior involvement.
- The PR verdict is deterministic. A mapped test change clears a finding; the LLM
  can only explain it, not decide whether it clears.

## PR guard

The standard-library agent reads all PR file pages, checks both names on renames,
and excludes deleted tests from clearing findings. Incomplete or changing lists
raise an error. It maintains one marker-bearing `github-actions[bot]` comment,
updates it when findings clear, and posts nothing if no finding ever existed.

The workflow runs on opened, updated, and reopened PRs using base-commit code.
It has a five-minute timeout and serializes runs for each PR. Findings are advisory;
execution failures fail the job. The initial PR introducing the agent records
`not_evaluated` because its base predates the agent.

For Anthropic explanations, configure repository Actions secret `LLM_API_KEY`
and variables `LLM_MODEL`, `LLM_INPUT_COST_PER_MTOK`, and
`LLM_OUTPUT_COST_PER_MTOK`, using the selected model's USD-per-million-token rates.
Optional `LLM_MAX_INPUT_CHARS` and `LLM_MAX_OUTPUT_TOKENS` default to 6000 and 220.

Only flagged runs call the LLM: one call, no retries or tools, with a 20-second
socket timeout. Input contains filenames, rule IDs, and truncated patches marked
as untrusted. Output is capped, mentions neutralized, and the comment marker
removed. Missing configuration or provider errors preserve the deterministic
comment. A provider-side spending limit adds an account-level boundary.

The uploaded `artifacts/pr-guard.json` records files, rules, test matches, LLM usage,
estimated cost, fallback reason, and verdict, excluding keys and patch contents.
Usage and cost stay unknown when a failed call returns no usage data.

Run the orchestration locally with a synthetic payload and mocked GitHub responses,
without credentials or network requests:

```bash
mkdir -p artifacts
docker compose run --rm --no-deps --volume "$PWD/artifacts:/app/artifacts" web python -m tests.agents.run_sample
```

Expect `flagged`, `missing_api_key`, no LLM call, and a local JSON log. This does
not verify live GitHub permissions or Anthropic credentials.

## Limits and next steps

- A mapped test changing does not prove it covers the change. The guard cannot
  judge test quality, catch every permission bug, or inspect unguarded paths.
  Review-time savings need measurement in real use.
- QuerySet updates, bulk operations, and raw SQL can bypass services and model
  methods. Audit immutability is application-level, without database triggers.
- Tenant scoping is application-level, without PostgreSQL row-level security.
  School and lender are categories; each institution ID is a separate boundary.
  Cross-institution grants are not implemented.
- The GitHub token has `contents: read`, `pull-requests: write`, and `issues: write`.
  PR write access is needed for comment posting in this integration; it also grants
  broader PR-management capabilities, so it is not a comment-only permission.
  The agent only uses it to manage its comment. It lacks the `contents: write`
  permission required by the merge endpoint. A same-repository PR can still edit
  the workflow itself; production needs branch protection and code owners.
- Fork PR tokens normally cannot post comments or access LLM secrets. A failed
  comment write fails the job. The live demo uses a same-repository PR.
- Production next steps include row-level security, database audit and status
  enforcement, concurrency tests, MFA, and production authentication/deployment
  settings. Durable background jobs, exports, and a UI are outside this sample.

## AI use and review

I used Codex to help implement the sample, write tests, and draft documentation.
I ran the Docker-based verification, including a fresh-clone setup, and checked
the test, lint, migration, and security-check results. The tests demonstrate
specific behaviors; they do not replace a full code review or establish production
readiness.
