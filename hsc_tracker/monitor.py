from __future__ import annotations

import logging
import random
import time

from selenium.common.exceptions import WebDriverException

from hsc_tracker.browser import HSCPortalClient, create_webdriver
from hsc_tracker.config import AppConfig
from hsc_tracker.exceptions import RateLimitedError, SessionExpiredError
from hsc_tracker.notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class HSCTrackerService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.notifier = TelegramNotifier(config.telegram_token, config.chat_id)
        self._healthcheck_sent = False

    def run_forever(self) -> None:
        last_notified_count = -1

        while True:
            driver = None
            try:
                if not self._healthcheck_sent:
                    ok = self.notifier.send_message("HSC tracker health check: bot started and Telegram is reachable.")
                    if ok:
                        logger.info("Telegram health check passed")
                    else:
                        logger.warning("Telegram health check failed; monitoring will continue")
                    self._healthcheck_sent = True

                logger.info("Starting a new authenticated browser session")
                driver = create_webdriver(config=self.config)
                portal = HSCPortalClient(driver=driver, config=self.config)
                session_started = time.monotonic()

                portal.login_with_digital_signature()
                portal.prepare_queue_filters()

                while True:
                    session_age = time.monotonic() - session_started
                    if session_age >= self.config.session_restart_seconds:
                        logger.info(
                            "Session reached %.0f seconds, rotating browser session",
                            session_age,
                        )
                        break

                    count = portal.fetch_allow_online_count()

                    if count > 0:
                        if count != last_notified_count:
                            message = f"🚨 З'явилися талони на Данила Апостола! Доступно: {count}"
                            self.notifier.send_message(message)
                            last_notified_count = count
                        else:
                            logger.info("Slots are still available (%s), duplicate notification suppressed", count)
                    else:
                        last_notified_count = -1
                        logger.info("No available slots right now")

                    sleep_for = self.config.poll_interval_seconds + random.uniform(0, self.config.poll_jitter_seconds)
                    logger.info("Sleeping %.1f seconds before next API check", sleep_for)
                    time.sleep(sleep_for)

            except SessionExpiredError:
                logger.warning("Session expired or unauthorized payload received; re-authenticating")
            except RateLimitedError:
                cooldown = self.config.rate_limit_cooldown_seconds
                logger.warning("Rate limit detected; sleeping for %s seconds before retry", cooldown)
                time.sleep(cooldown)
            except KeyboardInterrupt:
                logger.info("Interrupted by user; stopping tracker")
                return
            except WebDriverException:
                logger.exception("WebDriver error occurred; restarting browser session")
            except Exception:
                logger.exception("Unexpected error in monitoring loop; restarting")
            finally:
                if driver is not None:
                    try:
                        driver.quit()
                    except Exception:
                        logger.exception("Failed to quit driver cleanly")

            time.sleep(5)
