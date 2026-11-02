import json
import re
from http.client import HTTPException, HTTPSConnection

from agents.rules import ChangedFile

COMMENT_MARKER = "<!-- approval-pr-guard -->"
BOT_LOGIN = "github-actions[bot]"


class GitHubError(RuntimeError):
    def __init__(
        self, message: str, *, status: int | None = None, method: str | None = None
    ):
        super().__init__(message)
        self.status = status
        self.method = method


class GitHubClient:
    def __init__(self, *, token: str, repository: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Expected repository in owner/name format")
        self._token = token
        self._prefix = f"/repos/{repository}"

    def _request(self, method: str, path: str, body: dict | None = None):
        connection = HTTPSConnection("api.github.com", timeout=20)
        try:
            connection.request(
                method,
                self._prefix + path,
                body=json.dumps(body).encode("utf-8") if body is not None else None,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/vnd.github+json",
                    "Content-Type": "application/json",
                    "User-Agent": "approval-pr-guard",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response = connection.getresponse()
            if not 200 <= response.status < 300:
                # Do not expose response bodies, which may contain sensitive data.
                raise GitHubError(
                    "GitHub HTTP request failed", status=response.status, method=method
                )
            return json.loads(response.read())
        except (HTTPException, OSError, ValueError) as error:
            raise GitHubError("GitHub request or JSON decoding failed") from error
        finally:
            connection.close()

    @staticmethod
    def _number(value: int) -> int:
        if type(value) is not int or value < 1:
            raise ValueError("Expected a positive integer ID")
        return value

    def _pages(self, path: str, *, max_pages: int = 100) -> list[dict]:
        items = []
        for page in range(1, max_pages + 1):
            batch = self._request("GET", f"{path}?per_page=100&page={page}")
            if not isinstance(batch, list) or any(
                not isinstance(item, dict) for item in batch
            ):
                raise GitHubError("Invalid GitHub list response")
            items.extend(batch)
            if len(batch) < 100:
                return items
        raise GitHubError("GitHub pagination limit reached; results are incomplete")

    def list_pr_files(self, pr_number: int) -> tuple[ChangedFile, ...]:
        path = f"/pulls/{self._number(pr_number)}"
        before = self._request("GET", path)
        try:
            count = before["changed_files"]
            head = before["head"]["sha"]
            base = before["base"]["sha"]
            if type(count) is not int or not 0 <= count <= 3000:
                raise GitHubError("PR file count exceeds supported API limits")
            # One extra page permits an empty page after exactly 3000 files.
            rows = self._pages(f"{path}/files", max_pages=31)
            files = []
            for row in rows:
                filename = row["filename"]
                status = row["status"]
                previous = row.get("previous_filename")
                patch = row.get("patch")
                if (
                    not isinstance(filename, str)
                    or not filename
                    or status
                    not in {
                        "added",
                        "removed",
                        "modified",
                        "renamed",
                        "copied",
                        "changed",
                        "unchanged",
                    }
                    or (previous is not None and not isinstance(previous, str))
                    or (status == "renamed" and not previous)
                    or (patch is not None and not isinstance(patch, str))
                ):
                    raise GitHubError("Invalid PR file metadata")
                files.append(ChangedFile(filename, status, previous, patch))
            after = self._request("GET", path)
            if (
                len(files) != count
                or len({file.filename for file in files}) != count
                or after["changed_files"] != count
                or after["head"]["sha"] != head
                or after["base"]["sha"] != base
            ):
                raise GitHubError(
                    "PR files are incomplete or changed during pagination"
                )
        except (KeyError, TypeError) as error:
            raise GitHubError("Invalid PR response") from error
        return tuple(files)

    def upsert_comment(self, pr_number: int, *, finding_body: str | None) -> str:
        path = f"/issues/{self._number(pr_number)}/comments"
        comments = self._pages(path)
        matches = [
            comment
            for comment in comments
            if comment.get("user", {}).get("login") == BOT_LOGIN
            and COMMENT_MARKER in (comment.get("body") or "")
        ]
        if len(matches) > 1:
            raise GitHubError("Multiple guard comments found")
        if not matches and finding_body is None:
            return "unchanged"
        text = (
            finding_body
            if finding_body is not None
            else "Cleared: no guarded changes are missing a matching test change."
        )
        body = {"body": f"{COMMENT_MARKER}\n\n{text}"}
        if matches:
            comment_id = self._number(matches[0]["id"])
            self._request("PATCH", f"/issues/comments/{comment_id}", body)
            return "updated"
        self._request("POST", path, body)
        return "created"
