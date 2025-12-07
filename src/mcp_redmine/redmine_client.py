"""Redmine API client implementation."""

from pathlib import Path

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

    async def upload_file(
        self,
        file_path: str,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload a file to Redmine and get an upload token.

        This uploads the file content to Redmine's uploads endpoint.
        The returned token can be used to attach the file to issues.

        Args:
            file_path: Absolute path to the file to upload
            filename: Optional filename to use (defaults to file's basename)

        Returns:
            Dictionary containing the upload token:
            {"upload": {"token": "xxx.yyy"}}

        Raises:
            RedmineError: If the file doesn't exist, upload fails,
                         or file size exceeds server limit (422)
        """
        path = Path(file_path)

        if not path.exists():
            raise RedmineError(f"File not found: {file_path}")

        if not path.is_file():
            raise RedmineError(f"Not a file: {file_path}")

        # Use provided filename or extract from path
        upload_filename = filename or path.name

        # Build URL with filename parameter
        url = f"{self.base_url}/uploads.json"
        params = {"filename": upload_filename}

        try:
            # Read file content as binary
            with open(path, "rb") as f:
                file_content = f.read()

            # Make request with octet-stream content type
            response = await self._http_client.post(
                url=url,
                params=params,
                content=file_content,
                headers={
                    "X-Redmine-API-Key": self.config.api_key,
                    "Content-Type": "application/octet-stream",
                },
            )

            # Handle HTTP errors
            if response.status_code >= 400:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                if response.status_code == 401:
                    error_msg = "Authentication failed. Please check your API key."
                elif response.status_code == 403:
                    error_msg = "Access forbidden. Please check your permissions."
                elif response.status_code == 404:
                    error_msg = "Upload endpoint not found."
                elif response.status_code == 422:
                    error_msg = (
                        "File upload failed. The file may exceed the maximum "
                        "allowed size configured on the Redmine server."
                    )
                elif response.status_code >= 500:
                    error_msg = f"Redmine server error: {response.status_code}"

                raise RedmineError(error_msg, response.status_code)

            return response.json()

        except httpx.TimeoutException as e:
            raise RedmineError(f"Upload timeout after {self.timeout} seconds") from e
        except httpx.ConnectError as e:
            raise RedmineError(
                f"Failed to connect to Redmine at {self.base_url}"
            ) from e
        except httpx.HTTPError as e:
            raise RedmineError(f"HTTP error during upload: {str(e)}") from e
        except OSError as e:
            raise RedmineError(f"Failed to read file: {str(e)}") from e

    async def download_file(
        self,
        url: str,
        save_path: str,
    ) -> int:
        """Download a file from Redmine and save it to the specified path.

        Args:
            url: The URL to download from (typically content_url from attachment)
            save_path: Absolute path where the file should be saved

        Returns:
            The size of the downloaded file in bytes

        Raises:
            RedmineError: If download fails or file cannot be saved
        """
        save_path_obj = Path(save_path)

        # Ensure parent directory exists
        parent_dir = save_path_obj.parent
        if not parent_dir.exists():
            try:
                parent_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise RedmineError(
                    f"Failed to create directory {parent_dir}: {str(e)}"
                ) from e

        try:
            # Make request with authentication header
            response = await self._http_client.get(
                url=url,
                headers={
                    "X-Redmine-API-Key": self.config.api_key,
                },
                follow_redirects=True,
            )

            # Handle HTTP errors
            if response.status_code >= 400:
                error_msg = f"HTTP {response.status_code}: Download failed"
                if response.status_code == 401:
                    error_msg = "Authentication failed. Please check your API key."
                elif response.status_code == 403:
                    error_msg = "Access forbidden. Please check your permissions."
                elif response.status_code == 404:
                    error_msg = "File not found on server."
                elif response.status_code >= 500:
                    error_msg = f"Redmine server error: {response.status_code}"

                raise RedmineError(error_msg, response.status_code)

            # Save file content
            with open(save_path_obj, "wb") as f:
                f.write(response.content)

            return len(response.content)

        except httpx.TimeoutException as e:
            raise RedmineError(f"Download timeout after {self.timeout} seconds") from e
        except httpx.ConnectError as e:
            raise RedmineError(f"Failed to connect for download") from e
        except httpx.HTTPError as e:
            raise RedmineError(f"HTTP error during download: {str(e)}") from e
        except OSError as e:
            raise RedmineError(f"Failed to save file: {str(e)}") from e

    async def aclose(self) -> None:
        """Close the HTTP client and release resources.

        This method should be called when the client is no longer needed
        to ensure proper cleanup of HTTP connections and resources.
        """
        await self._http_client.aclose()

    async def __aenter__(self) -> "RedmineClient":
        """Enter the async context manager.

        Returns:
            The RedmineClient instance
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager and close the HTTP client.

        Args:
            exc_type: Exception type if an error occurred
            exc_val: Exception value if an error occurred
            exc_tb: Exception traceback if an error occurred
        """
        await self.aclose()
