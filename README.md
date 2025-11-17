# Redmine MCP Server

A Model Context Protocol (MCP) server that enables Claude Code to interact with Redmine project management systems.

## Features

This server provides 11 tools across three categories:

**Project Operations**
- List and retrieve project details
- Get project members and permissions

**Issue Management**
- Search, create, and update issues (tickets)
- Add comments and track progress
- Support for filtering by project, tracker, status, assignee, and priority

**Metadata**
- List trackers, statuses, priorities, and users
- Essential for creating and updating issues correctly

## Installation

**Prerequisites:** Python 3.11+, [uv](https://github.com/astral-sh/uv) package manager, and a Redmine instance with REST API enabled.

```bash
git clone <repository-url>
cd mcp-redmine
uv sync
```

## Configuration

### Get Your Redmine API Key

1. Log in to your Redmine instance
2. Go to "My account" (top right menu)
3. Click "Show" under "API access key"
4. Copy the API key

### Add to Claude Code (Recommended)

Use the `claude mcp add` command to easily configure the server:

```bash
claude mcp add --transport stdio redmine \
  --env REDMINE_URL=https://redmine.example.com \
  --env REDMINE_API_KEY=your_api_key_here \
  -- uv --directory /absolute/path/to/mcp-redmine run mcp-redmine
```

**Important:** Replace the following:
- `https://redmine.example.com` - Your Redmine instance URL (include https:// or http://)
- `your_api_key_here` - Your actual Redmine API key
- `/absolute/path/to/mcp-redmine` - Full path to this project directory

Restart Claude Code after adding the server.

### Manual Configuration

Alternatively, add this to your Claude Code MCP settings file (`~/.config/claude-code/mcp.json` or similar):

```json
{
  "mcpServers": {
    "redmine": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/mcp-redmine",
        "run",
        "mcp-redmine"
      ],
      "env": {
        "REDMINE_URL": "https://redmine.example.com",
        "REDMINE_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### Local Development

For local testing, you can use a `.env` file. Copy `.env.example` to `.env` and fill in your values. Note that the MCP configuration's `env` section takes precedence over `.env` files.

## Usage

Once configured, use Claude Code to interact with Redmine naturally:

```
"Show me all open issues in project 5"
"Create a bug in project 3 titled 'Login page error'"
"Update issue 123 to 'In Progress' and add a comment"
"Who are the members of project 2?"
"What trackers are available?"
```

Claude will automatically use the appropriate tools to fulfill your requests.

## Troubleshooting

**Authentication errors:**
- Verify your API key is correct
- Check that REST API is enabled in Redmine (Administration → Settings → API tab)
- Ensure your user account has appropriate permissions

**Connection errors:**
- Verify REDMINE_URL is correct with protocol (https:// or http://)
- Check that the Redmine server is accessible from your network

**Tools not appearing:**
- Verify the MCP server path in your configuration is absolute and correct
- Restart Claude Code after making configuration changes
- Run `claude mcp list` to verify the server is registered

## Limitations

Current version does not support:
- Time tracking entries
- File attachments upload
- Custom fields
- Wiki pages
- Bulk operations

These features may be added in future versions based on demand.

## License

MIT License

## Resources

- [Model Context Protocol Specification](https://spec.modelcontextprotocol.io/)
- [Redmine REST API Documentation](https://www.redmine.org/projects/redmine/wiki/Rest_api)
