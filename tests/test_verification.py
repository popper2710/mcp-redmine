"""Tests for verification.collect_unapplied_fields() and message builders."""

from mcp_redmine.verification import (
    collect_unapplied_fields,
    format_create_warning,
    format_update_error_message,
)


def make_issue(**overrides):
    """A representative issue JSON as returned by Redmine."""
    issue = {
        "id": 123,
        "project": {"id": 1, "name": "Demo"},
        "tracker": {"id": 2, "name": "Feature"},
        "status": {"id": 2, "name": "In Progress"},
        "priority": {"id": 4, "name": "Normal"},
        "assigned_to": {"id": 5, "name": "Alice"},
        "subject": "Test subject",
        "description": "line1\nline2",
        "start_date": "2026-07-01",
        "due_date": "2026-07-31",
        "done_ratio": 50,
        "estimated_hours": 2.0,
        "is_private": False,
        "custom_fields": [
            {"id": 1, "name": "Env", "value": "production"},
            {"id": 2, "name": "Tags", "value": ["a", "b"]},
        ],
    }
    issue.update(overrides)
    return issue


class TestCollectUnappliedFieldsApplied:
    def test_all_fields_applied(self):
        requested = {
            "status_id": 2,
            "priority_id": 4,
            "assigned_to_id": 5,
            "subject": "Test subject",
            "description": "line1\nline2",
            "start_date": "2026-07-01",
            "done_ratio": 50,
            "estimated_hours": 2.0,
            "is_private": False,
        }
        assert collect_unapplied_fields(requested, make_issue()) == []

    def test_empty_request(self):
        assert collect_unapplied_fields({}, make_issue()) == []

    def test_unverifiable_fields_are_ignored(self):
        requested = {
            "notes": "a comment",
            "private_notes": True,
            "uploads": [{"token": "x", "filename": "f.txt"}],
        }
        assert collect_unapplied_fields(requested, make_issue()) == []


class TestCollectUnappliedFieldsDiscarded:
    def test_status_discarded(self):
        requested = {"status_id": 5}
        result = collect_unapplied_fields(requested, make_issue())
        assert result == [{"field": "status_id", "requested": 5, "actual": 2}]

    def test_assigned_to_discarded_when_absent(self):
        issue = make_issue()
        del issue["assigned_to"]
        result = collect_unapplied_fields({"assigned_to_id": 5}, issue)
        assert result == [
            {"field": "assigned_to_id", "requested": 5, "actual": None}
        ]

    def test_parent_issue_discarded(self):
        result = collect_unapplied_fields(
            {"parent_issue_id": 99}, make_issue()
        )
        assert result == [
            {"field": "parent_issue_id", "requested": 99, "actual": None}
        ]

    def test_multiple_fields_discarded(self):
        requested = {"status_id": 5, "done_ratio": 80, "priority_id": 4}
        result = collect_unapplied_fields(requested, make_issue())
        fields = {item["field"] for item in result}
        assert fields == {"status_id", "done_ratio"}


class TestClearingFields:
    """Clearing a value is requested as "" but persisted as absent/None;
    a successful clear must not be reported as a discarded field."""

    def test_clearing_date_with_empty_string(self):
        issue = make_issue()
        del issue["due_date"]
        assert collect_unapplied_fields({"due_date": ""}, issue) == []

    def test_discarded_clear_is_still_reported(self):
        # A clear that did NOT stick (value survived) remains a mismatch
        result = collect_unapplied_fields({"due_date": ""}, make_issue())
        assert result == [
            {"field": "due_date", "requested": "", "actual": "2026-07-31"}
        ]

    def test_clearing_multivalue_custom_field(self):
        issue = make_issue(custom_fields=[{"id": 2, "value": []}])
        requested = {"custom_fields": [{"id": 2, "value": [""]}]}
        assert collect_unapplied_fields(requested, issue) == []

    def test_clearing_description_read_back_as_null(self):
        issue = make_issue(description=None)
        assert collect_unapplied_fields({"description": ""}, issue) == []


class TestProjectIdVerification:
    def test_numeric_project_id_verified(self):
        result = collect_unapplied_fields({"project_id": 9}, make_issue())
        assert result == [{"field": "project_id", "requested": 9, "actual": 1}]

    def test_string_identifier_skipped(self):
        # The issue JSON only carries the numeric project id, so a string
        # identifier cannot be compared - it must not raise a false error.
        result = collect_unapplied_fields(
            {"project_id": "demo-project"}, make_issue()
        )
        assert result == []


class TestTextComparison:
    def test_crlf_normalization_is_not_a_mismatch(self):
        issue = make_issue(description="line1\r\nline2")
        result = collect_unapplied_fields(
            {"description": "line1\nline2"}, issue
        )
        assert result == []

    def test_trailing_whitespace_is_not_a_mismatch(self):
        issue = make_issue(description="line1\nline2\n")
        result = collect_unapplied_fields(
            {"description": "line1\nline2"}, issue
        )
        assert result == []

    def test_real_description_mismatch(self):
        result = collect_unapplied_fields(
            {"description": "completely different"}, make_issue()
        )
        assert len(result) == 1
        assert result[0]["field"] == "description"


class TestNumericComparison:
    def test_estimated_hours_within_tolerance(self):
        issue = make_issue(estimated_hours=2.0000001)
        assert collect_unapplied_fields({"estimated_hours": 2.0}, issue) == []

    def test_estimated_hours_mismatch(self):
        result = collect_unapplied_fields(
            {"estimated_hours": 8.0}, make_issue()
        )
        assert result == [
            {"field": "estimated_hours", "requested": 8.0, "actual": 2.0}
        ]

    def test_estimated_hours_discarded_when_absent(self):
        issue = make_issue()
        del issue["estimated_hours"]
        result = collect_unapplied_fields({"estimated_hours": 8.0}, issue)
        assert result == [
            {"field": "estimated_hours", "requested": 8.0, "actual": None}
        ]


class TestIsPrivate:
    def test_mismatch_reported_when_present(self):
        result = collect_unapplied_fields({"is_private": True}, make_issue())
        assert result == [
            {"field": "is_private", "requested": True, "actual": False}
        ]

    def test_skipped_when_server_omits_field(self):
        issue = make_issue()
        del issue["is_private"]
        assert collect_unapplied_fields({"is_private": True}, issue) == []


class TestCustomFields:
    def test_string_vs_int_value_equal(self):
        issue = make_issue(
            custom_fields=[{"id": 1, "name": "Points", "value": "3"}]
        )
        requested = {"custom_fields": [{"id": 1, "value": 3}]}
        assert collect_unapplied_fields(requested, issue) == []

    def test_list_value_order_insensitive(self):
        requested = {"custom_fields": [{"id": 2, "value": ["b", "a"]}]}
        assert collect_unapplied_fields(requested, make_issue()) == []

    def test_value_mismatch(self):
        requested = {"custom_fields": [{"id": 1, "value": "staging"}]}
        result = collect_unapplied_fields(requested, make_issue())
        assert result == [
            {
                "field": "custom_fields[id=1]",
                "requested": "staging",
                "actual": "production",
            }
        ]

    def test_unknown_custom_field_id_reported(self):
        requested = {"custom_fields": [{"id": 42, "value": "x"}]}
        result = collect_unapplied_fields(requested, make_issue())
        assert result == [
            {"field": "custom_fields[id=42]", "requested": "x", "actual": None}
        ]

    def test_boolean_value_matches_redmine_storage(self):
        # Redmine persists boolean custom fields as "1"/"0"
        issue = make_issue(custom_fields=[{"id": 5, "value": "0"}])
        requested = {"custom_fields": [{"id": 5, "value": False}]}
        assert collect_unapplied_fields(requested, issue) == []

    def test_none_and_empty_string_equal(self):
        issue = make_issue(custom_fields=[{"id": 1, "value": ""}])
        requested = {"custom_fields": [{"id": 1, "value": None}]}
        assert collect_unapplied_fields(requested, issue) == []

    def test_malformed_entries_ignored(self):
        requested = {"custom_fields": ["not a dict", {"value": "no id"}]}
        assert collect_unapplied_fields(requested, make_issue()) == []


class TestFormatUpdateErrorMessage:
    UNAPPLIED_STATUS = [{"field": "status_id", "requested": 5, "actual": 2}]

    def test_includes_field_details(self):
        message = format_update_error_message(self.UNAPPLIED_STATUS)
        assert "status_id" in message
        assert "requested 5" in message
        assert "actual 2" in message
        assert "silently discarded" in message

    def test_with_allowed_statuses(self):
        allowed = [
            {"id": 1, "name": "New"},
            {"id": 2, "name": "In Progress"},
        ]
        message = format_update_error_message(self.UNAPPLIED_STATUS, allowed)
        assert "Allowed statuses for this issue: New(1), In Progress(2)." in message

    def test_fallback_without_allowed_statuses(self):
        # Redmine < 5.0 silently ignores include=allowed_statuses, so the
        # message must fall back to pointing at the workflow configuration.
        message = format_update_error_message(self.UNAPPLIED_STATUS, None)
        assert "does not report allowed statuses" in message
        assert "Administration > Workflow" in message

    def test_empty_allowed_statuses_means_no_transitions(self):
        # [] means the server DID report: no transitions are allowed
        message = format_update_error_message(self.UNAPPLIED_STATUS, [])
        assert "No status transitions are allowed" in message
        assert "does not report" not in message

    def test_no_status_hint_for_other_fields(self):
        unapplied = [{"field": "done_ratio", "requested": 80, "actual": 50}]
        message = format_update_error_message(unapplied)
        assert "Allowed statuses" not in message
        assert "allowed statuses" not in message


class TestFormatCreateWarning:
    def test_contains_issue_id_and_retry_guard(self):
        unapplied = [{"field": "status_id", "requested": 5, "actual": 1}]
        message = format_create_warning(123, unapplied)
        assert "Issue #123 was created" in message
        assert "status_id" in message
        assert "Do NOT retry creation" in message
        assert "update_issue" in message
