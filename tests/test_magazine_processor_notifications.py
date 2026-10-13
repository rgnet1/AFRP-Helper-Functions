"""Tests for magazine processor notification wiring."""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch


def _stub_module(name: str, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod


if "utils.magazine.dropbox_handler" not in sys.modules:
    _stub_module("utils.magazine.dropbox_handler", DropboxHandler=MagicMock)
if "utils.magazine.server_handler" not in sys.modules:
    _stub_module("utils.magazine.server_handler", ServerHandler=MagicMock)
if "utils.magazine.sharepoint" not in sys.modules:
    _stub_module("utils.magazine.sharepoint", upload_file_to_sharepoint=MagicMock)

from tests.test_magazine_notifier import FakeConfig
from utils.magazine.magazine_processor import MagazineProcessor


class MagazineProcessorNotificationTests(unittest.TestCase):
    def _processor(self, config):
        with patch("utils.magazine.magazine_processor.DropboxHandler"):
            return MagazineProcessor(config)

    def test_notify_runs_only_via_helper_and_never_raises_on_bad_config(self):
        config = FakeConfig(notify_channels=["ntfy"], ntfy_topic=None)
        processor = self._processor(config)

        processor._notify_after_run("Magazine Check: No new files to process")

        self.assertIsNotNone(processor._notifier)
        self.assertEqual(processor._notifier.channels, [])

    def test_notify_never_raises_when_notify_raises(self):
        config = FakeConfig(notify_channels=["ntfy"], ntfy_topic="topic")
        processor = self._processor(config)
        failing = MagicMock()
        failing.notify.side_effect = RuntimeError("network down")
        processor._notifier = failing

        processor._notify_after_run("Magazine Check: Files were processed and uploaded")

        failing.notify.assert_called_once_with(
            "Magazine Check: Files were processed and uploaded"
        )

    def test_notify_skips_empty_message(self):
        processor = self._processor(FakeConfig())
        processor._notify_after_run("")
        self.assertIsNone(processor._notifier)


if __name__ == "__main__":
    unittest.main()
