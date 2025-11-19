#!/usr/bin/env python3
"""Comprehensive test script for identifier support and search functionality."""

import asyncio
import os
from dotenv import load_dotenv
from src.mcp_redmine.models import RedmineConfig
from src.mcp_redmine.redmine_client import RedmineClient

load_dotenv()

# Test results tracking
results = {
    "passed": 0,
    "failed": 0,
    "tests": []
}

def print_header(text):
    """Print a formatted test header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def record_result(test_name, success, message=""):
    """Record a test result."""
    results["tests"].append({
        "name": test_name,
        "success": success,
        "message": message
    })
    if success:
        results["passed"] += 1
        print(f"✓ {test_name}")
        if message:
            print(f"  → {message}")
    else:
        results["failed"] += 1
        print(f"✗ {test_name}")
        print(f"  → {message}")

async def test_get_project(client):
    """Test get_project with numeric ID and string identifier."""
    print_header("Test 1: get_project - Numeric ID")
    try:
        result = await client.get("/projects/1.json")
        project_name = result["project"]["name"]
        record_result(
            "get_project with numeric ID",
            True,
            f"Retrieved project: {project_name}"
        )
        return result["project"]["identifier"]
    except Exception as e:
        record_result("get_project with numeric ID", False, str(e))
        return None

async def test_get_project_identifier(client, identifier):
    """Test get_project with string identifier."""
    print_header("Test 2: get_project - String Identifier")
    try:
        result = await client.get(f"/projects/{identifier}.json")
        project_name = result["project"]["name"]
        record_result(
            "get_project with string identifier",
            True,
            f"Retrieved project: {project_name}"
        )
    except Exception as e:
        record_result("get_project with string identifier", False, str(e))

async def test_create_issue_numeric(client):
    """Test create_issue with numeric project_id."""
    print_header("Test 3: create_issue - Numeric project_id")
    try:
        issue_data = {
            "issue": {
                "project_id": 1,
                "subject": "Test: Numeric project_id",
                "description": "Testing create_issue with numeric ID"
            }
        }
        result = await client.post("/issues.json", json_data=issue_data)
        issue_id = result["issue"]["id"]
        record_result(
            "create_issue with numeric project_id",
            True,
            f"Created issue #{issue_id}"
        )
        return issue_id
    except Exception as e:
        record_result("create_issue with numeric project_id", False, str(e))
        return None

async def test_create_issue_identifier(client, identifier):
    """Test create_issue with string identifier."""
    print_header("Test 4: create_issue - String Identifier")
    try:
        issue_data = {
            "issue": {
                "project_id": identifier,
                "subject": "Test: String identifier",
                "description": "Testing create_issue with string identifier"
            }
        }
        result = await client.post("/issues.json", json_data=issue_data)
        issue_id = result["issue"]["id"]
        record_result(
            "create_issue with string identifier",
            True,
            f"Created issue #{issue_id}"
        )
        return issue_id
    except Exception as e:
        record_result("create_issue with string identifier", False, str(e))
        return None

async def test_list_issues_numeric(client):
    """Test list_issues with numeric project_id."""
    print_header("Test 5: list_issues - Numeric project_id")
    try:
        params = {"project_id": 1, "limit": 5}
        result = await client.get("/issues.json", params=params)
        count = result["total_count"]
        record_result(
            "list_issues with numeric project_id",
            True,
            f"Found {count} issues"
        )
    except Exception as e:
        record_result("list_issues with numeric project_id", False, str(e))

async def test_list_issues_identifier(client, identifier):
    """Test list_issues with string identifier."""
    print_header("Test 6: list_issues - String Identifier")
    try:
        params = {"project_id": identifier, "limit": 5}
        result = await client.get("/issues.json", params=params)
        count = result["total_count"]
        record_result(
            "list_issues with string identifier",
            True,
            f"Found {count} issues"
        )
    except Exception as e:
        record_result("list_issues with string identifier", False, str(e))

async def test_search_projects(client):
    """Test search_projects functionality."""
    print_header("Test 7: search_projects - Exact Match")
    try:
        # Get all projects first
        all_projects = await client.get("/projects.json")
        projects_list = all_projects.get("projects", [])

        if not projects_list:
            record_result("search_projects - exact match", False, "No projects available")
            return

        # Use first project for testing
        test_project = projects_list[0]
        project_name = test_project["name"]

        # Test with part of the name
        search_term = project_name[:3]  # First 3 characters

        # Perform search locally (simulating the search_projects tool)
        query_lower = search_term.lower()
        matches = [
            p for p in projects_list
            if (query_lower in p.get("name", "").lower() or
                query_lower in p.get("identifier", "").lower() or
                query_lower in p.get("description", "").lower())
        ]

        if matches:
            record_result(
                "search_projects with partial name",
                True,
                f"Query '{search_term}' found {len(matches)} project(s)"
            )
        else:
            record_result(
                "search_projects with partial name",
                False,
                f"Query '{search_term}' found no matches"
            )

    except Exception as e:
        record_result("search_projects", False, str(e))

async def test_search_projects_identifier(client, identifier):
    """Test search_projects with identifier."""
    print_header("Test 8: search_projects - Identifier Search")
    try:
        all_projects = await client.get("/projects.json")
        projects_list = all_projects.get("projects", [])

        # Search with part of identifier
        search_term = identifier[:3] if len(identifier) >= 3 else identifier
        query_lower = search_term.lower()

        matches = [
            p for p in projects_list
            if (query_lower in p.get("name", "").lower() or
                query_lower in p.get("identifier", "").lower() or
                query_lower in p.get("description", "").lower())
        ]

        if matches:
            record_result(
                "search_projects with identifier substring",
                True,
                f"Query '{search_term}' found {len(matches)} project(s)"
            )
        else:
            record_result(
                "search_projects with identifier substring",
                False,
                f"Query '{search_term}' found no matches"
            )

    except Exception as e:
        record_result("search_projects with identifier", False, str(e))

async def cleanup_issues(client, issue_ids):
    """Clean up test issues."""
    print_header("Cleanup: Deleting Test Issues")
    for issue_id in issue_ids:
        if issue_id:
            try:
                await client.delete(f"/issues/{issue_id}.json")
                print(f"✓ Deleted issue #{issue_id}")
            except Exception as e:
                print(f"✗ Failed to delete issue #{issue_id}: {e}")

def print_summary():
    """Print test summary."""
    print("\n" + "=" * 70)
    print("  TEST SUMMARY")
    print("=" * 70)
    print(f"Total Tests: {results['passed'] + results['failed']}")
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")

    if results['failed'] > 0:
        print("\nFailed Tests:")
        for test in results['tests']:
            if not test['success']:
                print(f"  • {test['name']}: {test['message']}")

    print("\n" + "=" * 70)
    if results['failed'] == 0:
        print("  ✓ ALL TESTS PASSED!")
    else:
        print(f"  ✗ {results['failed']} TEST(S) FAILED")
    print("=" * 70 + "\n")

async def main():
    """Run all tests."""
    # Create client
    config = RedmineConfig(
        url=os.getenv("REDMINE_URL"),
        api_key=os.getenv("REDMINE_API_KEY"),
    )
    client = RedmineClient(config)

    print("\n" + "=" * 70)
    print("  COMPREHENSIVE REDMINE MCP SERVER TEST SUITE")
    print("=" * 70)
    print(f"  Testing against: {config.url}")
    print("=" * 70)

    # Track created issues for cleanup
    created_issues = []

    # Run tests
    identifier = await test_get_project(client)

    if identifier:
        await test_get_project_identifier(client, identifier)

        issue_id_1 = await test_create_issue_numeric(client)
        if issue_id_1:
            created_issues.append(issue_id_1)

        issue_id_2 = await test_create_issue_identifier(client, identifier)
        if issue_id_2:
            created_issues.append(issue_id_2)

        await test_list_issues_numeric(client)
        await test_list_issues_identifier(client, identifier)
        await test_search_projects(client)
        await test_search_projects_identifier(client, identifier)
    else:
        print("\n✗ Cannot continue tests without valid project identifier")

    # Cleanup
    if created_issues:
        await cleanup_issues(client, created_issues)

    # Print summary
    print_summary()

    # Exit with appropriate code
    return 0 if results['failed'] == 0 else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
