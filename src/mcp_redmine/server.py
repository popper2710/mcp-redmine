"""Redmine MCP Server - Main entry point."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .models import RedmineConfig, RedmineError
from .redmine_client import RedmineClient
from .text_utils import apply_patches
from .verification import (
    collect_unapplied_fields,
    format_create_warning,
    format_update_error_message,
)

# Load environment variables from .env file
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("Redmine MCP Server")

# Global Redmine client instance
_redmine_client: RedmineClient | None = None


def get_redmine_client() -> RedmineClient:
    """Get or create Redmine client instance.

    Returns:
        RedmineClient instance

    Raises:
        RedmineError: If required environment variables are not set
    """
    global _redmine_client

    if _redmine_client is None:
        # Get configuration from environment variables
        redmine_url = os.getenv("REDMINE_URL")
        redmine_api_key = os.getenv("REDMINE_API_KEY")

        if not redmine_url:
            raise RedmineError(
                "REDMINE_URL environment variable is not set. "
                "Please set it to your Redmine instance URL."
            )

        if not redmine_api_key:
            raise RedmineError(
                "REDMINE_API_KEY environment variable is not set. "
                "Please set it to your Redmine API key."
            )

        # Create configuration
        config = RedmineConfig(
            url=redmine_url,
            api_key=redmine_api_key,
        )

        # Create client
        _redmine_client = RedmineClient(config)

    return _redmine_client


# Project Operations

@mcp.tool()
async def list_projects(
    limit: int = 25,
    offset: int = 0,
) -> dict:
    """List accessible Redmine projects.

    Args:
        limit: Maximum number of projects to return (default: 25, max: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        Dictionary containing:
        - projects: List of projects with their details (id, name, identifier, description, status, etc.)
        - total_count: Total number of accessible projects
        - limit: Current limit value
        - offset: Current offset value
    """
    client = get_redmine_client()
    params = {
        "limit": min(limit, 100),  # Cap at 100
        "offset": offset,
    }
    response = await client.get("/projects.json", params=params)
    return response


@mcp.tool()
async def get_project(project_id: int | str) -> dict:
    """Get detailed information about a specific project.

    Args:
        project_id: The ID (numeric) or identifier (string) of the project to retrieve

    Returns:
        Dictionary containing detailed project information including
        trackers, issue categories, and other metadata
    """
    client = get_redmine_client()
    response = await client.get(f"/projects/{project_id}.json")
    return response


@mcp.tool()
async def search(
    q: str,
    issues: bool = False,
    projects: bool = False,
    wiki_pages: bool = False,
    news: bool = False,
    documents: bool = False,
    changesets: bool = False,
    messages: bool = False,
    scope: str = "all",
    limit: int = 25,
    offset: int = 0,
) -> dict:
    """Search across Redmine resources using the Search API.

    Args:
        q: Search query string (required)
        issues: Include issues in search results
        projects: Include projects in search results
        wiki_pages: Include wiki pages in search results
        news: Include news in search results
        documents: Include documents in search results
        changesets: Include changesets in search results
        messages: Include messages in search results
        scope: Search scope - 'all', 'my_project', or 'subprojects' (default: 'all')
        limit: Maximum number of results (default: 25, max: 100)
        offset: Pagination offset (default: 0)

    Returns:
        Dictionary containing:
        - results: List with id, title, type, url, description, datetime
        - total_count: Total number of results
        - limit: Current limit value
        - offset: Current offset value

    Note:
        Uses Redmine Search API (Redmine 3.3+, Alpha status).
        If no resource types specified, searches all types.

    Example:
        # Search projects only
        search(q="ERP", projects=True)

        # Search issues and projects
        search(q="bug", issues=True, projects=True)
    """
    client = get_redmine_client()

    # Validate scope parameter
    valid_scopes = ["all", "my_project", "subprojects"]
    if scope not in valid_scopes:
        raise RedmineError(
            f"Invalid scope '{scope}'. "
            f"Valid values are: {', '.join(valid_scopes)}"
        )

    # Build parameters
    params = {
        "q": q,
        "scope": scope,
        "limit": min(limit, 100),
        "offset": offset,
    }

    # Add resource type filters
    if issues:
        params["issues"] = "1"
    if projects:
        params["projects"] = "1"
    if wiki_pages:
        params["wiki_pages"] = "1"
    if news:
        params["news"] = "1"
    if documents:
        params["documents"] = "1"
    if changesets:
        params["changesets"] = "1"
    if messages:
        params["messages"] = "1"

    response = await client.get("/search.json", params=params)
    return response


@mcp.tool()
async def get_issue(
    issue_id: int,
    include_journals: bool = False,
    include_children: bool = False,
    include_attachments: bool = True,
    include_relations: bool = True,
) -> dict:
    """Get detailed information about a specific issue (ticket).

    Args:
        issue_id: The ID of the issue to retrieve
        include_journals: Include comment/change history (default: False).
            WARNING: Can be very large as it contains full old/new values
            for every field change including description edits.
        include_children: Include child issues/subtasks (default: False)
        include_attachments: Include attachment list (default: True)
        include_relations: Include related issues (default: True)

    Returns:
        Dictionary containing detailed issue information including
        journals (comments), attachments, and relations
    """
    client = get_redmine_client()

    # Build include parameter based on options
    includes = []
    if include_journals:
        includes.append("journals")
    if include_children:
        includes.append("children")
    if include_attachments:
        includes.append("attachments")
    if include_relations:
        includes.append("relations")

    params = {}
    if includes:
        params["include"] = ",".join(includes)

    response = await client.get(f"/issues/{issue_id}.json", params=params)
    return response


# Issue Operations

@mcp.tool()
async def list_issues(
    project_id: int | str | None = None,
    tracker_id: int | None = None,
    status_id: str = "*",
    assigned_to_id: int | None = None,
    priority_id: int | None = None,
    limit: int = 25,
    offset: int = 0,
    minimal_output: bool = True,
) -> dict:
    """Search and list issues (tickets) with various filters.

    Args:
        project_id: Filter by project ID (numeric) or project identifier (string) (optional)
        tracker_id: Filter by tracker ID (optional)
        status_id: Filter by status - "open", "closed", or "*" for all (default: "*")
        assigned_to_id: Filter by assigned user ID (optional)
        priority_id: Filter by priority ID (optional)
        limit: Maximum number of issues to return (default: 25, max: 100)
        offset: Offset for pagination (default: 0)
        minimal_output: Return minimal issue information (default: True).
            When True, returns only id, subject, status, priority, assigned_to, and project.
            When False, returns full issue details from Redmine API.

    Returns:
        Dictionary containing list of issues, total count, and pagination info
    """
    client = get_redmine_client()

    # Build query parameters
    params = {
        "limit": min(limit, 100),  # Cap at 100
        "offset": offset,
        "status_id": status_id,
    }

    # Add optional filters
    if project_id is not None:
        params["project_id"] = project_id
    if tracker_id is not None:
        params["tracker_id"] = tracker_id
    if assigned_to_id is not None:
        params["assigned_to_id"] = assigned_to_id
    if priority_id is not None:
        params["priority_id"] = priority_id

    response = await client.get("/issues.json", params=params)

    # Return minimal output if requested (default)
    if minimal_output:
        minimal_issues = []
        for issue in response.get("issues", []):
            minimal_issue = {
                "id": issue.get("id"),
                "subject": issue.get("subject"),
                "status": issue.get("status", {}).get("name"),
                "priority": issue.get("priority", {}).get("name"),
                "assigned_to": issue.get("assigned_to", {}).get("name")
                if issue.get("assigned_to")
                else None,
                "project": issue.get("project", {}).get("name"),
            }
            minimal_issues.append(minimal_issue)
        return {
            "issues": minimal_issues,
            "total_count": response.get("total_count", 0),
            "offset": response.get("offset", 0),
            "limit": response.get("limit", 0),
        }

    return response


@mcp.tool()
async def create_issue(
    project_id: int | str,
    subject: str,
    description: str = "",
    tracker_id: int | None = None,
    status_id: int | None = None,
    priority_id: int | None = None,
    assigned_to_id: int | None = None,
    category_id: int | None = None,
    fixed_version_id: int | None = None,
    parent_issue_id: int | None = None,
    start_date: str | None = None,
    due_date: str | None = None,
    estimated_hours: float | None = None,
    done_ratio: int | None = None,
    is_private: bool | None = None,
    watcher_user_ids: list[int] | None = None,
    custom_fields: list[dict] | None = None,
    uploads: list[dict] | None = None,
) -> dict:
    """Create a new issue (ticket) in Redmine.

    Args:
        project_id: Project ID (numeric) or project identifier (string) (required)
        subject: Issue subject/title (required)
        description: Issue description (optional)
        tracker_id: Tracker ID (optional, uses project default if not specified)
        status_id: Status ID (optional)
        priority_id: Priority ID (optional)
        assigned_to_id: Assigned user ID (optional)
        category_id: Category ID (optional)
        fixed_version_id: Target version ID (optional)
        parent_issue_id: Parent issue ID for subtasks (optional)
        start_date: Start date in YYYY-MM-DD format (optional)
        due_date: Due date in YYYY-MM-DD format (optional)
        estimated_hours: Estimated hours as float (optional)
        done_ratio: Progress percentage 0-100 (optional)
        is_private: Whether the issue is private (optional)
        watcher_user_ids: List of user IDs to add as watchers (optional, requires Redmine 2.3.0+)
        custom_fields: List of custom field dictionaries with 'id' and 'value' keys (optional)
        uploads: List of file uploads to attach. Each upload should be a dictionary with:
            - token: Upload token from upload_attachment() (required)
            - filename: Filename to use in Redmine (required)
            - content_type: MIME type (optional, e.g., "application/pdf")
            - description: File description (optional)

    Returns:
        Dictionary containing the created issue information including its ID.
        If Redmine silently ignored some of the requested fields (workflow or
        permission restrictions), the response contains a "warnings" list
        describing them. In that case the issue WAS created - do NOT retry
        creation; use update_issue to fix the remaining fields instead.
    """
    client = get_redmine_client()

    # Build issue data
    issue_data = {
        "project_id": project_id,
        "subject": subject,
    }

    # Add optional fields
    if description:
        issue_data["description"] = description
    if tracker_id is not None:
        issue_data["tracker_id"] = tracker_id
    if status_id is not None:
        issue_data["status_id"] = status_id
    if priority_id is not None:
        issue_data["priority_id"] = priority_id
    if assigned_to_id is not None:
        issue_data["assigned_to_id"] = assigned_to_id
    if category_id is not None:
        issue_data["category_id"] = category_id
    if fixed_version_id is not None:
        issue_data["fixed_version_id"] = fixed_version_id
    if parent_issue_id is not None:
        issue_data["parent_issue_id"] = parent_issue_id
    if start_date is not None:
        issue_data["start_date"] = start_date
    if due_date is not None:
        issue_data["due_date"] = due_date
    if estimated_hours is not None:
        if estimated_hours < 0:
            raise ValueError("estimated_hours must be non-negative")
        issue_data["estimated_hours"] = estimated_hours
    if done_ratio is not None:
        if not 0 <= done_ratio <= 100:
            raise ValueError("done_ratio must be between 0 and 100")
        issue_data["done_ratio"] = done_ratio
    if is_private is not None:
        issue_data["is_private"] = is_private
    if watcher_user_ids is not None:
        issue_data["watcher_user_ids"] = watcher_user_ids
    if custom_fields is not None:
        issue_data["custom_fields"] = custom_fields
    if uploads is not None:
        issue_data["uploads"] = uploads

    # Wrap in "issue" key as required by Redmine API
    request_data = {"issue": issue_data}

    response = await client.post("/issues.json", json_data=request_data)

    # Redmine silently discards fields the API user may not set (workflow /
    # permission restrictions) while still returning 201. Surface those as
    # warnings - not an error, because the issue WAS created and an error
    # would push agents into retrying and creating duplicates.
    created_issue = response.get("issue", {})
    unapplied = collect_unapplied_fields(issue_data, created_issue)
    if unapplied:
        response["warnings"] = [
            format_create_warning(created_issue.get("id"), unapplied)
        ]

    return response


async def _add_watchers(
    client: RedmineClient, issue_id: int, watcher_user_ids: list[int]
) -> None:
    """Add watchers via POST /issues/:id/watchers.json."""
    for user_id in watcher_user_ids:
        try:
            await client.post(
                f"/issues/{issue_id}/watchers.json",
                json_data={"user_id": user_id},
            )
        except RedmineError as e:
            raise RedmineError(
                f"The field update for issue #{issue_id} was submitted, but "
                f"adding watcher user {user_id} failed: {e.message}",
                e.status_code,
            ) from e


@mcp.tool()
async def update_issue(
    issue_id: int,
    project_id: int | str | None = None,
    subject: str | None = None,
    description: str | None = None,
    description_patches: list[dict] | None = None,
    tracker_id: int | None = None,
    status_id: int | None = None,
    priority_id: int | None = None,
    assigned_to_id: int | None = None,
    category_id: int | None = None,
    fixed_version_id: int | None = None,
    parent_issue_id: int | None = None,
    start_date: str | None = None,
    due_date: str | None = None,
    estimated_hours: float | None = None,
    done_ratio: int | None = None,
    is_private: bool | None = None,
    watcher_user_ids: list[int] | None = None,
    custom_fields: list[dict] | None = None,
    notes: str | None = None,
    private_notes: bool | None = None,
    uploads: list[dict] | None = None,
) -> dict:
    """Update an existing issue (ticket).

    DESCRIPTION UPDATES - two approaches (mutually exclusive, do NOT provide both):
      - description: Replace the entire description with new text.
      - description_patches: Apply targeted find-and-replace edits to the existing description.
        Format: [{"old_text": "text to find", "new_text": "replacement"}]
        Optional "replace_all": true to replace all occurrences (default: false).

    Args:
        issue_id: Issue ID to update (required)
        project_id: Project ID (numeric) or identifier (string) to move the issue to another project (optional)
        subject: New subject/title (optional)
        description: New description - replaces entire content (optional).
            Cannot be used together with description_patches.
        description_patches: List of find-and-replace edits for the existing description (optional).
            Each dict: {"old_text": "text to find", "new_text": "replacement"}.
            Optional "replace_all": true to replace all occurrences (default: false).
            Example: [{"old_text": "Status: Draft", "new_text": "Status: Final"}]
            IMPORTANT: Use get_issue() first to see exact current content before constructing patches.
            Cannot be used together with description.
        tracker_id: New tracker ID (optional)
        status_id: New status ID (optional)
        priority_id: New priority ID (optional)
        assigned_to_id: New assigned user ID (optional)
        category_id: New category ID (optional)
        fixed_version_id: New target version ID (optional)
        parent_issue_id: New parent issue ID (optional)
        start_date: New start date in YYYY-MM-DD format (optional)
        due_date: New due date in YYYY-MM-DD format (optional)
        estimated_hours: New estimated hours as float (optional)
        done_ratio: Progress percentage 0-100 (optional)
        is_private: Whether the issue is private (optional)
        watcher_user_ids: User IDs to add as watchers (optional; add-only,
            never removes existing watchers; requires Redmine 2.3.0+)
        custom_fields: List of custom field dictionaries with 'id' and 'value' keys (optional)
        notes: Comment to add to the issue history (optional)
        private_notes: Whether the notes are private (optional)
        uploads: List of file uploads to attach. Each upload should be a dictionary with:
            - token: Upload token from upload_attachment() (required)
            - filename: Filename to use in Redmine (required)
            - content_type: MIME type (optional, e.g., "application/pdf")
            - description: File description (optional)

    Returns:
        Dictionary containing the updated issue (fetched back after the
        update). The description is truncated in the response unless this
        update changed it; use get_issue() for the full text.

    Raises:
        RedmineError: If Redmine silently discarded any requested field
            (workflow/permission rules, e.g. a status transition not allowed
            for your role). The error lists the discarded fields and, when
            available, the allowed statuses.
    """
    client = get_redmine_client()

    if description is not None and description_patches is not None:
        raise ValueError(
            "Cannot provide both 'description' and 'description_patches'. "
            "Use 'description' for full replacement, or 'description_patches' for partial edits."
        )

    # Build issue update data
    issue_data = {}

    # Add fields to update
    if project_id is not None:
        issue_data["project_id"] = project_id
    if subject is not None:
        issue_data["subject"] = subject
    if description is not None:
        issue_data["description"] = description
    if description_patches is not None:
        # Note: no optimistic locking available for issues (Redmine API limitation).
        # Concurrent edits between this GET and the subsequent PUT may be overwritten.
        current = await client.get(f"/issues/{issue_id}.json")
        current_desc = current.get("issue", {}).get("description")
        if not current_desc:
            raise ValueError(
                "Cannot apply description_patches: issue has no description content. "
                "Use 'description' parameter to set initial content."
            )
        patched = apply_patches(current_desc, description_patches)
        if not patched.strip():
            raise ValueError(
                "Patch result would produce empty description."
            )
        issue_data["description"] = patched
    if tracker_id is not None:
        issue_data["tracker_id"] = tracker_id
    if status_id is not None:
        issue_data["status_id"] = status_id
    if priority_id is not None:
        issue_data["priority_id"] = priority_id
    if assigned_to_id is not None:
        issue_data["assigned_to_id"] = assigned_to_id
    if category_id is not None:
        issue_data["category_id"] = category_id
    if fixed_version_id is not None:
        issue_data["fixed_version_id"] = fixed_version_id
    if parent_issue_id is not None:
        issue_data["parent_issue_id"] = parent_issue_id
    if start_date is not None:
        issue_data["start_date"] = start_date
    if due_date is not None:
        issue_data["due_date"] = due_date
    if estimated_hours is not None:
        if estimated_hours < 0:
            raise ValueError("estimated_hours must be non-negative")
        issue_data["estimated_hours"] = estimated_hours
    if done_ratio is not None:
        if not 0 <= done_ratio <= 100:
            raise ValueError("done_ratio must be between 0 and 100")
        issue_data["done_ratio"] = done_ratio
    if is_private is not None:
        issue_data["is_private"] = is_private
    if custom_fields is not None:
        issue_data["custom_fields"] = custom_fields
    if notes is not None:
        issue_data["notes"] = notes
    if private_notes is not None:
        issue_data["private_notes"] = private_notes
    if uploads is not None:
        issue_data["uploads"] = uploads

    # Check if at least one field is being updated
    if not issue_data and not watcher_user_ids:
        raise ValueError("At least one field must be specified for update")

    if issue_data:
        # Wrap in "issue" key as required by Redmine API
        request_data = {"issue": issue_data}
        await client.put(f"/issues/{issue_id}.json", json_data=request_data)

    # Redmine ignores watcher_user_ids in update payloads (it is only
    # honored on creation), so watchers go through the dedicated API.
    if watcher_user_ids is not None:
        await _add_watchers(client, issue_id, watcher_user_ids)

    # Redmine silently discards fields the API user may not set (workflow /
    # permission restrictions) while still returning 200, so read the issue
    # back and fail loudly if anything did not stick.
    includes = "allowed_statuses"
    if watcher_user_ids is not None:
        includes += ",watchers"
    updated = await client.get(
        f"/issues/{issue_id}.json", params={"include": includes}
    )
    updated_issue = updated.get("issue", {})

    # A project identifier string cannot be compared against the numeric id
    # in the issue JSON; resolve it so project moves get verified too.
    if isinstance(issue_data.get("project_id"), str):
        try:
            project = await client.get(
                f"/projects/{issue_data['project_id']}.json"
            )
            issue_data["project_id"] = project.get("project", {}).get("id")
        except RedmineError:
            pass  # unresolvable; verification skips non-numeric project_id

    unapplied = collect_unapplied_fields(issue_data, updated_issue)

    # The watchers endpoint returns 200 even for users it cannot add
    # (nonexistent, locked, or non-member), so watchers need the same
    # read-back check. Redmine renders the watchers include only when the
    # API user may view watchers; without it the check is skipped.
    if watcher_user_ids is not None and "watchers" in updated_issue:
        actual_watchers = {
            watcher.get("id") for watcher in updated_issue["watchers"]
        }
        for user_id in watcher_user_ids:
            if user_id not in actual_watchers:
                unapplied.append(
                    {
                        "field": "watcher_user_ids",
                        "requested": user_id,
                        "actual": None,
                    }
                )
    updated_issue.pop("watchers", None)

    if unapplied:
        raise RedmineError(
            format_update_error_message(
                unapplied, updated_issue.get("allowed_statuses")
            )
        )

    # allowed_statuses was only needed for the error message above (and is
    # absent on Redmine < 5.0); keep the response shape stable.
    updated_issue.pop("allowed_statuses", None)

    # Avoid re-sending a large unchanged description into the caller's
    # context when this update did not touch it.
    if description is None and description_patches is None:
        current_desc = updated_issue.get("description")
        if isinstance(current_desc, str) and len(current_desc) > 200:
            updated_issue["description"] = (
                current_desc[:200]
                + "... (truncated; use get_issue() for full text)"
            )

    return updated


@mcp.tool()
async def update_issue_journal(
    journal_id: int,
    notes: str,
) -> dict:
    """Update the notes (comment text) of an existing issue journal (comment).

    Use this to edit a comment that was previously added to an issue.
    Journal IDs can be found with get_issue(issue_id, include_journals=True) -
    each entry in the "journals" array has an "id" field.

    Args:
        journal_id: The ID of the journal (comment) to update (required).
            This is the journal's own ID, NOT the issue ID.
        notes: The new comment text (required). Replaces the entire notes.
            WARNING: An empty string deletes the journal entirely if it has
            no associated field changes (Redmine behavior).

    Returns:
        Dictionary containing success flag, journal_id, and the new notes.

    Note:
        Requires Redmine 5.0+ and the "Edit notes" (or "Edit own notes")
        permission.
    """
    client = get_redmine_client()

    request_data = {"journal": {"notes": notes}}

    try:
        response = await client.put(
            f"/journals/{journal_id}.json", json_data=request_data
        )
    except RedmineError as e:
        if e.status_code == 404:
            raise RedmineError(
                f"Journal {journal_id} was not found, OR this Redmine server "
                "is older than 5.0, which does not support editing journal "
                "notes via the REST API. On older servers the comment can "
                "only be edited in the Redmine web UI.",
                404,
            ) from e
        raise

    # Redmine returns an empty body on success; there is no single-journal
    # GET endpoint, so report the values we set.
    if not response:
        return {
            "success": True,
            "journal_id": journal_id,
            "notes": notes,
        }
    return response


# Issue Relations


@mcp.tool()
async def create_issue_relation(
    issue_id: int,
    issue_to_id: int,
    relation_type: str,
    delay: int | None = None,
) -> dict:
    """Create a relation between two issues.

    Args:
        issue_id: Source issue ID (required)
        issue_to_id: Target issue ID to relate to (required)
        relation_type: Type of relation (required). Valid values:
            - "relates" - Related to
            - "duplicates" - Duplicates (source duplicates target)
            - "duplicated" - Duplicated by (source is duplicated by target)
            - "blocks" - Blocks (source blocks target)
            - "blocked" - Blocked by (source is blocked by target)
            - "precedes" - Precedes (source must finish before target)
            - "follows" - Follows (source starts after target finishes)
            - "copied_to" - Copied to
            - "copied_from" - Copied from
        delay: Optional delay in days (only for "precedes" or "follows" relations)

    Returns:
        Dictionary containing the created relation information including relation ID

    Note:
        Some relation types automatically create their inverse:
        - "duplicates" creates "duplicated" on the other side
        - "blocks" creates "blocked" on the other side
        - "precedes" creates "follows" on the other side

        The Redmine REST API has no update operation for relations.
        To change an existing relation, delete it with
        delete_issue_relation() and create a new one.
    """
    client = get_redmine_client()

    # Valid relation types
    valid_types = [
        "relates",
        "duplicates",
        "duplicated",
        "blocks",
        "blocked",
        "precedes",
        "follows",
        "copied_to",
        "copied_from",
    ]

    if relation_type not in valid_types:
        raise ValueError(
            f"Invalid relation_type '{relation_type}'. "
            f"Valid values are: {', '.join(valid_types)}"
        )

    # Build relation data
    relation_data = {
        "issue_to_id": issue_to_id,
        "relation_type": relation_type,
    }

    # Add delay if specified (only valid for precedes/follows)
    if delay is not None:
        if relation_type not in ["precedes", "follows"]:
            raise ValueError(
                f"delay parameter is only valid for 'precedes' or 'follows' relations, "
                f"not for '{relation_type}'"
            )
        relation_data["delay"] = delay

    # Wrap in "relation" key as required by Redmine API
    request_data = {"relation": relation_data}

    response = await client.post(
        f"/issues/{issue_id}/relations.json", json_data=request_data
    )
    return response


@mcp.tool()
async def delete_issue_relation(relation_id: int) -> dict:
    """Delete a relation between issues.

    Args:
        relation_id: The ID of the relation to delete (required)

    Returns:
        Empty dictionary on success (Redmine returns 204 No Content)

    Note:
        To get relation IDs, use get_issue() with the issue ID and look at
        the "relations" array in the response. Each relation has an "id" field.

        Relations cannot be updated; delete and re-create to change one.
    """
    client = get_redmine_client()
    response = await client.delete(f"/relations/{relation_id}.json")
    return response


# Attachment Operations


@mcp.tool()
async def get_attachment(attachment_id: int) -> dict:
    """Get metadata about a specific attachment.

    Args:
        attachment_id: The ID of the attachment to retrieve

    Returns:
        Dictionary containing attachment metadata:
        - id: Attachment ID
        - filename: Original filename
        - filesize: File size in bytes
        - content_type: MIME type of the file
        - description: Optional description
        - content_url: URL to download the file
        - author: Author information (id, name)
        - created_on: Creation timestamp

    Note:
        To get attachment IDs, use get_issue() which includes attachments
        in the response when they exist on the issue.
    """
    client = get_redmine_client()
    response = await client.get(f"/attachments/{attachment_id}.json")
    return response


@mcp.tool()
async def download_attachment(
    attachment_id: int,
    save_path: str,
) -> dict:
    """Download an attachment and save it to the specified path.

    Args:
        attachment_id: The ID of the attachment to download
        save_path: Absolute path where the file should be saved

    Returns:
        Dictionary containing:
        - success: True if download succeeded
        - file_path: The path where the file was saved
        - filename: Original filename from Redmine
        - size: File size in bytes

    Note:
        The parent directory will be created automatically if it doesn't exist.
        The caller is responsible for validating save_path to prevent
        path traversal attacks or writing to sensitive locations.
    """
    client = get_redmine_client()

    # First, get attachment metadata to obtain content_url
    attachment_response = await client.get(f"/attachments/{attachment_id}.json")
    attachment = attachment_response.get("attachment", {})

    content_url = attachment.get("content_url")
    if not content_url:
        raise RedmineError(
            f"Could not get download URL for attachment {attachment_id}"
        )

    filename = attachment.get("filename", f"attachment_{attachment_id}")

    # Download the file
    file_size = await client.download_file(content_url, save_path)

    return {
        "success": True,
        "file_path": save_path,
        "filename": filename,
        "size": file_size,
    }


@mcp.tool()
async def upload_attachment(
    file_path: str,
    filename: str | None = None,
) -> dict:
    """Upload a file to Redmine and get an upload token.

    The returned token can be used to attach the file to an issue
    using create_issue() or update_issue() with the 'uploads' parameter.

    Args:
        file_path: Absolute path to the file to upload
        filename: Optional filename to use in Redmine (defaults to the file's basename)

    Returns:
        Dictionary containing:
        - token: Upload token to use when attaching to an issue
        - filename: The filename that will be used

    Example:
        # Step 1: Upload the file
        result = upload_attachment("/path/to/report.pdf")
        token = result["token"]

        # Step 2: Attach to an issue
        update_issue(
            issue_id=123,
            uploads=[{
                "token": token,
                "filename": "report.pdf",
                "content_type": "application/pdf",
                "description": "Monthly report"
            }]
        )

    Note:
        The caller is responsible for validating file_path to prevent
        unauthorized file access.
    """
    client = get_redmine_client()

    # Upload file and get token
    response = await client.upload_file(file_path, filename)

    upload_data = response.get("upload", {})
    token = upload_data.get("token")

    if not token:
        raise RedmineError("Failed to get upload token from Redmine")

    actual_filename = filename or Path(file_path).name

    return {
        "token": token,
        "filename": actual_filename,
    }


@mcp.tool()
async def update_attachment(
    attachment_id: int,
    filename: str | None = None,
    description: str | None = None,
) -> dict:
    """Update the metadata (filename and/or description) of an attachment.

    The file content itself cannot be changed - delete the attachment and
    upload a new file instead.

    Args:
        attachment_id: The ID of the attachment to update (required)
        filename: New filename (optional)
        description: New description (optional). Pass an empty string to
            clear the description.

    Returns:
        Dictionary containing the updated attachment metadata.

    Note:
        Requires Redmine 3.4 or later.
    """
    client = get_redmine_client()

    attachment_data = {}
    if filename is not None:
        attachment_data["filename"] = filename
    if description is not None:
        attachment_data["description"] = description

    if not attachment_data:
        raise ValueError(
            "At least one of 'filename' or 'description' must be provided"
        )

    request_data = {"attachment": attachment_data}

    # Undocumented API: PATCH /attachments/:id, added in Redmine 3.4
    # (redmine.org issue #22356).
    try:
        await client.patch(
            f"/attachments/{attachment_id}.json", json_data=request_data
        )
    except RedmineError as e:
        if e.status_code in (404, 405):
            raise RedmineError(
                f"Attachment {attachment_id} was not found, OR this Redmine "
                "server is older than 3.4, which does not support updating "
                "attachments via the REST API.",
                e.status_code,
            ) from e
        raise

    # Fetch the attachment back so the caller sees the persisted state
    return await client.get(f"/attachments/{attachment_id}.json")


@mcp.tool()
async def delete_attachment(attachment_id: int) -> dict:
    """Delete an attachment from Redmine.

    Args:
        attachment_id: The ID of the attachment to delete

    Returns:
        Dictionary containing:
        - success: True if deletion succeeded
        - message: Confirmation message

    Note:
        This permanently removes the attachment from the issue.
        The user must have permission to delete attachments.
    """
    client = get_redmine_client()
    await client.delete(f"/attachments/{attachment_id}.json")

    return {
        "success": True,
        "message": f"Attachment {attachment_id} deleted successfully",
    }


# Metadata Operations

@mcp.tool()
async def list_trackers() -> dict:
    """List all available trackers (issue types).

    Trackers define the type of issue (e.g., Bug, Feature, Support).
    Use this to get tracker IDs for creating or updating issues.

    Returns:
        Dictionary containing list of trackers with id, name, and description
    """
    client = get_redmine_client()
    response = await client.get("/trackers.json")
    return response


@mcp.tool()
async def list_issue_statuses() -> dict:
    """List all available issue statuses.

    Statuses define the state of an issue (e.g., New, In Progress, Resolved, Closed).
    Use this to get status IDs for creating or updating issues.

    Returns:
        Dictionary containing list of statuses with id, name, and is_closed flag
    """
    client = get_redmine_client()
    response = await client.get("/issue_statuses.json")
    return response


@mcp.tool()
async def list_priorities() -> dict:
    """List all available issue priorities.

    Priorities define the urgency of an issue (e.g., Low, Normal, High, Urgent).
    Use this to get priority IDs for creating or updating issues.

    Returns:
        Dictionary containing list of priorities with id, name, and is_default flag
    """
    client = get_redmine_client()
    response = await client.get("/enumerations/issue_priorities.json")
    return response


@mcp.tool()
async def list_users(status: int = 1, limit: int = 100) -> dict:
    """List Redmine users.

    Use this to get user IDs for assigning issues.

    Args:
        status: User status filter (1=active, 3=locked, default: 1)
        limit: Maximum number of users to return (default: 100)

    Returns:
        Dictionary containing list of users with id, login, firstname, lastname, and mail
    """
    client = get_redmine_client()
    params = {"status": status, "limit": limit}
    response = await client.get("/users.json", params=params)
    return response


@mcp.tool()
async def get_project_members(project_id: int) -> dict:
    """Get members of a specific project.

    Use this to see who can be assigned to issues in a project.

    Args:
        project_id: The ID of the project

    Returns:
        Dictionary containing list of project members with user and role information
    """
    client = get_redmine_client()
    response = await client.get(f"/projects/{project_id}/memberships.json")
    return response


# Wiki Operations


@mcp.tool()
async def list_wiki_pages(
    project_id: int | str,
) -> dict:
    """List all wiki pages in a project.

    Args:
        project_id: Project ID (numeric) or project identifier (string) (required)

    Returns:
        Dictionary containing:
        - wiki_pages: List of wiki pages with title, version, created_on, updated_on
    """
    client = get_redmine_client()
    response = await client.get(f"/projects/{project_id}/wiki/index.json")
    return response


@mcp.tool()
async def get_wiki_page(
    project_id: int | str,
    title: str,
    include_attachments: bool = False,
) -> dict:
    """Get a specific wiki page content.

    Args:
        project_id: Project ID (numeric) or project identifier (string) (required)
        title: Wiki page title (required)
        include_attachments: Include attachment information in response (default: False)

    Returns:
        Dictionary containing:
        - wiki_page: Page details including title, text, version, author, created_on, updated_on
        - attachments: List of attachments (if include_attachments is True)
    """
    client = get_redmine_client()
    params = None
    if include_attachments:
        params = {"include": "attachments"}
    response = await client.get(
        f"/projects/{project_id}/wiki/{title}.json",
        params=params,
    )
    return response


@mcp.tool()
async def get_wiki_page_version(
    project_id: int | str,
    title: str,
    version: int,
) -> dict:
    """Get a specific version of a wiki page.

    Args:
        project_id: Project ID (numeric) or project identifier (string) (required)
        title: Wiki page title (required)
        version: Version number to retrieve (required)

    Returns:
        Dictionary containing the wiki page content at the specified version

    Note:
        Use this to view the history of a wiki page or compare versions.
    """
    client = get_redmine_client()
    response = await client.get(
        f"/projects/{project_id}/wiki/{title}/{version}.json"
    )
    return response


@mcp.tool()
async def create_or_update_wiki_page(
    project_id: int | str,
    title: str,
    text: str | None = None,
    text_patches: list[dict] | None = None,
    comments: str | None = None,
    parent_title: str | None = None,
    uploads: list[dict] | None = None,
) -> dict:
    """Create a new wiki page or update an existing one.

    CONTENT - provide exactly one of text or text_patches (mutually exclusive):
      - text: Full page content. Required when creating a new page. For updates, replaces entire content.
      - text_patches: Apply targeted find-and-replace edits to the existing page content.
        Format: [{"old_text": "text to find", "new_text": "replacement"}]
        Optional "replace_all": true to replace all occurrences (default: false).
        Only works on existing pages. Cannot be used to create new pages.

    METADATA-ONLY UPDATE:
      For existing pages, you can update only metadata (parent_title, comments, uploads)
      without providing text or text_patches.

    Args:
        project_id: Project ID (numeric) or project identifier (string) (required)
        title: Wiki page title (required)
        text: Full page content in Textile or Markdown format.
            Required for creating new pages. Replaces entire content on update.
            Cannot be used together with text_patches.
        text_patches: List of find-and-replace edits for the existing page content.
            Each dict: {"old_text": "text to find", "new_text": "replacement"}.
            Optional "replace_all": true to replace all occurrences (default: false).
            Example: [{"old_text": "## Old Section", "new_text": "## New Section"}]
            IMPORTANT: Use get_wiki_page() first to see exact current content before constructing patches.
            Cannot be used together with text. Only works on existing pages.
        comments: Comment describing the change (optional)
        parent_title: Title of the parent page for hierarchy (optional)
        uploads: List of file uploads to attach. Each upload should be a dictionary with:
            - token: Upload token from upload_attachment() (required)
            - filename: Filename to use in Redmine (required)
            - content_type: MIME type (optional)
            - description: File description (optional)

    Returns:
        Dictionary containing the created/updated wiki page information

    Note:
        - Redmine automatically manages version history
        - Use existing upload_attachment() to get upload tokens for attachments
    """
    client = get_redmine_client()

    if text is not None and text_patches is not None:
        raise ValueError(
            "Cannot provide both 'text' and 'text_patches'. "
            "Use 'text' for full content, or 'text_patches' for partial edits."
        )
    if text is not None and text == "":
        raise ValueError("text field cannot be empty string")

    metadata_only = text is None and text_patches is None

    if metadata_only:
        if not any([parent_title, comments, uploads]):
            raise ValueError(
                "Either 'text' (for full content), 'text_patches' (for partial edits), "
                "or at least one metadata field (parent_title, comments, uploads) must be provided."
            )
        # Fetch current text (Redmine API requires text field even for metadata-only updates)
        try:
            current_page = await client.get(
                f"/projects/{project_id}/wiki/{title}.json"
            )
            text = current_page.get("wiki_page", {}).get("text", "")
        except RedmineError as e:
            if e.status_code == 404:
                raise ValueError(
                    "Cannot perform metadata-only update on a page that doesn't exist. "
                    "Use 'text' to create a new page."
                )
            raise

    wiki_page_data = {}

    if text_patches is not None:
        try:
            current_page = await client.get(
                f"/projects/{project_id}/wiki/{title}.json"
            )
            current_text = current_page.get("wiki_page", {}).get("text", "")
            current_version = current_page.get("wiki_page", {}).get("version")
        except RedmineError as e:
            if e.status_code == 404:
                raise ValueError(
                    "Cannot use text_patches on a page that doesn't exist. "
                    "Use 'text' to create a new page."
                )
            raise
        if not current_text:
            raise ValueError(
                "Cannot apply text_patches: wiki page has no content. "
                "Use 'text' to set initial content."
            )
        text = apply_patches(current_text, text_patches)
        if not text.strip():
            raise ValueError(
                "Patch result would produce empty content, which Redmine does not allow."
            )
        # Optimistic locking: include version to detect concurrent edits
        if current_version is not None:
            wiki_page_data["version"] = current_version

    if text is not None:
        wiki_page_data["text"] = text

    if comments:
        wiki_page_data["comments"] = comments
    if parent_title:
        wiki_page_data["parent_title"] = parent_title
    if uploads:
        wiki_page_data["uploads"] = uploads

    request_data = {"wiki_page": wiki_page_data}

    response = await client.put(
        f"/projects/{project_id}/wiki/{title}.json",
        json_data=request_data,
    )

    # Redmine returns empty response on successful update, so fetch the page
    if not response:
        return await get_wiki_page(project_id, title)

    return response


@mcp.tool()
async def delete_wiki_page(
    project_id: int | str,
    title: str,
) -> dict:
    """Delete a wiki page.

    Args:
        project_id: Project ID (numeric) or project identifier (string) (required)
        title: Wiki page title to delete (required)

    Returns:
        Empty dictionary on success (Redmine returns 204 No Content)

    Note:
        This permanently deletes the wiki page and all its version history.
        The user must have permission to delete wiki pages.
    """
    client = get_redmine_client()
    response = await client.delete(f"/projects/{project_id}/wiki/{title}.json")
    return response


def main():
    """Main entry point for the MCP server."""
    try:
        # Validate configuration on startup
        get_redmine_client()

        # Run the server with stdio transport
        mcp.run(transport="stdio")
    except RedmineError as e:
        print(f"Configuration error: {e.message}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
