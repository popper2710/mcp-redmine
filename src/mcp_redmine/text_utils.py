"""Text patching utilities for differential updates."""

ALLOWED_PATCH_KEYS = {"old_text", "new_text", "replace_all"}


def normalize_line_endings(text: str) -> str:
    """Normalize CRLF and CR line endings to LF."""
    if "\r" not in text:
        return text
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _truncate(text: str, max_length: int) -> str:
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


def apply_patches(content: str, patches: list[dict]) -> str:
    """Apply a sequence of search-and-replace patches to content.

    Args:
        content: The original text content.
        patches: List of patch dicts with keys:
            - old_text (str): Text to find (required, must not be empty)
            - new_text (str): Replacement text (required, empty string = delete)
            - replace_all (bool): Replace all occurrences (optional, default False)

    Returns:
        The patched content string.

    Raises:
        ValueError: If validation fails or old_text is not found.
    """
    if not patches:
        raise ValueError("At least one patch is required")

    content = normalize_line_endings(content)

    for i, patch in enumerate(patches):
        patch_num = i + 1

        if not isinstance(patch, dict):
            raise ValueError(
                f"Patch {patch_num}: must be a dictionary with 'old_text' and 'new_text' keys"
            )

        unknown_keys = set(patch.keys()) - ALLOWED_PATCH_KEYS
        if unknown_keys:
            raise ValueError(
                f"Patch {patch_num}: unknown keys {unknown_keys}. "
                f"Allowed keys: 'old_text', 'new_text', 'replace_all'"
            )

        if "old_text" not in patch or "new_text" not in patch:
            raise ValueError(
                f"Patch {patch_num}: must contain both 'old_text' and 'new_text' keys"
            )

        old_text = patch["old_text"]
        new_text = patch["new_text"]
        replace_all = patch.get("replace_all", False)

        if not isinstance(old_text, str) or not isinstance(new_text, str):
            raise ValueError(
                f"Patch {patch_num}: 'old_text' and 'new_text' must be strings"
            )

        if not old_text:
            raise ValueError(f"Patch {patch_num}: 'old_text' must not be empty")

        old_text = normalize_line_endings(old_text)
        new_text = normalize_line_endings(new_text)

        count = content.count(old_text)

        if count == 0:
            raise ValueError(
                f"Patch {patch_num}: 'old_text' not found in current content. "
                f"Searched for: {_truncate(old_text, 50)} "
                f"Content preview: {_truncate(content, 200)}"
            )

        if not replace_all and count > 1:
            raise ValueError(
                f"Patch {patch_num}: 'old_text' found {count} times. "
                f"Please provide more surrounding context to make the match unique, "
                f"or set 'replace_all' to true."
            )

        if replace_all:
            content = content.replace(old_text, new_text)
        else:
            content = content.replace(old_text, new_text, 1)

    return content
