from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    telegram_token: str
    chat_id: str
    key_password: str
    key_path: Path
    key_provider: str = "КНЕДП monobank | Universalbank"
    user_agent: str = ""
    action_delay_min_seconds: float = 0.6
    action_delay_max_seconds: float = 1.4
    poll_interval_seconds: int = 60
    poll_jitter_seconds: int = 20
    rate_limit_cooldown_seconds: int = 3600
    session_restart_seconds: int = 600
    service_id: int = 49
    target_department_id: int = 65
    headless: bool = False


def load_config() -> AppConfig:
    load_dotenv()

    telegram_token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("CHAT_ID", "").strip()
    key_password = os.getenv("KEY_PASSWORD", "").strip()
    key_path_raw = os.getenv("KEY_PATH", "").strip()
    key_provider = os.getenv("KEY_PROVIDER", "КНЕДП monobank | Universalbank").strip()
    user_agent = os.getenv("USER_AGENT", "").strip()

    if not telegram_token:
        raise ValueError("TELEGRAM_TOKEN is required")
    if not chat_id:
        raise ValueError("CHAT_ID is required")
    if not key_password:
        raise ValueError("KEY_PASSWORD is required")
    if not key_path_raw:
        raise ValueError("KEY_PATH is required")

    key_path = Path(key_path_raw).expanduser().resolve()
    if not key_path.exists() or not key_path.is_file():
        raise ValueError(f"KEY_PATH does not point to a valid file: {key_path}")

    poll_interval_seconds = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    poll_jitter_seconds = int(os.getenv("POLL_JITTER_SECONDS", "20"))
    rate_limit_cooldown_seconds = int(os.getenv("RATE_LIMIT_COOLDOWN_SECONDS", "3600"))
    session_restart_seconds = int(os.getenv("SESSION_RESTART_SECONDS", "600"))
    service_id = int(os.getenv("SERVICE_ID", "49"))
    target_department_id = int(os.getenv("TARGET_DEPARTMENT_ID", "65"))
    action_delay_min_seconds = float(os.getenv("ACTION_DELAY_MIN_SECONDS", "0.6"))
    action_delay_max_seconds = float(os.getenv("ACTION_DELAY_MAX_SECONDS", "1.4"))
    headless = os.getenv("HEADLESS", "false").strip().lower() in {"1", "true", "yes"}

    if action_delay_min_seconds < 0 or action_delay_max_seconds < 0:
        raise ValueError("ACTION_DELAY_* values must be >= 0")
    if action_delay_max_seconds < action_delay_min_seconds:
        raise ValueError("ACTION_DELAY_MAX_SECONDS must be >= ACTION_DELAY_MIN_SECONDS")
    if poll_jitter_seconds < 0:
        raise ValueError("POLL_JITTER_SECONDS must be >= 0")
    if rate_limit_cooldown_seconds <= 0:
        raise ValueError("RATE_LIMIT_COOLDOWN_SECONDS must be > 0")
    if session_restart_seconds <= 0:
        raise ValueError("SESSION_RESTART_SECONDS must be > 0")

    return AppConfig(
        telegram_token=telegram_token,
        chat_id=chat_id,
        key_password=key_password,
        key_path=key_path,
        key_provider=key_provider,
        user_agent=user_agent,
        action_delay_min_seconds=action_delay_min_seconds,
        action_delay_max_seconds=action_delay_max_seconds,
        poll_interval_seconds=poll_interval_seconds,
        poll_jitter_seconds=poll_jitter_seconds,
        rate_limit_cooldown_seconds=rate_limit_cooldown_seconds,
        session_restart_seconds=session_restart_seconds,
        service_id=service_id,
        target_department_id=target_department_id,
        headless=headless,
    )
