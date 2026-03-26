"""Tests for text_utils.apply_patches()."""

import pytest

from mcp_redmine.text_utils import apply_patches


# --- Normal cases ---


class TestApplyPatchesNormal:
    def test_single_patch(self):
        content = "Hello world"
        patches = [{"old_text": "world", "new_text": "Python"}]
        assert apply_patches(content, patches) == "Hello Python"

    def test_multiple_patches_sequential(self):
        content = "Hello world, goodbye world"
        patches = [
            {"old_text": "Hello world", "new_text": "Hi earth"},
            {"old_text": "goodbye world", "new_text": "farewell earth"},
        ]
        assert apply_patches(content, patches) == "Hi earth, farewell earth"

    def test_second_patch_depends_on_first(self):
        content = "aaa bbb"
        patches = [
            {"old_text": "aaa", "new_text": "ccc"},
            {"old_text": "ccc bbb", "new_text": "done"},
        ]
        assert apply_patches(content, patches) == "done"

    def test_delete_text(self):
        content = "Hello [REMOVE THIS] world"
        patches = [{"old_text": "[REMOVE THIS] ", "new_text": ""}]
        assert apply_patches(content, patches) == "Hello world"

    def test_multiline_patch(self):
        content = "line1\nline2\nline3\nline4"
        patches = [{"old_text": "line2\nline3", "new_text": "new2\nnew3\nnew3.5"}]
        assert apply_patches(content, patches) == "line1\nnew2\nnew3\nnew3.5\nline4"

    def test_replace_all_true(self):
        content = "foo bar foo baz foo"
        patches = [{"old_text": "foo", "new_text": "qux", "replace_all": True}]
        assert apply_patches(content, patches) == "qux bar qux baz qux"

    def test_replace_all_false_single_match(self):
        content = "Hello world"
        patches = [{"old_text": "world", "new_text": "earth", "replace_all": False}]
        assert apply_patches(content, patches) == "Hello earth"

    def test_unicode_content(self):
        content = "日本語のテスト文字列です"
        patches = [{"old_text": "テスト", "new_text": "サンプル"}]
        assert apply_patches(content, patches) == "日本語のサンプル文字列です"

    def test_emoji_content(self):
        content = "Status: 🔴 Failed"
        patches = [{"old_text": "🔴 Failed", "new_text": "🟢 Passed"}]
        assert apply_patches(content, patches) == "Status: 🟢 Passed"

    def test_crlf_normalization(self):
        content = "line1\r\nline2\r\nline3"
        patches = [{"old_text": "line1\nline2", "new_text": "new1\nnew2"}]
        assert apply_patches(content, patches) == "new1\nnew2\nline3"

    def test_crlf_in_old_text(self):
        content = "line1\nline2\nline3"
        patches = [{"old_text": "line1\r\nline2", "new_text": "new1\nnew2"}]
        assert apply_patches(content, patches) == "new1\nnew2\nline3"

    def test_old_text_at_beginning(self):
        content = "Hello world"
        patches = [{"old_text": "Hello", "new_text": "Hi"}]
        assert apply_patches(content, patches) == "Hi world"

    def test_old_text_at_end(self):
        content = "Hello world"
        patches = [{"old_text": "world", "new_text": "earth"}]
        assert apply_patches(content, patches) == "Hello earth"

    def test_noop_same_old_and_new(self):
        content = "Hello world"
        patches = [{"old_text": "world", "new_text": "world"}]
        assert apply_patches(content, patches) == "Hello world"


# --- Error cases ---


class TestApplyPatchesErrors:
    def test_empty_patches_list(self):
        with pytest.raises(ValueError, match="At least one patch is required"):
            apply_patches("content", [])

    def test_patch_not_dict(self):
        with pytest.raises(ValueError, match="Patch 1: must be a dictionary"):
            apply_patches("content", ["not a dict"])

    def test_missing_old_text_key(self):
        with pytest.raises(ValueError, match="must contain both"):
            apply_patches("content", [{"new_text": "bar"}])

    def test_missing_new_text_key(self):
        with pytest.raises(ValueError, match="must contain both"):
            apply_patches("content", [{"old_text": "foo"}])

    def test_empty_old_text(self):
        with pytest.raises(ValueError, match="must not be empty"):
            apply_patches("content", [{"old_text": "", "new_text": "bar"}])

    def test_unknown_keys(self):
        with pytest.raises(ValueError, match="unknown keys"):
            apply_patches(
                "content",
                [{"old_text": "foo", "new_text": "bar", "typo_key": "baz"}],
            )

    def test_old_text_not_found(self):
        with pytest.raises(ValueError, match="not found in current content"):
            apply_patches("Hello world", [{"old_text": "xyz", "new_text": "abc"}])

    def test_not_found_error_includes_preview(self):
        with pytest.raises(ValueError, match="Content preview:"):
            apply_patches("Hello world", [{"old_text": "xyz", "new_text": "abc"}])

    def test_not_found_error_includes_searched_text(self):
        with pytest.raises(ValueError, match="Searched for:"):
            apply_patches("Hello world", [{"old_text": "xyz", "new_text": "abc"}])

    def test_multiple_matches_without_replace_all(self):
        with pytest.raises(ValueError, match="found 3 times"):
            apply_patches(
                "foo foo foo",
                [{"old_text": "foo", "new_text": "bar"}],
            )

    def test_multiple_matches_error_suggests_replace_all(self):
        with pytest.raises(ValueError, match="replace_all"):
            apply_patches(
                "foo foo",
                [{"old_text": "foo", "new_text": "bar"}],
            )

    def test_second_patch_fails(self):
        with pytest.raises(ValueError, match="Patch 2"):
            apply_patches(
                "Hello world",
                [
                    {"old_text": "Hello", "new_text": "Hi"},
                    {"old_text": "nonexistent", "new_text": "fail"},
                ],
            )

    def test_non_string_old_text(self):
        with pytest.raises(ValueError, match="must be strings"):
            apply_patches("content", [{"old_text": 123, "new_text": "bar"}])

    def test_non_string_new_text(self):
        with pytest.raises(ValueError, match="must be strings"):
            apply_patches("content", [{"old_text": "foo", "new_text": 123}])

    def test_long_content_preview_truncated(self):
        long_content = "x" * 500
        try:
            apply_patches(long_content, [{"old_text": "yyy", "new_text": "zzz"}])
        except ValueError as e:
            # Preview should be truncated to ~200 chars + "..."
            msg = str(e)
            assert "..." in msg
            assert len(msg) < 600
