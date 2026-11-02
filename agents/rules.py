import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path


@dataclass(frozen=True)
class ChangedFile:
    filename: str
    status: str
    previous_filename: str | None = None
    patch: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Rule:
    id: str
    paths: tuple[str, ...]
    tests: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    rule_id: str
    guarded_files: tuple[str, ...]
    expected_tests: tuple[str, ...]


def load_rules(path: Path | None = None) -> tuple[Rule, ...]:
    if path is None:
        path = Path(__file__).with_name("guarded_paths.toml")
    with path.open("rb") as source:
        config = tomllib.load(source)
    return tuple(
        Rule(id=item["id"], paths=tuple(item["paths"]), tests=tuple(item["tests"]))
        for item in config["rule"]
    )


def _matches(filename: str, patterns: tuple[str, ...]) -> bool:
    # GitHub uses case-sensitive, repository-relative paths. '*' includes '/'.
    return any(fnmatchcase(filename, pattern) for pattern in patterns)


def evaluate_rules(
    changed_files: Iterable[ChangedFile], *, rules: Iterable[Rule]
) -> tuple[Finding, ...]:
    files = tuple(changed_files)
    findings = []
    for rule in rules:
        guarded_files = sorted(
            {
                name
                for file in files
                for name in (file.filename, file.previous_filename)
                if name is not None and _matches(name, rule.paths)
            }
        )
        # Only the surviving name can count as a test; renaming one away cannot.
        test_changed = any(
            file.status != "removed" and _matches(file.filename, rule.tests)
            for file in files
        )
        if guarded_files and not test_changed:
            findings.append(
                Finding(
                    rule_id=rule.id,
                    guarded_files=tuple(guarded_files),
                    expected_tests=rule.tests,
                )
            )
    return tuple(findings)
