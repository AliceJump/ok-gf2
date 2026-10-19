import json
import subprocess
import unittest
from unittest.mock import patch

from scripts.release.github_changelog import changelog


class GithubChangelogTest(unittest.TestCase):
    @patch("scripts.release.github_changelog.run")
    def test_linked_author_uses_login_not_display_name(self, run):
        run.side_effect = [
            "end\n",
            "start\n",
            "abc\0fix: 修复\n",
            json.dumps({"author": {"login": "Dewcat"}, "commit": {"author": {"name": "Private Name"}}}),
        ]
        self.assertEqual(changelog("owner/repo", "v1", "v2"), "* fix: 修复 (@Dewcat)")
        self.assertEqual(run.call_args_list[2].args, ("git", "log", "--format=%H%x00%s", "start..end", "--"))

    @patch("scripts.release.github_changelog.run")
    def test_unlinked_author_never_falls_back_to_real_name(self, run):
        run.side_effect = [
            "end",
            "start",
            "abc\0fix: old account",
            json.dumps({"author": None, "commit": {"author": {"name": "Private Name"}}}),
        ]
        self.assertEqual(changelog("owner/repo", "v1", "v2"), "* fix: old account")

    @patch("scripts.release.github_changelog.run")
    def test_initial_release_and_bot_login(self, run):
        run.side_effect = ["end", "abc\0update stats", json.dumps({"author": {"login": "github-actions[bot]"}})]
        self.assertEqual(changelog("owner/repo", "", "v1"), "* update stats (@github-actions[bot])")

    @patch("scripts.release.github_changelog.run")
    def test_api_failure_stops_generation(self, run):
        run.side_effect = ["end", "start", "abc\0fix", subprocess.CalledProcessError(1, "gh")]
        with self.assertRaises(subprocess.CalledProcessError):
            changelog("owner/repo", "v1", "v2")

    @patch("scripts.release.github_changelog.run")
    def test_maintenance_filtered_without_hiding_other_changes(self, run):
        run.side_effect = [
            "end",
            "start",
            "aaa\0chore: ruff format\nbbb\0fix: repair\nccc\0update download stats\nddd\0chore: update dependency",
            json.dumps({"author": {"login": "contributor"}}),
            json.dumps({"author": {"login": "github-actions[bot]"}}),
        ]
        self.assertEqual(
            changelog("owner/repo", "v1", "v2"),
            "* fix: repair (@contributor)\n* chore: update dependency (@github-actions[bot])",
        )
        api_calls = [call.args for call in run.call_args_list if call.args[0] == "gh"]
        self.assertEqual(
            api_calls,
            [("gh", "api", "repos/owner/repo/commits/bbb"), ("gh", "api", "repos/owner/repo/commits/ddd")],
        )

    @patch("scripts.release.github_changelog.run")
    def test_maintenance_only_range(self, run):
        run.side_effect = ["end", "start", "aaa\0chore: ruff format\nbbb\0update download stats"]
        self.assertEqual(changelog("owner/repo", "v1", "v2"), "")
        self.assertEqual(run.call_count, 3)

    @patch("scripts.release.github_changelog.run")
    def test_empty_range(self, run):
        run.side_effect = ["end", "start", ""]
        self.assertEqual(changelog("owner/repo", "v1", "v2"), "")
