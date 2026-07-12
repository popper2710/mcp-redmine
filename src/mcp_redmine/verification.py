"""Post-update verification for detecting silently discarded fields.

Redmine's safe_attributes mechanism silently drops attributes that the API
user is not allowed to set (workflow or permission restrictions) and still
returns HTTP 200 (see redmine.org issues #8626, #10233, #12496). These
helpers compare the requested field values against the issue state Redmine
actually persisted, so callers can fail loudly instead of reporting a
success that never happened.
"""

from typing import Any, Callable

from .text_utils import normalize_line_endings

# Marker for "the issue JSON does not carry this field, so it cannot be
# verified" (distinct from None, which means "the field is unset").
_UNVERIFIABLE = object()

# Tolerate float representation drift (Redmine rounds hours on persist).
FLOAT_TOLERANCE = 0.01


def _nested_id(key: str) -> Callable[[dict], Any]:
    """Extractor for association fields like {"status": {"id": 2, ...}}."""

    def extract(issue: dict) -> Any:
        value = issue.get(key)
        if value is None:
            return None
        return value.get("id")

    return extract


def _scalar(key: str) -> Callable[[dict], Any]:
    def extract(issue: dict) -> Any:
        return issue.get(key)

    return extract


def _applied_eq(requested: Any, actual: Any) -> bool:
    # An empty string means "clear the field" in the Redmine API, and
    # cleared fields are omitted from the issue JSON - "" must compare
    # equal to None or a fully successful clear reads as a false mismatch.
    if requested == "" and actual is None:
        return True
    return requested == actual


def _float_eq(requested: Any, actual: Any) -> bool:
    if actual is None:
        return False
    return abs(float(requested) - float(actual)) < FLOAT_TOLERANCE


def _text_eq(requested: str, actual: Any) -> bool:
    if actual is None:
        actual = ""  # a cleared text field may read back as null
    # rstrip: trailing-whitespace normalization on save must not read as a
    # discarded field.
    return (
        normalize_line_endings(requested).rstrip()
        == normalize_line_endings(actual).rstrip()
    )


# Maps update/create request field names to how the corresponding value is
# read back from the issue JSON returned by Redmine.
#   extract: callable(issue_json) -> persisted value (or _UNVERIFIABLE)
#   compare: callable(requested, actual) -> bool (defaults to _applied_eq)
#   verify_if: callable(requested) -> bool; skip verification when False
FIELD_SPECS = {
    # project_id accepts a string identifier, but the issue JSON only
    # carries the numeric id, so only numeric requests are verifiable
    # (callers should resolve identifiers to ids before verifying).
    "project_id": {
        "extract": _nested_id("project"),
        "verify_if": lambda value: isinstance(value, int),
    },
    "tracker_id": {"extract": _nested_id("tracker")},
    "status_id": {"extract": _nested_id("status")},
    "priority_id": {"extract": _nested_id("priority")},
    "category_id": {"extract": _nested_id("category")},
    "fixed_version_id": {"extract": _nested_id("fixed_version")},
    "assigned_to_id": {"extract": _nested_id("assigned_to")},
    "parent_issue_id": {"extract": _nested_id("parent")},
    "subject": {"extract": _scalar("subject")},
    "description": {"extract": _scalar("description"), "compare": _text_eq},
    "start_date": {"extract": _scalar("start_date")},
    "due_date": {"extract": _scalar("due_date")},
    "done_ratio": {"extract": _scalar("done_ratio")},
    "estimated_hours": {
        "extract": _scalar("estimated_hours"),
        "compare": _float_eq,
    },
    # Some Redmine versions omit is_private from the issue JSON; skip
    # verification rather than report a false mismatch.
    "is_private": {
        "extract": lambda issue: issue.get("is_private", _UNVERIFIABLE),
    },
}


def _cf_str(value: Any) -> str:
    """Normalize a custom field value the way Redmine persists it:
    strings for everything, "1"/"0" for booleans, "" for null."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _custom_field_value_eq(requested: Any, actual: Any) -> bool:
    if isinstance(requested, list) or isinstance(actual, list):
        requested_list = requested if isinstance(requested, list) else [requested]
        actual_list = actual if isinstance(actual, list) else [actual]
        # Clearing a multi-value field is requested as [""] but persisted
        # as [] - ignore blank entries on both sides.
        return sorted(
            _cf_str(v) for v in requested_list if v not in (None, "")
        ) == sorted(_cf_str(v) for v in actual_list if v not in (None, ""))
    return _cf_str(requested) == _cf_str(actual)


def _collect_unapplied_custom_fields(
    requested_custom_fields: list, issue: dict
) -> list[dict]:
    actual_by_id = {
        cf.get("id"): cf.get("value") for cf in issue.get("custom_fields", [])
    }
    unapplied = []
    for cf in requested_custom_fields or []:
        if not isinstance(cf, dict) or "id" not in cf:
            continue
        cf_id = cf["id"]
        requested_value = cf.get("value")
        if cf_id not in actual_by_id:
            unapplied.append(
                {
                    "field": f"custom_fields[id={cf_id}]",
                    "requested": requested_value,
                    "actual": None,
                }
            )
            continue
        actual_value = actual_by_id[cf_id]
        if not _custom_field_value_eq(requested_value, actual_value):
            unapplied.append(
                {
                    "field": f"custom_fields[id={cf_id}]",
                    "requested": requested_value,
                    "actual": actual_value,
                }
            )
    return unapplied


def collect_unapplied_fields(requested: dict, issue: dict) -> list[dict]:
    """Compare requested field values against the persisted issue JSON.

    Args:
        requested: The fields sent to Redmine (the "issue" payload).
            Fields without a verification spec (notes, uploads, ...) are
            ignored.
        issue: The issue JSON returned by Redmine after the operation.

    Returns:
        List of {"field", "requested", "actual"} dicts for every field
        Redmine silently discarded. Empty list when everything applied.
    """
    unapplied = []
    for field, requested_value in requested.items():
        if field == "custom_fields":
            unapplied.extend(
                _collect_unapplied_custom_fields(requested_value, issue)
            )
            continue

        spec = FIELD_SPECS.get(field)
        if spec is None:
            continue

        verify_if = spec.get("verify_if")
        if verify_if is not None and not verify_if(requested_value):
            continue

        actual = spec["extract"](issue)
        if actual is _UNVERIFIABLE:
            continue

        compare = spec.get("compare", _applied_eq)
        if not compare(requested_value, actual):
            unapplied.append(
                {"field": field, "requested": requested_value, "actual": actual}
            )
    return unapplied


def _describe_unapplied(unapplied: list[dict]) -> str:
    return ", ".join(
        f"{item['field']} (requested {item['requested']!r}, "
        f"actual {item['actual']!r})"
        for item in unapplied
    )


def format_update_error_message(
    unapplied: list[dict],
    allowed_statuses: list[dict] | None = None,
) -> str:
    """Build the error message for an update whose fields were discarded.

    Args:
        unapplied: Result of collect_unapplied_fields() (must be non-empty).
        allowed_statuses: The "allowed_statuses" array from
            GET /issues/:id.json?include=allowed_statuses (Redmine 5.0+).
            Pass None when the server does not report it.
    """
    message = (
        "Redmine accepted the update (HTTP 200) but silently discarded "
        f"these fields: {_describe_unapplied(unapplied)}. Likely causes: "
        "workflow or permission restrictions, a user that cannot be "
        "assigned or watch this issue, parent-issue fields derived from "
        "subtasks, or a concurrent edit by another user."
    )
    if any(item["field"] == "status_id" for item in unapplied):
        if allowed_statuses:
            statuses = ", ".join(
                f"{status.get('name')}({status.get('id')})"
                for status in allowed_statuses
            )
            message += f" Allowed statuses for this issue: {statuses}."
        elif allowed_statuses is not None:
            # Present but empty: the workflow defines no transitions from
            # the current status for the API user's role.
            message += (
                " No status transitions are allowed for the API user's role "
                "from the issue's current status (check Administration > "
                "Workflow)."
            )
        else:
            # Absent: Redmine < 5.0 silently ignores include=allowed_statuses.
            message += (
                " (This Redmine server does not report allowed statuses; "
                "check Administration > Workflow for allowed transitions.)"
            )
    return message


def format_create_warning(issue_id: int | None, unapplied: list[dict]) -> str:
    """Build the warning attached to a create_issue response when Redmine
    discarded some of the requested fields.

    The issue itself was created, so this must NOT be raised as an error
    (a retry would create a duplicate issue).
    """
    return (
        f"Issue #{issue_id} was created, but Redmine silently ignored: "
        f"{_describe_unapplied(unapplied)}. This is caused by workflow or "
        "permission restrictions. Do NOT retry creation; use update_issue "
        "to fix these fields if needed."
    )
