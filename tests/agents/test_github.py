import json

import pytest

from agents.github import BOT_LOGIN, COMMENT_MARKER, GitHubClient, GitHubError
from agents.rules import ChangedFile


@pytest.fixture
def http(monkeypatch):
    responses = []
    calls = []

    class Connection:
        def __init__(self, host, timeout):
            assert host == "api.github.com"
            assert timeout == 20

        def request(self, method, path, body, headers):
            calls.append((method, path, json.loads(body) if body else None, headers))

        def getresponse(self):
            value = responses.pop(0)
            if isinstance(value, Exception):
                raise value

            class Response:
                status = value[0]

                def read(self):
                    if isinstance(value[1], bytes):
                        return value[1]
                    return json.dumps(value[1]).encode()

            return Response()

        def close(self):
            pass

    monkeypatch.setattr("agents.github.HTTPSConnection", Connection)
    return responses, calls


@pytest.fixture
def client():
    return GitHubClient(token="synthetic-token", repository="example/sample")


def metadata(count, head="head", base="base"):
    return {"changed_files": count, "head": {"sha": head}, "base": {"sha": base}}


def file(index):
    return {"filename": f"source/{index}.py", "status": "modified"}


def comment(identifier=7, login=BOT_LOGIN, body=COMMENT_MARKER):
    return {"id": identifier, "user": {"login": login}, "body": body}


def test_files_paginate_and_preserve_rename(client, http):
    responses, calls = http
    renamed = {
        "filename": "new.py",
        "status": "renamed",
        "previous_filename": "old.py",
    }
    responses.extend(
        [
            (200, metadata(101)),
            (200, [file(i) for i in range(100)]),
            (200, [renamed]),
            (200, metadata(101)),
        ]
    )

    result = client.list_pr_files(12)

    assert len(result) == 101
    assert result[-1] == ChangedFile("new.py", "renamed", "old.py")
    assert [call[1] for call in calls] == [
        "/repos/example/sample/pulls/12",
        "/repos/example/sample/pulls/12/files?per_page=100&page=1",
        "/repos/example/sample/pulls/12/files?per_page=100&page=2",
        "/repos/example/sample/pulls/12",
    ]
    assert calls[0][3]["Authorization"] == "Bearer synthetic-token"


def test_files_preserve_optional_patch(client, http):
    responses, _ = http
    row = {"filename": "source.py", "status": "modified", "patch": "+synthetic"}
    responses.extend([(200, metadata(1)), (200, [row]), (200, metadata(1))])

    assert client.list_pr_files(12) == (
        ChangedFile("source.py", "modified", patch="+synthetic"),
    )


@pytest.mark.parametrize("count", [0, 100])
def test_empty_and_exact_page_boundary(client, http, count):
    responses, _ = http
    responses.extend([(200, metadata(count)), (200, [file(i) for i in range(count)])])
    if count:
        responses.append((200, []))
    responses.append((200, metadata(count)))

    assert len(client.list_pr_files(12)) == count


@pytest.mark.parametrize(
    ("rows", "after"),
    [
        ([file(1)], metadata(2)),
        ([file(1), file(1)], metadata(2)),
        ([file(1), file(2)], metadata(2, head="new-head")),
        ([file(1), file(2)], metadata(2, base="new-base")),
        ([file(1), file(2)], metadata(3)),
    ],
)
def test_incomplete_or_changed_files_raise(client, http, rows, after):
    responses, _ = http
    responses.extend([(200, metadata(2)), (200, rows), (200, after)])

    with pytest.raises(GitHubError):
        client.list_pr_files(12)


def test_file_limit_raises_before_listing(client, http):
    responses, calls = http
    responses.append((200, metadata(3001)))

    with pytest.raises(GitHubError):
        client.list_pr_files(12)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "batch",
    [{"message": "invalid"}, [{}], [{"filename": "new.py", "status": "renamed"}]],
)
def test_invalid_file_response_raises(client, http, batch):
    responses, _ = http
    responses.extend([(200, metadata(1)), (200, batch)])

    with pytest.raises(GitHubError):
        client.list_pr_files(12)


@pytest.mark.parametrize(
    "failure", [(403, {}), (500, {}), (302, {}), (200, b"invalid json"), TimeoutError()]
)
def test_later_page_failure_never_returns_partial_files(client, http, failure):
    responses, _ = http
    responses.extend(
        [
            (200, metadata(101)),
            (200, [file(i) for i in range(100)]),
            failure,
        ]
    )

    with pytest.raises(GitHubError):
        client.list_pr_files(12)


def test_create_ignores_human_marker_and_unrelated_bot_comment(client, http):
    responses, calls = http
    responses.extend(
        [
            (200, [comment(login="someone"), comment(body="Other bot task")]),
            (201, {"id": 10}),
        ]
    )

    assert client.upsert_comment(12, finding_body="Missing a test") == "created"
    assert calls[-1][:3] == (
        "POST",
        "/repos/example/sample/issues/12/comments",
        {"body": f"{COMMENT_MARKER}\n\nMissing a test"},
    )


def test_comment_on_later_page_is_updated(client, http):
    responses, calls = http
    responses.extend(
        [
            (200, [comment(i, login="someone") for i in range(100)]),
            (200, [comment()]),
            (200, {}),
        ]
    )

    assert client.upsert_comment(12, finding_body="Still missing") == "updated"
    assert calls[1][1].endswith("comments?per_page=100&page=2")
    assert calls[-1][:3] == (
        "PATCH",
        "/repos/example/sample/issues/comments/7",
        {"body": f"{COMMENT_MARKER}\n\nStill missing"},
    )


def test_clear_existing_comment(client, http):
    responses, calls = http
    responses.extend([(200, [comment()]), (200, {})])

    assert client.upsert_comment(12, finding_body=None) == "updated"
    assert calls[-1][2] == {
        "body": f"{COMMENT_MARKER}\n\n"
        "Cleared: no guarded changes are missing a matching test change."
    }


def test_no_finding_and_no_existing_comment_posts_nothing(client, http):
    responses, calls = http
    responses.append((200, []))

    assert client.upsert_comment(12, finding_body=None) == "unchanged"
    assert len(calls) == 1


def test_duplicate_bot_comments_raise_without_writing(client, http):
    responses, calls = http
    responses.append((200, [comment(7), comment(8)]))

    with pytest.raises(GitHubError):
        client.upsert_comment(12, finding_body="Missing")
    assert len(calls) == 1


def test_comment_listing_failure_does_not_create_comment(client, http):
    responses, calls = http
    responses.append((403, {}))

    with pytest.raises(GitHubError):
        client.upsert_comment(12, finding_body="Missing")
    assert len(calls) == 1


@pytest.mark.parametrize("existing", [[], [comment()]])
def test_comment_write_failure_raises(client, http, existing):
    responses, _ = http
    responses.extend([(200, existing), (403, {})])

    with pytest.raises(GitHubError):
        client.upsert_comment(12, finding_body="Missing")


def test_pagination_bound_raises(client, http):
    responses, _ = http
    responses.append((200, [comment(i) for i in range(100)]))

    with pytest.raises(GitHubError):
        client._pages("/issues/12/comments", max_pages=1)


def test_comment_body_is_json_data(client, http):
    responses, calls = http
    responses.extend([(200, []), (201, {})])
    body = '"quoted"\n$(do-not-execute)'

    client.upsert_comment(12, finding_body=body)

    assert calls[-1][2]["body"] == f"{COMMENT_MARKER}\n\n{body}"


@pytest.mark.parametrize("repository", ["https://evil.example/a", "a/b/c", "a/b?x=y"])
def test_invalid_repository_rejected(repository):
    with pytest.raises(ValueError):
        GitHubClient(token="synthetic", repository=repository)


@pytest.mark.parametrize("number", [0, -1, True, "12/path"])
def test_invalid_pr_number_rejected_before_http(client, http, number):
    _, calls = http
    with pytest.raises(ValueError):
        client.list_pr_files(number)
    assert calls == []
