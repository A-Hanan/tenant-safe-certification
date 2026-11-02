from pathlib import Path

import pytest

from agents.rules import ChangedFile, Finding, Rule, evaluate_rules, load_rules


@pytest.fixture
def rules():
    return load_rules()


@pytest.mark.parametrize(
    ("changes", "expected_ids"),
    [
        ([ChangedFile("approvals/services.py", "modified")], ("approval-logic",)),
        ([ChangedFile("approvals/transitions.py", "modified")], ("approval-logic",)),
        ([ChangedFile("approvals/models.py", "removed")], ("approval-logic",)),
        ([ChangedFile("institutions/models.py", "modified")], ("tenant-access",)),
        ([ChangedFile("approvals/api/views.py", "modified")], ("tenant-access",)),
        (
            [ChangedFile("institutions/migrations/0002_example.py", "added")],
            ("tenant-access",),
        ),
        (
            [
                ChangedFile("approvals/services.py", "modified"),
                ChangedFile("tests/approvals/test_transition_matrix.py", "modified"),
            ],
            (),
        ),
        (
            [
                ChangedFile("approvals/services.py", "modified"),
                ChangedFile("tests/approvals/test_separation_of_duties.py", "added"),
            ],
            (),
        ),
        (
            [
                ChangedFile("approvals/api/views.py", "modified"),
                ChangedFile("tests/approvals/test_tenant_isolation.py", "modified"),
            ],
            (),
        ),
        (
            [
                ChangedFile("institutions/models.py", "modified"),
                ChangedFile("tests/institutions/test_memberships.py", "modified"),
            ],
            (),
        ),
        (
            [
                ChangedFile("approvals/services.py", "modified"),
                ChangedFile("tests/approvals/test_read_api.py", "modified"),
            ],
            ("approval-logic",),
        ),
        (
            [
                ChangedFile("approvals/services.py", "modified"),
                ChangedFile("tests/approvals/test_transition_matrix.py", "removed"),
            ],
            ("approval-logic",),
        ),
        (
            [ChangedFile("archive/services.py", "renamed", "approvals/services.py")],
            ("approval-logic",),
        ),
        (
            [ChangedFile("approvals/services.py", "renamed", "other/services.py")],
            ("approval-logic",),
        ),
        (
            [
                ChangedFile("approvals/services.py", "modified"),
                ChangedFile(
                    "tests/archived_test.py",
                    "renamed",
                    "tests/approvals/test_transition_matrix.py",
                ),
            ],
            ("approval-logic",),
        ),
        (
            [
                ChangedFile("approvals/services.py", "modified"),
                ChangedFile(
                    "tests/approvals/test_transition_matrix.py",
                    "renamed",
                    "tests/old_test.py",
                ),
            ],
            (),
        ),
        (
            [
                ChangedFile("approvals/services.py", "modified"),
                ChangedFile("approvals/api/views.py", "modified"),
                ChangedFile("tests/approvals/test_transition_matrix.py", "modified"),
            ],
            ("tenant-access",),
        ),
        ([ChangedFile("README.md", "modified")], ()),
        ([ChangedFile("tests/approvals/test_transition_matrix.py", "modified")], ()),
        ([], ()),
    ],
    ids=[
        "approval-service",
        "approval-transitions",
        "deleted-approval-model",
        "institution",
        "approval-api",
        "nested-institution-path",
        "mapped-transition-test",
        "mapped-separation-test",
        "mapped-isolation-test",
        "mapped-institution-test",
        "unrelated-test",
        "deleted-test",
        "renamed-out-of-guard",
        "renamed-into-guard",
        "test-renamed-away",
        "test-renamed-into-mapping",
        "each-rule-needs-its-own-test",
        "unguarded",
        "test-only",
        "empty",
    ],
)
def test_guarded_changes(changes, expected_ids, rules):
    findings = evaluate_rules(changes, rules=rules)

    assert tuple(finding.rule_id for finding in findings) == expected_ids


def test_findings_include_sorted_unique_paths_and_expected_tests(rules):
    changes = [
        ChangedFile("approvals/transitions.py", "modified"),
        ChangedFile("approvals/services.py", "modified"),
        ChangedFile("approvals/services.py", "modified"),
    ]
    expected = (
        Finding(
            rule_id="approval-logic",
            guarded_files=("approvals/services.py", "approvals/transitions.py"),
            expected_tests=(
                "tests/approvals/test_transition_matrix.py",
                "tests/approvals/test_separation_of_duties.py",
            ),
        ),
    )

    assert evaluate_rules(iter(changes), rules=rules) == expected
    assert evaluate_rules(reversed(changes), rules=rules) == expected


def test_both_rules_see_generator_input(rules):
    changes = iter(
        [
            ChangedFile("approvals/models.py", "modified"),
            ChangedFile("institutions/models.py", "modified"),
        ]
    )

    assert tuple(
        finding.rule_id for finding in evaluate_rules(changes, rules=rules)
    ) == ("approval-logic", "tenant-access")


def test_matching_is_case_sensitive(rules):
    changes = [
        ChangedFile("approvals/services.py", "modified"),
        ChangedFile("tests/approvals/TEST_TRANSITION_MATRIX.py", "modified"),
    ]

    assert tuple(
        finding.rule_id for finding in evaluate_rules(changes, rules=rules)
    ) == ("approval-logic",)


def test_load_rules_from_explicit_toml_path(tmp_path):
    path = tmp_path / "rules.toml"
    path.write_text(
        '[[rule]]\nid = "sample"\npaths = ["source/*"]\ntests = ["tests/*"]\n',
        encoding="utf-8",
    )

    assert load_rules(path) == (Rule("sample", ("source/*",), ("tests/*",)),)


def test_default_rules_path_does_not_depend_on_working_directory(tmp_path, monkeypatch):
    expected = load_rules(Path(__file__).parents[2] / "agents" / "guarded_paths.toml")
    monkeypatch.chdir(tmp_path)

    assert load_rules() == expected
