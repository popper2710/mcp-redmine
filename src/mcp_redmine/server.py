"""Redmine MCP Server - Main entry point."""

import os
import sys
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .models import RedmineConfig, RedmineError
from .redmine_client import RedmineClient

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
async def get_project(project_id: int) -> dict:
    """Get detailed information about a specific project.

    Args:
        project_id: The ID of the project to retrieve

    Returns:
        Dictionary containing detailed project information including
        trackers, issue categories, and other metadata
    """
    client = get_redmine_client()
    response = await client.get(f"/projects/{project_id}.json")
    return response


@mcp.tool()
async def get_issue(issue_id: int) -> dict:
    """Get detailed information about a specific issue (ticket).

    Args:
        issue_id: The ID of the issue to retrieve

    Returns:
        Dictionary containing detailed issue information including
        journals (comments), attachments, and relations
    """
    client = get_redmine_client()
    # Include associated data: journals, children, attachments, relations
    params = {"include": "journals,children,attachments,relations"}
    response = await client.get(f"/issues/{issue_id}.json", params=params)
    return response


# Issue Operations

@mcp.tool()
async def list_issues(
    project_id: int | None = None,
    tracker_id: int | None = None,
    status_id: str = "*",
    assigned_to_id: int | None = None,
    priority_id: int | None = None,
    limit: int = 25,
    offset: int = 0,
) -> dict:
    """Search and list issues (tickets) with various filters.

    Args:
        project_id: Filter by project ID (optional)
        tracker_id: Filter by tracker ID (optional)
        status_id: Filter by status - "open", "closed", or "*" for all (default: "*")
        assigned_to_id: Filter by assigned user ID (optional)
        priority_id: Filter by priority ID (optional)
        limit: Maximum number of issues to return (default: 25, max: 100)
        offset: Offset for pagination (default: 0)

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
    return response


@mcp.tool()
async def create_issue(
    project_id: int,
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
) -> dict:
    """Create a new issue (ticket) in Redmine.

    Args:
        project_id: Project ID (required)
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

    Returns:
        Dictionary containing the created issue information including its ID
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

    # Wrap in "issue" key as required by Redmine API
    request_data = {"issue": issue_data}

    response = await client.post("/issues.json", json_data=request_data)
    return response


@mcp.tool()
async def update_issue(
    issue_id: int,
    subject: str | None = None,
    description: str | None = None,
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
) -> dict:
    """Update an existing issue (ticket).

    Args:
        issue_id: Issue ID to update (required)
        subject: New subject/title (optional)
        description: New description (optional)
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
        watcher_user_ids: List of user IDs to add as watchers (optional, requires Redmine 2.3.0+)
        custom_fields: List of custom field dictionaries with 'id' and 'value' keys (optional)
        notes: Comment to add to the issue history (optional)
        private_notes: Whether the notes are private (optional)

    Returns:
        Dictionary containing the updated issue information or empty dict on success
        (Redmine API returns 200 with no content on successful PUT)
    """
    client = get_redmine_client()

    # Build issue update data
    issue_data = {}

    # Add fields to update
    if subject is not None:
        issue_data["subject"] = subject
    if description is not None:
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
    if notes is not None:
        issue_data["notes"] = notes
    if private_notes is not None:
        issue_data["private_notes"] = private_notes

    # Check if at least one field is being updated
    if not issue_data:
        raise ValueError("At least one field must be specified for update")

    # Wrap in "issue" key as required by Redmine API
    request_data = {"issue": issue_data}

    response = await client.put(f"/issues/{issue_id}.json", json_data=request_data)

    # Redmine returns empty response on successful update, so fetch the updated issue
    if not response:
        # Fetch updated issue to return
        updated_issue = await client.get(f"/issues/{issue_id}.json")
        return updated_issue

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
    """
    client = get_redmine_client()
    response = await client.delete(f"/relations/{relation_id}.json")
    return response


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
