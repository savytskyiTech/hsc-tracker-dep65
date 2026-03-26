from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import NoAlertPresentException, TimeoutException, UnexpectedAlertPresentException
from selenium.webdriver import ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from hsc_tracker.config import AppConfig
from hsc_tracker.exceptions import RateLimitedError, SessionExpiredError

logger = logging.getLogger(__name__)

CABINET_URL = "https://eqn.hsc.gov.ua/cabinet"
QUEUE_URL = "https://eqn.hsc.gov.ua/cabinet/queue"
API_URL_TEMPLATE = "https://eqn.hsc.gov.ua/api/v2/equeue/departments?serviceId={service_id}"

XPATH_AUTHORIZATION_BUTTON = "/html/body/div[2]/main/section/div[2]/button"
XPATH_CONSENT_CHECKBOX = "/html/body/div[2]/main/section/div[2]/label/span/input"
XPATH_FILE_CARRIER = "/html/body/div[1]/div/div[1]/div[2]/div/div[2]/table/tbody/tr[1]/td[2]/a/span"
XPATH_PROVIDER_SELECT = "/html/body/div[1]/div/div[1]/div[2]/div/div[1]/form/div[3]/div/div[2]/select"
XPATH_PASSWORD_INPUT = "/html/body/div[1]/div/div[1]/div[2]/div/div[1]/form/div[5]/div/div[2]/input"
XPATH_CONTINUE_BUTTON = "/html/body/div[1]/div/div[1]/div[2]/div/div[1]/form/div[6]/button"
XPATH_VERIFY_DATA_BUTTON = "/html/body/div[1]/div/div[1]/div[2]/div/div[1]/form/div[2]/div[1]/button"

XPATH_EXAM_TYPE_BUTTON = "/html/body/div[2]/main/section/div/div[3]/div[2]/button"
XPATH_TRANSPORT_BUTTON = "/html/body/div[2]/main/section/div/div[3]/div[1]/button"
XPATH_CATEGORY_BUTTON = "/html/body/div[2]/main/section/div/div[3]/div[3]/button"

AUTH_BUTTON_FALLBACKS: list[tuple[str, str]] = [
    (By.XPATH, XPATH_AUTHORIZATION_BUTTON),
    (By.XPATH, "//button[contains(., 'Авторизац') or contains(., 'Authorization') or contains(., 'Увійти')]") ,
    (By.CSS_SELECTOR, "button[type='button']"),
]

CONSENT_CHECKBOX_FALLBACKS: list[tuple[str, str]] = [
    (By.XPATH, XPATH_CONSENT_CHECKBOX),
    (By.CSS_SELECTOR, "input[type='checkbox']"),
    (By.XPATH, "//label//input[@type='checkbox']"),
]

FILE_CARRIER_FALLBACKS: list[tuple[str, str]] = [
    (By.XPATH, XPATH_FILE_CARRIER),
    (By.XPATH, "//*[contains(., 'Файловий носій')]"),
    (By.XPATH, "//button[contains(., 'Файловий')]"),
    (By.XPATH, "//*[contains(@role, 'tab') and contains(., 'Файловий')]"),
    (By.XPATH, "//*[contains(@class, 'tab') and contains(., 'Файловий')]"),
]

EXAM_TYPE_FALLBACKS: list[tuple[str, str]] = [
    (By.XPATH, XPATH_EXAM_TYPE_BUTTON),
    (By.XPATH, "//button[contains(., 'Практичний іспит')]"),
]

TRANSPORT_FALLBACKS: list[tuple[str, str]] = [
    (By.XPATH, XPATH_TRANSPORT_BUTTON),
    (By.XPATH, "//button[contains(., 'на транспорті')]"),
]

CATEGORY_FALLBACKS: list[tuple[str, str]] = [
    (By.XPATH, XPATH_CATEGORY_BUTTON),
    (By.XPATH, "//button[contains(., 'Категорія B') or contains(., 'B (механіка)')]"),
]

PROVIDER_SELECT_FALLBACKS: list[tuple[str, str]] = [
    (By.XPATH, XPATH_PROVIDER_SELECT),
    (By.CSS_SELECTOR, "select"),
]

FILE_INPUT_FALLBACKS: list[tuple[str, str]] = [
    (By.CSS_SELECTOR, "input[type='file']"),
    (By.CSS_SELECTOR, "input[accept*='pfx']"),
    (By.XPATH, "//input[@type='file']"),
]

PASSWORD_INPUT_FALLBACKS: list[tuple[str, str]] = [
    (By.XPATH, XPATH_PASSWORD_INPUT),
    (By.CSS_SELECTOR, "input[type='password']"),
    (By.XPATH, "//input[contains(@placeholder, 'Пароль') or contains(@aria-label, 'Пароль')]"),
]

CONTINUE_BUTTON_FALLBACKS: list[tuple[str, str]] = [
    (By.XPATH, XPATH_CONTINUE_BUTTON),
    (By.XPATH, "//button[contains(., 'Продовжити') or contains(., 'Увійти') or contains(., 'Continue')]"),
]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def create_webdriver(config: AppConfig) -> WebDriver:
    options = ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1400,1200")
    options.add_argument("--start-maximized")
    user_agent = config.user_agent or DEFAULT_USER_AGENT
    options.add_argument(f"--user-agent={user_agent}")
    if config.headless:
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()),
        options=options,
    )
    driver.set_page_load_timeout(60)
    logger.info("WebDriver started with configured user-agent")
    return driver


class HSCPortalClient:
    def __init__(self, driver: WebDriver, config: AppConfig) -> None:
        self.driver = driver
        self.config = config
        self.wait = WebDriverWait(driver, 30)

    def _human_pause(self) -> None:
        delay = random.uniform(self.config.action_delay_min_seconds, self.config.action_delay_max_seconds)
        time.sleep(delay)

    def login_with_digital_signature(self) -> None:
        logger.info("Opening cabinet page")
        self.driver.get(CABINET_URL)
        self._human_pause()

        self._click_any(CONSENT_CHECKBOX_FALLBACKS, "consent checkbox")
        self._click_any(AUTH_BUTTON_FALLBACKS, "authorization button")

        self._wait_for_idgov_redirect()

        self._ensure_file_carrier_selected()
        self._select_provider(self.config.key_provider)
        self._upload_key_file()
        self._handle_provider_alert_and_retry_upload_if_needed()
        self._fill_password_and_continue()
        self._click_xpath(XPATH_VERIFY_DATA_BUTTON)

        logger.info("Waiting for redirect back to HSC cabinet")
        self._wait_for_url_contains("eqn.hsc.gov.ua/cabinet", timeout_seconds=60)

    def _wait_for_idgov_redirect(self) -> None:
        logger.info("Waiting for id.gov.ua redirect")
        deadline = time.time() + 45
        retried_auth_click = False

        while time.time() < deadline:
            current_url = self._get_current_url_safe()
            if "id.gov.ua" in current_url:
                return

            if not retried_auth_click and "eqn.hsc.gov.ua/cabinet" in current_url:
                logger.info("Still on cabinet page; retrying authorization click")
                self._click_any(AUTH_BUTTON_FALLBACKS, "authorization button retry")
                retried_auth_click = True

            time.sleep(0.5)

        raise RuntimeError("Timed out waiting for redirect to id.gov.ua")

    def _wait_for_url_contains(self, expected: str, timeout_seconds: int) -> None:
        deadline = time.time() + timeout_seconds
        last_exception: Exception | None = None

        while time.time() < deadline:
            try:
                current_url = self.driver.current_url
                if expected in current_url:
                    return
            except WebDriverException as exc:
                last_exception = exc
                logger.debug("Transient WebDriver error while reading current_url", exc_info=True)

            time.sleep(0.4)

        if last_exception is not None:
            raise RuntimeError(f"Timed out waiting for URL containing '{expected}'") from last_exception
        raise RuntimeError(f"Timed out waiting for URL containing '{expected}'")

    def _get_current_url_safe(self) -> str:
        try:
            return self.driver.current_url
        except WebDriverException:
            logger.debug("Transient WebDriver error while reading current_url", exc_info=True)
            return ""

    def _ensure_file_carrier_selected(self) -> None:
        # On the updated id.gov.ua UI the "Файловий" tab may already be active,
        # so clicking can be unnecessary or even fail if the element is non-clickable.
        try:
            if self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
                logger.info("File carrier mode already active")
                return
        except Exception:
            logger.debug("Could not probe file input before selecting carrier", exc_info=True)

        try:
            self._click_any(FILE_CARRIER_FALLBACKS, "file carrier option")
        except RuntimeError:
            # If click fails but file input exists, continue safely.
            if self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
                logger.info("File input is present; continuing without explicit carrier click")
                return
            raise

    def prepare_queue_filters(self) -> None:
        logger.info("Navigating to queue page and selecting filters")
        self.driver.get(QUEUE_URL)
        self._human_pause()
        self._click_any(EXAM_TYPE_FALLBACKS, "practical exam button")
        self._click_any(TRANSPORT_FALLBACKS, "transport service button")
        self._click_any(CATEGORY_FALLBACKS, "category B button")

    def fetch_allow_online_count(self) -> int:
        url = API_URL_TEMPLATE.format(service_id=self.config.service_id)
        self.driver.get(url)
        self._human_pause()

        pre_elements = self.driver.find_elements(By.TAG_NAME, "pre")
        payload_text = pre_elements[0].text.strip() if pre_elements else ""

        self._raise_if_rate_limited(payload_text)

        if not payload_text:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text.strip()
            lower_body = body_text.lower()
            self._raise_if_rate_limited(body_text)
            if (
                "401" in body_text
                or "unauthorized" in lower_body
                or "авториз" in lower_body
                or "login" in lower_body
                or "id.gov.ua" in self.driver.current_url
            ):
                raise SessionExpiredError("Session appears to be unauthorized")
            payload_text = body_text

        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise SessionExpiredError("API payload is not valid JSON") from exc

        departments = self._extract_departments(payload)
        for department in departments:
            dep_id = department.get("id")
            if dep_id == self.config.target_department_id:
                allow_online_count = department.get("allowOnlineCount", 0)
                logger.info(
                    "Department %s allowOnlineCount=%s",
                    self.config.target_department_id,
                    allow_online_count,
                )
                try:
                    return int(allow_online_count)
                except (TypeError, ValueError):
                    return 0

        logger.warning("Target department id=%s not found in API response", self.config.target_department_id)
        return 0

    def _raise_if_rate_limited(self, text: str) -> None:
        if not text:
            return

        lower_text = text.lower()
        rate_limit_markers = (
            "too many requests",
            "429",
            "rate limit",
            "забагато запит",
            "надто багато запит",
        )
        if any(marker in lower_text for marker in rate_limit_markers):
            raise RateLimitedError("Remote service returned rate-limit response")

    def _extract_departments(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            for key in ("data", "items", "departments", "result"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

            if "id" in payload:
                return [payload]

        raise SessionExpiredError("Unexpected JSON schema from API")

    def _select_provider(self, provider_name: str) -> None:
        for by, locator in PROVIDER_SELECT_FALLBACKS:
            try:
                select_element = self.wait.until(EC.presence_of_element_located((by, locator)))
                select = Select(select_element)
                options = [(opt.text.strip(), opt) for opt in select.options]
                option_texts = [text for text, _ in options]

                if provider_name in option_texts:
                    select.select_by_visible_text(provider_name)
                    logger.info("Selected provider: %s", provider_name)
                    return

                target_norm = self._normalize_provider_name(provider_name)
                for text, option in options:
                    if target_norm and target_norm in self._normalize_provider_name(text):
                        option.click()
                        logger.info("Selected provider by partial match: %s", text)
                        return

                for text, option in options:
                    text_norm = self._normalize_provider_name(text)
                    if "monobank" in text_norm or "universalbank" in text_norm:
                        option.click()
                        logger.info("Selected provider by heuristic match: %s", text)
                        return

                current = select.first_selected_option.text.strip() if select.options else "unknown"
                raise RuntimeError(
                    f"Provider '{provider_name}' not found in dropdown. Current provider: '{current}'. "
                    f"Available providers: {option_texts}"
                )
            except Exception:
                logger.debug("Provider select not found with %s=%s", by, locator, exc_info=True)

        raise RuntimeError("Provider select was not found on id.gov.ua page")

    def _normalize_provider_name(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())

    def _upload_key_file(self) -> None:
        path = str(self.config.key_path)
        for by, locator in FILE_INPUT_FALLBACKS:
            elements = self.driver.find_elements(by, locator)
            for file_input in elements:
                try:
                    self.driver.execute_script(
                        "arguments[0].style.display='block';"
                        "arguments[0].style.visibility='visible';"
                        "arguments[0].removeAttribute('hidden');"
                        "arguments[0].removeAttribute('disabled');",
                        file_input,
                    )
                    file_input.send_keys(path)

                    value = file_input.get_attribute("value") or ""
                    if value:
                        logger.info("Digital key file attached successfully")
                    else:
                        logger.info("File input accepted key path")
                    self._human_pause()
                    return
                except Exception:
                    logger.debug("Failed to upload key with %s=%s", by, locator, exc_info=True)

        raise RuntimeError("Could not find a usable file input on id.gov.ua page")

    def _fill_password_and_continue(self) -> None:
        try:
            password_input = self._wait_for_password_input_ready()
            password_input.clear()
            password_input.send_keys(self.config.key_password)
            self._human_pause()
            self._click_any(CONTINUE_BUTTON_FALLBACKS, "continue button")
        except UnexpectedAlertPresentException:
            self._handle_provider_alert_and_retry_upload_if_needed()
            password_input = self._wait_for_password_input_ready()
            password_input.clear()
            password_input.send_keys(self.config.key_password)
            self._human_pause()
            self._click_any(CONTINUE_BUTTON_FALLBACKS, "continue button")

    def _handle_provider_alert_and_retry_upload_if_needed(self) -> None:
        alert_text = self._accept_alert_if_present(timeout_seconds=2)
        if not alert_text:
            return

        lower = alert_text.lower()
        logger.warning("Received browser alert after key upload: %s", alert_text)
        is_provider_mismatch = "сертифікат не знайдено" in lower or "кнедп дпс" in lower
        if not is_provider_mismatch:
            raise RuntimeError(f"Unexpected id.gov.ua alert: {alert_text}")

        logger.info("Retrying with selected provider: %s", self.config.key_provider)
        self._select_provider(self.config.key_provider)
        self._upload_key_file()

        second_alert = self._accept_alert_if_present(timeout_seconds=2)
        if second_alert:
            raise RuntimeError(f"Provider retry failed, alert still shown: {second_alert}")

    def _accept_alert_if_present(self, timeout_seconds: int) -> str | None:
        try:
            alert = WebDriverWait(self.driver, timeout_seconds).until(EC.alert_is_present())
            text = alert.text
            alert.accept()
            return text
        except TimeoutException:
            return None
        except NoAlertPresentException:
            return None

    def _wait_for_password_input_ready(self) -> WebElement:
        deadline = time.time() + 30
        last_element: WebElement | None = None

        while time.time() < deadline:
            for by, locator in PASSWORD_INPUT_FALLBACKS:
                try:
                    elements = self.driver.find_elements(by, locator)
                    for element in elements:
                        last_element = element
                        if element.is_displayed() and element.is_enabled():
                            return element
                except Exception:
                    logger.debug("Password input lookup failed with %s=%s", by, locator, exc_info=True)

            time.sleep(0.25)

        if last_element is not None:
            raise RuntimeError("Password input found but it never became enabled")
        raise RuntimeError("Password input was not found after key upload")

    def _click_any(self, locators: list[tuple[str, str]], label: str) -> None:
        last_error: Exception | None = None
        for by, locator in locators:
            try:
                element = self.wait.until(EC.presence_of_element_located((by, locator)))
                self._safe_click(element)
                self._human_pause()
                return
            except Exception as exc:
                last_error = exc
                logger.debug("Failed click attempt for %s using locator %s=%s", label, by, locator)

        raise RuntimeError(f"Element not clickable: {label}") from last_error

    def _safe_click(self, element: WebElement) -> None:
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        try:
            if element.is_displayed() and element.is_enabled():
                element.click()
                return
        except Exception:
            logger.debug("Regular click failed, trying JavaScript click", exc_info=True)

        self.driver.execute_script("arguments[0].click();", element)

    def _click_xpath(self, xpath: str) -> None:
        try:
            element = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            self._safe_click(element)
        except TimeoutException as exc:
            raise RuntimeError(f"Element not clickable with xpath: {xpath}") from exc
