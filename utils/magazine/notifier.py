"""Magazine run notifications via ntfy, Telegram, Discord, or email.

Legacy Verizon vtext / PHONE_NUMBER SMS via Gmail was removed; configure NOTIFY_CHANNELS
in config/.env instead.
"""

import json
import logging
import smtplib
import sys
import urllib.request
from email.message import EmailMessage
from typing import List, Tuple
from urllib.parse import quote


class NtfyChannel:
    """Push a notification to an ntfy topic. No account required."""

    def __init__(self, topic: str, server: str = "https://ntfy.sh"):
        if not topic:
            raise ValueError("NTFY_TOPIC is required when the ntfy channel is enabled")
        self.topic = topic
        self.server = (server or "https://ntfy.sh").rstrip("/")

    def send(self, title: str, message: str) -> None:
        url = f"{self.server}/{quote(self.topic, safe='')}"
        request = urllib.request.Request(
            url,
            data=message.encode("utf-8"),
            headers={"Title": title},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()

    @classmethod
    def from_config(cls, config) -> "NtfyChannel":
        return cls(config.ntfy_topic, config.ntfy_server)


class EmailChannel:
    """Send a notification by email through Gmail SMTP."""

    def __init__(self, email: str, password: str, recipients: List[str]):
        if not email or not password:
            raise ValueError(
                "EMAIL and EMAIL_APP_PASSWORD are required when the email channel is enabled"
            )
        if not recipients:
            raise ValueError("NOTIFY_EMAILS is required when the email channel is enabled")
        self.email = email
        self.password = password
        self.recipients = recipients

    def send(self, title: str, message: str) -> None:
        mail = EmailMessage()
        mail["From"] = self.email
        mail["To"] = ", ".join(self.recipients)
        mail["Subject"] = title
        mail.set_content(message)

        server = smtplib.SMTP("smtp.gmail.com", 587)
        try:
            server.starttls()
            server.login(self.email, self.password)
            server.send_message(mail)
        finally:
            server.quit()

    @classmethod
    def from_config(cls, config) -> "EmailChannel":
        return cls(config.email, config.email_password, config.notify_emails)


class TelegramChannel:
    """Send a notification through a Telegram bot, once per chat id."""

    def __init__(self, token: str, chat_ids: List[str]):
        if not token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is required when the telegram channel is enabled"
            )
        if not chat_ids:
            raise ValueError(
                "TELEGRAM_CHAT_IDS is required when the telegram channel is enabled"
            )
        self.token = token
        self.chat_ids = chat_ids

    def send(self, title: str, message: str) -> None:
        text = f"{title}\n{message}" if title else message
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        for chat_id in self.chat_ids:
            payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
            request = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                response.read()

    @classmethod
    def from_config(cls, config) -> "TelegramChannel":
        return cls(config.telegram_bot_token, config.telegram_chat_ids)


class DiscordChannel:
    """Post a notification to a Discord channel via an incoming webhook."""

    def __init__(self, webhook_url: str):
        if not webhook_url:
            raise ValueError(
                "DISCORD_WEBHOOK_URL is required when the discord channel is enabled"
            )
        self.webhook_url = webhook_url

    def send(self, title: str, message: str) -> None:
        content = f"**{title}**\n{message}" if title else message
        payload = json.dumps({"content": content[:2000]}).encode("utf-8")
        request = urllib.request.Request(
            self.webhook_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "afrp-magazine-notifier",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()

    @classmethod
    def from_config(cls, config) -> "DiscordChannel":
        return cls(config.discord_webhook_url)


# Add a future channel by writing a class with from_config() and registering it here.
CHANNELS = {
    "ntfy": NtfyChannel,
    "email": EmailChannel,
    "telegram": TelegramChannel,
    "discord": DiscordChannel,
}


class Notifier:
    """Sends one message through every enabled notification channel."""

    def __init__(self, channels: List[Tuple[str, object]]):
        self.channels = channels

    @classmethod
    def from_config(cls, config) -> "Notifier":
        """Build only the channels listed in NOTIFY_CHANNELS.

        Raises:
            ValueError: If a listed channel is unknown or missing its settings.
        """
        enabled = []
        seen = set()
        for name in config.notify_channels:
            if name in seen:
                continue
            seen.add(name)
            channel_cls = CHANNELS.get(name)
            if channel_cls is None:
                supported = ", ".join(CHANNELS)
                raise ValueError(
                    f"Unknown notification channel '{name}'. Supported: {supported}"
                )
            enabled.append((name, channel_cls.from_config(config)))

        if not enabled:
            logging.warning("NOTIFY_CHANNELS is empty; no notifications will be sent")

        return cls(enabled)

    def notify(self, message: str, title: str = "Magazine") -> bool:
        """Send to every channel. One failure does not stop the others.

        Returns:
            True if every channel succeeded. False if there are no channels
            or any channel failed.
        """
        if not self.channels:
            logging.warning("No notification channels enabled")
            print("No notification channels enabled")
            return False

        ok = True
        for name, channel in self.channels:
            try:
                channel.send(title, message)
                logging.info(f"Notification sent via {name}")
                print(f"Notification sent via {name}.")
            except Exception as e:
                ok = False
                logging.error(f"Failed to send notification via {name}: {e}")
                print(f"Failed to send notification via {name}: {e}")
        return ok


if __name__ == "__main__":
    from utils.magazine.config import MagazineConfig

    logging.basicConfig(level=logging.INFO)
    text = sys.argv[1] if len(sys.argv) > 1 else "test message"
    notifier = Notifier.from_config(MagazineConfig())
    if not notifier.notify(text):
        sys.exit(1)
