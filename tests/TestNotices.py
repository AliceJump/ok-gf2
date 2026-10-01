import json
import tempfile
import unittest
from pathlib import Path

from src.notices import NOTICES, Notice, unread_notices
from src.notices.store import load_read_ids, mark_read


class NoticesTest(unittest.TestCase):
    def test_filters_read_and_inactive_notices(self):
        inactive = Notice("old", "旧提醒", "喝水", "无", "https://example.com", active=False)
        self.assertEqual([NOTICES[0]], unread_notices(set(), (NOTICES[0], inactive)))
        self.assertEqual([], unread_notices({NOTICES[0].id}, (NOTICES[0], inactive)))

    def test_missing_and_damaged_state_falls_back_to_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "notice_state.json"
            self.assertEqual(set(), load_read_ids(state))
            state.write_text("{broken", encoding="utf-8")
            self.assertEqual(set(), load_read_ids(state))
            state.write_text('{"read_ids": "wrong type"}', encoding="utf-8")
            self.assertEqual(set(), load_read_ids(state))

    def test_mark_read_persists_and_preserves_existing_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "configs" / "notice_state.json"
            mark_read(NOTICES[0].id, state)
            mark_read("another", state)
            mark_read(NOTICES[0].id, state)
            self.assertEqual({NOTICES[0].id, "another"}, load_read_ids(state))
            self.assertEqual(sorted([NOTICES[0].id, "another"]),
                             json.loads(state.read_text(encoding="utf-8"))["read_ids"])

    def test_mark_read_repairs_damaged_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "notice_state.json"
            state.write_text("broken", encoding="utf-8")
            mark_read(NOTICES[0].id, state)
            self.assertEqual({NOTICES[0].id}, load_read_ids(state))
