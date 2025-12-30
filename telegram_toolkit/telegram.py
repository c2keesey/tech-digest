#!/usr/bin/env python3
import os
import requests
from pathlib import Path
from typing import Optional


class TelegramNotifier:
    """Simple Telegram notification system for UV Python projects."""

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None,
                 env_file: Optional[str] = None):
        """
        Initialize Telegram notifier.

        Args:
            bot_token: Telegram bot token (defaults to TELEGRAM_BOT_TOKEN env var)
            chat_id: Telegram chat ID (defaults to TELEGRAM_CHAT_ID env var)
            env_file: Path to .env file (defaults to .env in current directory)
        """
        # Load environment variables from .env file if provided
        if env_file or Path('.env').exists():
            self._load_env_file(env_file or '.env')

        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')

        if not self.bot_token or not self.chat_id:
            raise ValueError(
                "Telegram credentials not found. Provide bot_token and chat_id parameters "
                "or set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables."
            )

    def _load_env_file(self, env_file: str) -> None:
        """Load environment variables from .env file."""
        env_path = Path(env_file)
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if line.strip() and not line.startswith('#'):
                        key, value = line.strip().split('=', 1)
                        os.environ[key] = value.strip('\'"')

    def send(self, title: str, message: str, url: Optional[str] = None,
             silent: bool = False) -> bool:
        """
        Send notification via Telegram.

        Args:
            title: Message title (will be bold)
            message: Message body
            url: Optional URL to include as link
            silent: Send silently without notification sound

        Returns:
            True if successful, False otherwise
        """
        # Format message with Telegram markdown
        telegram_message = f"*{title}*\n\n{message}"

        if url:
            telegram_message += f"\n\n[View Details]({url})"

        try:
            api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': telegram_message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': False,
                'disable_notification': silent
            }

            response = requests.post(api_url, json=payload, timeout=10)
            response.raise_for_status()
            print("Telegram notification sent")
            return True

        except requests.RequestException as e:
            print(f"Telegram notification failed: {e}")
            return False

    def send_error(self, title: str, error_message: str) -> bool:
        """
        Send error notification with error emoji.

        Args:
            title: Error title
            error_message: Error details

        Returns:
            True if successful, False otherwise
        """
        return self.send(f"Error: {title}", error_message)

    def send_success(self, title: str, message: str, url: Optional[str] = None) -> bool:
        """
        Send success notification with success emoji.

        Args:
            title: Success title
            message: Success details
            url: Optional URL

        Returns:
            True if successful, False otherwise
        """
        return self.send(f"Success: {title}", message, url)

    def test_connection(self) -> bool:
        """Test Telegram connection by sending a test message."""
        return self.send("Test Notification", "Telegram connection is working!")


def setup_telegram_bot():
    """Interactive setup for Telegram bot credentials."""
    print("Telegram Bot Setup")
    print("===================")
    print()
    print("1. Create a bot by messaging @BotFather on Telegram")
    print("2. Get your chat ID by messaging @userinfobot on Telegram")
    print()

    bot_token = input("Enter your bot token: ").strip()
    chat_id = input("Enter your chat ID: ").strip()

    # Test the connection
    try:
        notifier = TelegramNotifier(bot_token, chat_id)
        if notifier.test_connection():
            # Save to .env file
            env_content = f"TELEGRAM_BOT_TOKEN={bot_token}\nTELEGRAM_CHAT_ID={chat_id}\n"
            with open('.env', 'w') as f:
                f.write(env_content)
            print("Telegram setup complete! Credentials saved to .env")
            return True
        else:
            print("Connection test failed")
            return False
    except Exception as e:
        print(f"Setup failed: {e}")
        return False


if __name__ == "__main__":
    # Interactive setup when run directly
    setup_telegram_bot()
