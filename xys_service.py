"""
XYS Sign Service - Core Signing Logic

Provides XYS_ format signature generation for XHS Creator platform APIs.
Uses browser automation to call window.mnsv2() function.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

import structlog

logger = structlog.get_logger()

# 延迟导入 - 优先使用原生 playwright（与现有工作代码保持一致）
BROWSER_AVAILABLE = False
BROWSER_TYPE = None

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    BROWSER_AVAILABLE = True
    BROWSER_TYPE = "playwright"
except ImportError:
    try:
        from patchright.async_api import async_playwright, Browser, BrowserContext, Page
        BROWSER_AVAILABLE = True
        BROWSER_TYPE = "patchright"
    except ImportError:
        async_playwright = None
        Browser = None
        BrowserContext = None
        Page = None

if BROWSER_TYPE:
    logger.info("browser_library_loaded", type=BROWSER_TYPE)

from xys_scripts import (
    STEALTH_SCRIPT,
    PAGE_CHECK_SCRIPT,
    XYS_INTERCEPTOR_SCRIPT,
    CHECK_INTERCEPTOR_READY_SCRIPT,
    CHECK_MNSV2_SCRIPT,
    GET_XS_COMMON_SCRIPT,
    GENERATE_XYS_SIGNATURE_SCRIPT,
    CLEAR_SIGNATURE_STORE_SCRIPT,
)
from exceptions import (
    XYSSignServiceError,
    BrowserNotReadyError,
    SignatureGenerationError,
    CookieInjectionError,
    PageLoadError,
    XSCommonNotFoundError,
)
from config import get_config

logger = structlog.get_logger()


class InstanceStatus(str, Enum):
    """Browser instance status"""
    STARTING = "starting"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    STOPPED = "stopped"


class XYSSignService:
    """
    Single browser instance for XYS signature generation.

    Features:
    - Patchright-based browser automation
    - XYS_ format signature generation via mnsv2
    - X-S-Common header capture
    - Health check mechanism
    - Smart page reload with error detection
    """

    # XHS Creator URL for initialization
    CREATOR_URL = "https://creator.xiaohongshu.com"

    # Page load timeout
    PAGE_TIMEOUT = 30000  # 30 seconds

    # Sign function check retry settings
    SIGN_CHECK_RETRIES = 5
    SIGN_CHECK_DELAY = 2  # seconds

    def __init__(
        self,
        instance_id: Optional[str] = None,
        headless: bool = True,
        proxy: Optional[Dict[str, str]] = None,
        browser_executable: Optional[str] = None,
    ):
        """
        Initialize XYS sign service instance.

        Args:
            instance_id: Unique identifier for this instance
            headless: Run browser in headless mode
            proxy: Proxy configuration (server, username, password)
            browser_executable: Path to browser executable
        """
        self.instance_id = instance_id or str(uuid.uuid4())[:8]
        self.headless = headless
        self.proxy = proxy
        self.browser_executable = browser_executable

        self.status = InstanceStatus.STOPPED
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._playwright = None

        # X-S-Common cache
        self._xs_common: str = ""

        # Statistics
        self.created_at = datetime.utcnow()
        self.last_used_at: Optional[datetime] = None
        self.request_count = 0
        self.error_count = 0
        self.consecutive_errors = 0

        # Lock for thread safety
        self._lock = asyncio.Lock()

        logger.info(
            "xys_service_initialized",
            instance_id=self.instance_id,
            headless=headless,
            has_proxy=bool(proxy),
        )

    async def start(self, cookies: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Start browser instance.

        Args:
            cookies: Optional cookies to inject
        """
        if not BROWSER_AVAILABLE:
            raise XYSSignServiceError(
                "Browser library not installed. Run: pip install playwright && playwright install chromium"
            )

        async with self._lock:
            if self.status == InstanceStatus.READY:
                return

            self.status = InstanceStatus.STARTING

            try:
                # Launch playwright
                self._playwright = await async_playwright().start()

                # Browser launch options - 使用系统 Chrome（与现有工作代码保持一致）
                launch_options = {
                    "headless": self.headless,
                    "channel": "chrome",  # 使用系统安装的 Chrome
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--disable-web-security",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-background-timer-throttling",
                        "--disable-backgrounding-occluded-windows",
                        "--disable-renderer-backgrounding",
                    ]
                }

                # Add custom executable if provided (覆盖 channel 设置)
                if self.browser_executable:
                    launch_options.pop("channel", None)
                    launch_options["executable_path"] = self.browser_executable

                # Launch browser
                self.browser = await self._playwright.chromium.launch(**launch_options)

                # Context options
                context_options = {
                    "viewport": {"width": 1920, "height": 1080},
                    "user_agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "locale": "zh-CN",
                    "timezone_id": "Asia/Shanghai",
                }

                # Add proxy if configured
                if self.proxy:
                    context_options["proxy"] = self.proxy

                # Create context
                self.context = await self.browser.new_context(**context_options)

                # Add stealth script
                await self.context.add_init_script(STEALTH_SCRIPT)

                # Add XYS interceptor script (captures signatures from real requests)
                await self.context.add_init_script(XYS_INTERCEPTOR_SCRIPT)

                # Inject cookies if provided
                if cookies:
                    await self._inject_cookies(cookies)

                # Create page
                self.page = await self.context.new_page()

                # Navigate to Creator platform
                await self._navigate_to_creator()

                # Wait for mnsv2 to be available
                await self._wait_for_mnsv2()

                # Capture X-S-Common
                await self._capture_xs_common()

                self.status = InstanceStatus.READY

                logger.info(
                    "xys_service_started",
                    instance_id=self.instance_id,
                    has_xs_common=bool(self._xs_common),
                )

            except Exception as e:
                self.status = InstanceStatus.ERROR
                logger.error(
                    "xys_service_start_failed",
                    instance_id=self.instance_id,
                    error=str(e),
                )
                await self.stop()
                raise XYSSignServiceError(f"Failed to start browser: {e}")

    async def stop(self) -> None:
        """Stop browser instance and cleanup resources."""
        async with self._lock:
            self.status = InstanceStatus.STOPPED

            try:
                if self.page:
                    await self.page.close()
                if self.context:
                    await self.context.close()
                if self.browser:
                    await self.browser.close()
                if self._playwright:
                    await self._playwright.stop()
            except Exception as e:
                logger.warning(
                    "xys_service_stop_error",
                    instance_id=self.instance_id,
                    error=str(e),
                )
            finally:
                self.page = None
                self.context = None
                self.browser = None
                self._playwright = None

            logger.info(
                "xys_service_stopped",
                instance_id=self.instance_id,
            )

    async def sign(
        self,
        url: str,
        data: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate XYS signature for API request.

        Args:
            url: API URL path (e.g., "/api/cas/customer/web/verify-code")
            data: Request body data (optional)

        Returns:
            Dict containing success, X-s, X-t, and X-s-common

        Raises:
            BrowserNotReadyError: Browser is not ready
            SignatureGenerationError: Failed to generate signature
        """
        if self.status != InstanceStatus.READY:
            raise BrowserNotReadyError(
                self.instance_id,
                f"Browser status is {self.status.value}"
            )

        async with self._lock:
            self.status = InstanceStatus.BUSY

            try:
                if not self.page:
                    raise BrowserNotReadyError(self.instance_id, "Page is None")

                # Generate signature using interceptor
                result = await self.page.evaluate(
                    GENERATE_XYS_SIGNATURE_SCRIPT,
                    [url, data or ""]
                )

                if not result.get("success"):
                    raise SignatureGenerationError(result.get("error", "Unknown error"))

                # Use cached X-S-Common if not in result
                if not result.get("X-s-common") and self._xs_common:
                    result["X-s-common"] = self._xs_common

                self.request_count += 1
                self.last_used_at = datetime.utcnow()
                self.consecutive_errors = 0
                self.status = InstanceStatus.READY

                logger.debug(
                    "xys_signature_generated",
                    instance_id=self.instance_id,
                    url=url,
                )

                return {
                    "success": True,
                    "X-s": result.get("X-s", ""),
                    "X-t": result.get("X-t", ""),
                    "X-s-common": result.get("X-s-common", ""),
                }

            except Exception as e:
                self.error_count += 1
                self.consecutive_errors += 1
                self.status = InstanceStatus.READY

                logger.error(
                    "xys_signature_generation_failed",
                    instance_id=self.instance_id,
                    url=url,
                    error=str(e),
                )

                # Try to recover if too many consecutive errors
                if self.consecutive_errors >= 3:
                    await self._try_recover()

                raise SignatureGenerationError(str(e))

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on this instance.

        Returns:
            Dict with health status and details
        """
        result = {
            "instance_id": self.instance_id,
            "status": self.status.value,
            "healthy": False,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "consecutive_errors": self.consecutive_errors,
            "has_xs_common": bool(self._xs_common),
        }

        if self.status != InstanceStatus.READY:
            result["error"] = f"Instance status is {self.status.value}"
            return result

        try:
            if not self.page:
                result["error"] = "Page is None"
                return result

            # Check interceptor availability
            interceptor_ready = await self.page.evaluate(CHECK_INTERCEPTOR_READY_SCRIPT)

            if not interceptor_ready:
                result["error"] = "XYS interceptor not ready"
                return result

            # Check mnsv2 availability
            mnsv2_available = await self.page.evaluate(CHECK_MNSV2_SCRIPT)

            if not mnsv2_available:
                result["error"] = "mnsv2 function not available"
                return result

            # Check page status
            page_status = await self.page.evaluate(PAGE_CHECK_SCRIPT)

            if not page_status.get("success"):
                result["error"] = page_status.get("error", "Unknown page error")
                return result

            result["healthy"] = True
            result["mnsv2_available"] = mnsv2_available

        except Exception as e:
            result["error"] = str(e)

        return result

    async def _navigate_to_creator(self) -> None:
        """Navigate to XHS Creator platform and wait for load."""
        if not self.page:
            raise PageLoadError("Page is None")

        try:
            # First visit the login page to get security cookies
            login_url = f"{self.CREATOR_URL}/login"
            await self.page.goto(
                login_url,
                wait_until="domcontentloaded",  # 不要用 networkidle，容易超时
                timeout=self.PAGE_TIMEOUT,
            )

            # Wait for page to stabilize and JS to execute (security cookies need time)
            await asyncio.sleep(5)

            # Check for errors
            page_status = await self.page.evaluate(PAGE_CHECK_SCRIPT)

            if not page_status.get("success"):
                logger.warning(
                    "page_status_warning",
                    instance_id=self.instance_id,
                    status=page_status,
                )
            
            # Log cookies obtained
            cookies = await self.context.cookies() if self.context else []
            cookie_names = [c["name"] for c in cookies]
            logger.info(
                "cookies_obtained_after_navigation",
                instance_id=self.instance_id,
                cookie_count=len(cookies),
                key_cookies=[n for n in cookie_names if n in ["a1", "webId", "gid", "websectiga", "sec_poison_id"]],
            )

        except Exception as e:
            raise PageLoadError(f"Failed to navigate to Creator: {e}")

    async def _wait_for_mnsv2(self) -> None:
        """Wait for mnsv2 function to be available."""
        if not self.page:
            raise BrowserNotReadyError(self.instance_id, "Page is None")

        for attempt in range(self.SIGN_CHECK_RETRIES):
            try:
                mnsv2_available = await self.page.evaluate(CHECK_MNSV2_SCRIPT)

                if mnsv2_available:
                    logger.debug(
                        "mnsv2_available",
                        instance_id=self.instance_id,
                        attempt=attempt + 1,
                    )
                    return

                # Also check if interceptor is ready
                interceptor_ready = await self.page.evaluate(CHECK_INTERCEPTOR_READY_SCRIPT)

                if interceptor_ready:
                    logger.debug(
                        "xys_sign_ready",
                        instance_id=self.instance_id,
                        attempt=attempt + 1,
                    )
                    return

                # Wait and retry
                await asyncio.sleep(self.SIGN_CHECK_DELAY)

            except Exception as e:
                logger.warning(
                    "mnsv2_check_error",
                    instance_id=self.instance_id,
                    attempt=attempt + 1,
                    error=str(e),
                )
                await asyncio.sleep(self.SIGN_CHECK_DELAY)

        # Log warning but don't fail - mnsv2 might still work
        logger.warning(
            "mnsv2_not_detected",
            instance_id=self.instance_id,
            message="mnsv2 not detected after retries, continuing anyway",
        )

    async def _capture_xs_common(self) -> None:
        """Capture X-S-Common header by triggering a request."""
        if not self.page:
            return

        try:
            # Get X-S-Common from window variable (captured by interceptor)
            xs_common = await self.page.evaluate(GET_XS_COMMON_SCRIPT)
            if xs_common:
                self._xs_common = xs_common
                logger.info(
                    "xs_common_captured",
                    instance_id=self.instance_id,
                    length=len(self._xs_common),
                )

        except Exception as e:
            logger.warning(
                "xs_common_capture_failed",
                instance_id=self.instance_id,
                error=str(e),
            )

    async def _inject_cookies(self, cookies: List[Dict[str, Any]]) -> None:
        """Inject cookies into browser context."""
        if not self.context:
            raise CookieInjectionError("Context is None")

        try:
            # Format cookies for Playwright
            formatted_cookies = []
            for cookie in cookies:
                formatted_cookie = {
                    "name": cookie.get("name"),
                    "value": cookie.get("value"),
                    "domain": cookie.get("domain", ".xiaohongshu.com"),
                    "path": cookie.get("path", "/"),
                }

                # Add optional fields if present
                if "expires" in cookie:
                    formatted_cookie["expires"] = cookie["expires"]
                if "httpOnly" in cookie:
                    formatted_cookie["httpOnly"] = cookie["httpOnly"]
                if "secure" in cookie:
                    formatted_cookie["secure"] = cookie["secure"]
                if "sameSite" in cookie:
                    formatted_cookie["sameSite"] = cookie["sameSite"]

                formatted_cookies.append(formatted_cookie)

            await self.context.add_cookies(formatted_cookies)

            logger.debug(
                "cookies_injected",
                instance_id=self.instance_id,
                count=len(formatted_cookies),
            )

        except Exception as e:
            raise CookieInjectionError(f"Failed to inject cookies: {e}")

    async def _try_recover(self) -> None:
        """Try to recover from error state by reloading page."""
        logger.info(
            "attempting_recovery",
            instance_id=self.instance_id,
            consecutive_errors=self.consecutive_errors,
        )

        try:
            await self._navigate_to_creator()
            await self._wait_for_mnsv2()
            await self._capture_xs_common()
            self.consecutive_errors = 0

            logger.info(
                "recovery_successful",
                instance_id=self.instance_id,
            )

        except Exception as e:
            logger.error(
                "recovery_failed",
                instance_id=self.instance_id,
                error=str(e),
            )
            self.status = InstanceStatus.ERROR

    def get_stats(self) -> Dict[str, Any]:
        """Get instance statistics."""
        return {
            "instance_id": self.instance_id,
            "status": self.status.value,
            "headless": self.headless,
            "has_proxy": bool(self.proxy),
            "has_xs_common": bool(self._xs_common),
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "consecutive_errors": self.consecutive_errors,
            "success_rate": (
                round((self.request_count - self.error_count) / self.request_count * 100, 2)
                if self.request_count > 0 else 100.0
            ),
        }

    async def get_cookies(self) -> Dict[str, str]:
        """
        Get all cookies from browser context.
        
        Returns:
            Dict of cookie name -> value
        """
        if not self.context:
            return {}
        
        try:
            cookies = await self.context.cookies()
            return {c["name"]: c["value"] for c in cookies}
        except Exception as e:
            logger.warning(
                "get_cookies_failed",
                instance_id=self.instance_id,
                error=str(e),
            )
            return {}
