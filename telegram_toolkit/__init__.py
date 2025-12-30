"""
Telegram Automation Toolkit

A simple toolkit for Telegram notifications and cron job automation in UV Python projects.
"""

from .telegram import TelegramNotifier
from .cron import CronJob

__version__ = "0.1.0"
__all__ = ["TelegramNotifier", "CronJob"]
