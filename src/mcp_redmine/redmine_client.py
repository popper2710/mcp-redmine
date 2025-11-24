"""Redmine API client implementation."""

import httpx
from typing import Any, Dict, Optional
from .models import RedmineConfig, RedmineError


class RedmineClient:
    """Async HTTP client for Redmine REST API."""

    def __init__(self, config: RedmineConfig):
        """Initialize Redmine client.

        Args:
            config: Redmine configuration containing URL and API key
        """
        self.config = config
        self.base_url = config.url.rstrip("/")
        self.headers = {
            "X-Redmine-API-Key": config.api_key,
            "Content-Type": "application/json",
        }
        self.timeout = config.timeout
        # Initialize persistent HTTP client for connection pooling
        self._http_client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=self.headers,
        )

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request to Redmine API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON body for POST/PUT requests

        Returns:
            JSON response as dictionary

        Raises:
            RedmineError: If the request fails
        """
        url = f"{self.base_url}{endpoint}"

        try:
            response = await self._http_client.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
            )

            # Handle HTTP errors
            if response.status_code >= 400:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                if response.status_code == 401:
                    error_msg = "Authentication failed. Please check your API key."
                elif response.status_code == 403:
                    error_msg = "Access forbidden. Please check your permissions."
                elif response.status_code == 404:
                    error_msg = "Resource not found."
                elif response.status_code >= 500:
                    error_msg = f"Redmine server error: {response.status_code}"

                raise RedmineError(error_msg, response.status_code)

            # Return JSON response (handle empty responses from successful updates)
            if response.text.strip():
                return response.json()
            else:
                # Empty response (common for successful PUT/DELETE operations)
                return {}

        except httpx.TimeoutException as e:
            raise RedmineError(f"Request timeout after {self.timeout} seconds") from e
        except httpx.ConnectError as e:
            raise RedmineError(
                f"Failed to connect to Redmine at {self.base_url}"
            ) from e
        except httpx.HTTPError as e:
            raise RedmineError(f"HTTP error occurred: {str(e)}") from e
        except Exception as e:
            raise RedmineError(f"Unexpected error: {str(e)}") from e

    async def get(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a GET request.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response
        """
        return await self._request("GET", endpoint, params=params)

    async def post(
        self, endpoint: str, json_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Make a POST request.

        Args:
            endpoint: API endpoint path
            json_data: JSON body

        Returns:
            JSON response
        """
        return await self._request("POST", endpoint, json_data=json_data)

    async def put(
        self, endpoint: str, json_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Make a PUT request.

        Args:
            endpoint: API endpoint path
            json_data: JSON body

        Returns:
            JSON response
        """
        return await self._request("PUT", endpoint, json_data=json_data)

    async def delete(self, endpoint: str) -> Dict[str, Any]:
        """Make a DELETE request.

        Args:
            endpoint: API endpoint path

        Returns:
            JSON response
        """
        return await self._request("DELETE", endpoint)
