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
async def list_projects() -> dict:
    """List all accessible Redmine projects.

    Returns:
        Dictionary containing the list of projects with their details
        (id, name, identifier, description, status, etc.)
    """
    try:
        client = get_redmine_client()
        response = await client.get("/projects.json")
        return response
    except RedmineError as e:
        return {"error": e.message, "status_code": e.status_code}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
async def get_project(project_id: int) -> dict:
    """Get detailed information about a specific project.

    Args:
        project_id: The ID of the project to retrieve

    Returns:
        Dictionary containing detailed project information including
        trackers, issue categories, and other metadata
    """
    try:
        client = get_redmine_client()
        response = await client.get(f"/projects/{project_id}.json")
        return response
    except RedmineError as e:
        return {"error": e.message, "status_code": e.status_code}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
async def get_issue(issue_id: int) -> dict:
    """Get detailed information about a specific issue (ticket).

    Args:
        issue_id: The ID of the issue to retrieve

    Returns:
        Dictionary containing detailed issue information including
        journals (comments), attachments, and relations
    """
    try:
        client = get_redmine_client()
        # Include associated data: journals, children, attachments, relations
        params = {"include": "journals,children,attachments,relations"}
        response = await client.get(f"/issues/{issue_id}.json", params=params)
        return response
    except RedmineError as e:
        return {"error": e.message, "status_code": e.status_code}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


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
    try:
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
    except RedmineError as e:
        return {"error": e.message, "status_code": e.status_code}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
async def create_issue(
    project_id: int,
    subject: str,
    description: str = "",
    tracker_id: int | None = None,
    status_id: int | None = None,
    priority_id: int | None = None,
    assigned_to_id: int | None = None,
    parent_issue_id: int | None = None,
    start_date: str | None = None,
    due_date: str | None = None,
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
        parent_issue_id: Parent issue ID for subtasks (optional)
        start_date: Start date in YYYY-MM-DD format (optional)
        due_date: Due date in YYYY-MM-DD format (optional)

    Returns:
        Dictionary containing the created issue information including its ID
    """
    try:
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
        if parent_issue_id is not None:
            issue_data["parent_issue_id"] = parent_issue_id
        if start_date is not None:
            issue_data["start_date"] = start_date
        if due_date is not None:
            issue_data["due_date"] = due_date

        # Wrap in "issue" key as required by Redmine API
        request_data = {"issue": issue_data}

        response = await client.post("/issues.json", json_data=request_data)
        return response
    except RedmineError as e:
        return {"error": e.message, "status_code": e.status_code}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
async def update_issue(
    issue_id: int,
    subject: str | None = None,
    description: str | None = None,
    tracker_id: int | None = None,
    status_id: int | None = None,
    priority_id: int | None = None,
    assigned_to_id: int | None = None,
    notes: str | None = None,
    done_ratio: int | None = None,
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
        notes: Comment to add to the issue history (optional)
        done_ratio: Progress percentage 0-100 (optional)

    Returns:
        Dictionary containing the updated issue information or empty dict on success
        (Redmine API returns 200 with no content on successful PUT)
    """
    try:
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
        if notes is not None:
            issue_data["notes"] = notes
        if done_ratio is not None:
            # Validate range
            if not 0 <= done_ratio <= 100:
                return {"error": "done_ratio must be between 0 and 100"}
            issue_data["done_ratio"] = done_ratio

        # Check if at least one field is being updated
        if not issue_data:
            return {"error": "At least one field must be specified for update"}

        # Wrap in "issue" key as required by Redmine API
        request_data = {"issue": issue_data}

        response = await client.put(f"/issues/{issue_id}.json", json_data=request_data)

        # Redmine returns empty response on successful update, so fetch the updated issue
        if not response:
            # Fetch updated issue to return
            updated_issue = await client.get(f"/issues/{issue_id}.json")
            return updated_issue

        return response
    except RedmineError as e:
        return {"error": e.message, "status_code": e.status_code}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# Metadata Operations

@mcp.tool()
async def list_trackers() -> dict:
    """List all available trackers (issue types).

    Trackers define the type of issue (e.g., Bug, Feature, Support).
    Use this to get tracker IDs for creating or updating issues.

    Returns:
        Dictionary containing list of trackers with id, name, and description
    """
    try:
        client = get_redmine_client()
        response = await client.get("/trackers.json")
        return response
    except RedmineError as e:
        return {"error": e.message, "status_code": e.status_code}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
async def list_issue_statuses() -> dict:
    """List all available issue statuses.

    Statuses define the state of an issue (e.g., New, In Progress, Resolved, Closed).
    Use this to get status IDs for creating or updating issues.

    Returns:
        Dictionary containing list of statuses with id, name, and is_closed flag
    """
    try:
        client = get_redmine_client()
        response = await client.get("/issue_statuses.json")
        return response
    except RedmineError as e:
        return {"error": e.message, "status_code": e.status_code}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
async def list_priorities() -> dict:
    """List all available issue priorities.

    Priorities define the urgency of an issue (e.g., Low, Normal, High, Urgent).
    Use this to get priority IDs for creating or updating issues.

    Returns:
        Dictionary containing list of priorities with id, name, and is_default flag
    """
    try:
        client = get_redmine_client()
        response = await client.get("/enumerations/issue_priorities.json")
        return response
    except RedmineError as e:
        return {"error": e.message, "status_code": e.status_code}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


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
    try:
        client = get_redmine_client()
        params = {"status": status, "limit": limit}
        response = await client.get("/users.json", params=params)
        return response
    except RedmineError as e:
        return {"error": e.message, "status_code": e.status_code}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
async def get_project_members(project_id: int) -> dict:
    """Get members of a specific project.

    Use this to see who can be assigned to issues in a project.

    Args:
        project_id: The ID of the project

    Returns:
        Dictionary containing list of project members with user and role information
    """
    try:
        client = get_redmine_client()
        response = await client.get(f"/projects/{project_id}/memberships.json")
        return response
    except RedmineError as e:
        return {"error": e.message, "status_code": e.status_code}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


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
