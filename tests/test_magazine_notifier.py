"""Tests for magazine push notifications (ntfy, telegram, discord, email)."""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from utils.magazine.config import MagazineConfig
from utils.magazine.notifier import (
    DiscordChannel,
    EmailChannel,
    Notifier,
    NtfyChannel,
    TelegramChannel,
)


class FakeConfig:
    """Stand-in for MagazineConfig so channel tests do not read .env."""

    def __init__(self, **kwargs):
        values = {
            "notify_channels": [],
            "ntfy_topic": None,
            "ntfy_server": "https://ntfy.sh",
            "email": None,
            "email_password": None,
            "notify_emails": [],
            "telegram_bot_token": None,
            "telegram_chat_ids": [],
            "discord_webhook_url": None,
        }
        values.update(kwargs)
        self.__dict__.update(values)


class RecordingChannel:
    def __init__(self, error=None):
        self.error = error
        self.sent = []

    def send(self, title, message):
        if self.error:
            raise self.error
        self.sent.append((title, message))


def _urlopen():
    response = MagicMock()
    response.read.return_value = b""
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


class NtfyChannelTests(unittest.TestCase):
    def test_missing_topic_raises(self):
        with self.assertRaises(ValueError) as caught:
            NtfyChannel("")
        self.assertIn("NTFY_TOPIC", str(caught.exception))

    def test_posts_message_with_title(self):
        with patch(
            "utils.magazine.notifier.urllib.request.urlopen", return_value=_urlopen()
        ) as urlopen:
            NtfyChannel("my topic", "https://ntfy.example/").send("Magazine", "hello")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://ntfy.example/my%20topic")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.data, b"hello")
        self.assertEqual(request.get_header("Title"), "Magazine")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 30)

    def test_blank_server_uses_public_ntfy(self):
        channel = NtfyChannel("topic", "")
        self.assertEqual(channel.server, "https://ntfy.sh")


class EmailChannelTests(unittest.TestCase):
    def test_missing_credentials_raise(self):
        with self.assertRaises(ValueError) as caught:
            EmailChannel("", "pw", ["me@example.com"])
        self.assertIn("EMAIL", str(caught.exception))

    def test_missing_recipients_raise(self):
        with self.assertRaises(ValueError) as caught:
            EmailChannel("a@b.c", "pw", [])
        self.assertIn("NOTIFY_EMAILS", str(caught.exception))

    def test_sends_one_message_to_every_recipient(self):
        channel = EmailChannel("a@b.c", "pw", ["me@example.com", "other@example.com"])
        with patch("utils.magazine.notifier.smtplib.SMTP") as smtp_cls:
            channel.send("Magazine", "hello")

        smtp_cls.assert_called_once_with("smtp.gmail.com", 587)
        smtp = smtp_cls.return_value
        smtp.starttls.assert_called_once_with()
        smtp.login.assert_called_once_with("a@b.c", "pw")
        mail = smtp.send_message.call_args.args[0]
        self.assertEqual(mail["From"], "a@b.c")
        self.assertEqual(mail["To"], "me@example.com, other@example.com")
        self.assertEqual(mail["Subject"], "Magazine")
        self.assertEqual(mail.get_content().strip(), "hello")
        smtp.quit.assert_called_once_with()

    def test_closes_smtp_when_send_fails(self):
        channel = EmailChannel("a@b.c", "pw", ["me@example.com"])
        with patch("utils.magazine.notifier.smtplib.SMTP") as smtp_cls:
            smtp_cls.return_value.send_message.side_effect = OSError("refused")
            with self.assertRaises(OSError):
                channel.send("Magazine", "hello")
        smtp_cls.return_value.quit.assert_called_once_with()


class TelegramChannelTests(unittest.TestCase):
    def test_missing_token_raises(self):
        with self.assertRaises(ValueError) as caught:
            TelegramChannel("", ["1"])
        self.assertIn("TELEGRAM_BOT_TOKEN", str(caught.exception))

    def test_missing_chat_ids_raise(self):
        with self.assertRaises(ValueError) as caught:
            TelegramChannel("tok", [])
        self.assertIn("TELEGRAM_CHAT_IDS", str(caught.exception))

    def test_posts_once_per_chat(self):
        channel = TelegramChannel("tok", ["11", "22"])
        with patch(
            "utils.magazine.notifier.urllib.request.urlopen", return_value=_urlopen()
        ) as urlopen:
            channel.send("Magazine", "hello")

        self.assertEqual(urlopen.call_count, 2)
        payloads = []
        for call in urlopen.call_args_list:
            request = call.args[0]
            self.assertEqual(
                request.full_url, "https://api.telegram.org/bottok/sendMessage"
            )
            self.assertEqual(request.get_header("Content-type"), "application/json")
            payloads.append(json.loads(request.data))
        self.assertEqual(
            payloads,
            [
                {"chat_id": "11", "text": "Magazine\nhello"},
                {"chat_id": "22", "text": "Magazine\nhello"},
            ],
        )


class DiscordChannelTests(unittest.TestCase):
    def test_missing_webhook_raises(self):
        with self.assertRaises(ValueError) as caught:
            DiscordChannel("")
        self.assertIn("DISCORD_WEBHOOK_URL", str(caught.exception))

    def test_posts_webhook_content(self):
        channel = DiscordChannel("https://discord.example/hook")
        with patch(
            "utils.magazine.notifier.urllib.request.urlopen", return_value=_urlopen()
        ) as urlopen:
            channel.send("Magazine", "hello")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://discord.example/hook")
        self.assertEqual(request.get_header("User-agent"), "afrp-magazine-notifier")
        self.assertEqual(json.loads(request.data), {"content": "**Magazine**\nhello"})

    def test_truncates_content_to_discord_limit(self):
        channel = DiscordChannel("https://discord.example/hook")
        with patch(
            "utils.magazine.notifier.urllib.request.urlopen", return_value=_urlopen()
        ) as urlopen:
            channel.send("Magazine", "x" * 3000)

        content = json.loads(urlopen.call_args.args[0].data)["content"]
        self.assertEqual(len(content), 2000)


class NotifierTests(unittest.TestCase):
    def test_builds_only_enabled_channels(self):
        config = FakeConfig(
            notify_channels=["ntfy", "email", "ntfy"],
            ntfy_topic="topic",
            email="a@b.c",
            email_password="pw",
            notify_emails=["me@example.com"],
        )
        notifier = Notifier.from_config(config)
        self.assertEqual([name for name, _ in notifier.channels], ["ntfy", "email"])

    def test_unknown_channel_raises(self):
        with self.assertRaises(ValueError) as caught:
            Notifier.from_config(FakeConfig(notify_channels=["pager"]))
        self.assertIn("pager", str(caught.exception))

    def test_enabled_channel_missing_settings_raises(self):
        with self.assertRaises(ValueError) as caught:
            Notifier.from_config(FakeConfig(notify_channels=["telegram"]))
        self.assertIn("TELEGRAM_BOT_TOKEN", str(caught.exception))

    def test_notify_reaches_later_channels_after_a_failure(self):
        good = RecordingChannel()
        notifier = Notifier(
            [("bad", RecordingChannel(error=RuntimeError("down"))), ("good", good)]
        )
        self.assertFalse(notifier.notify("hello", title="Magazine"))
        self.assertEqual(good.sent, [("Magazine", "hello")])

    def test_notify_returns_true_when_every_channel_succeeds(self):
        first = RecordingChannel()
        second = RecordingChannel()
        notifier = Notifier([("first", first), ("second", second)])
        self.assertTrue(notifier.notify("hello"))
        self.assertEqual(first.sent, [("Magazine", "hello")])
        self.assertEqual(second.sent, [("Magazine", "hello")])

    def test_notify_with_no_channels_returns_false(self):
        self.assertFalse(Notifier([]).notify("hello"))


class MagazineConfigNotificationTests(unittest.TestCase):
    def test_parses_notification_settings(self):
        env = {
            "DROPBOX_CLIENT_ID": "id",
            "DROPBOX_CLIENT_SECRET": "secret",
            "NOTIFY_CHANNELS": " Ntfy, Email ",
            "NTFY_TOPIC": "secret-topic",
            "NTFY_SERVER": "",
            "EMAIL": "a@b.c",
            "EMAIL_APP_PASSWORD": "pw",
            "NOTIFY_EMAILS": " me@example.com , other@example.com ",
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_CHAT_IDS": " 11 , 22 ",
            "DISCORD_WEBHOOK_URL": "",
        }
        with patch("utils.magazine.config.load_dotenv"), patch.dict(
            os.environ, env, clear=True
        ):
            config = MagazineConfig()

        self.assertEqual(config.notify_channels, ["ntfy", "email"])
        self.assertEqual(config.ntfy_topic, "secret-topic")
        self.assertEqual(config.ntfy_server, "https://ntfy.sh")
        self.assertEqual(config.notify_emails, ["me@example.com", "other@example.com"])
        self.assertEqual(config.telegram_chat_ids, ["11", "22"])
        notifier = Notifier.from_config(config)
        self.assertEqual([name for name, _ in notifier.channels], ["ntfy", "email"])


if __name__ == "__main__":
    unittest.main()
