"""
XYS Sign Service Manager - Multi-Instance Management

Manages multiple browser instances for load balancing and high availability.
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import deque

import structlog

from xys_service import XYSSignService, InstanceStatus
from exceptions import (
    XYSSignServiceError,
    BrowserNotReadyError,
    InstanceLimitError,
    InstanceNotFoundError,
)
from config import get_config

logger = structlog.get_logger()


class XYSSignManager:
    """
    Manages multiple XYSSignService instances.

    Features:
    - Instance pool management
    - Round-robin load balancing
    - Automatic instance recovery
    - Health monitoring
    """

    # Default configuration
    DEFAULT_MAX_INSTANCES = 5
    DEFAULT_MIN_INSTANCES = 2

    def __init__(
        self,
        max_instances: int = DEFAULT_MAX_INSTANCES,
        min_instances: int = DEFAULT_MIN_INSTANCES,
        headless: bool = True,
        default_proxy: Optional[Dict[str, str]] = None,
        browser_executable: Optional[str] = None,
    ):
        """
        Initialize XYS sign service manager.

        Args:
            max_instances: Maximum number of browser instances
            min_instances: Minimum number of instances to maintain
            headless: Run browsers in headless mode
            default_proxy: Default proxy configuration
            browser_executable: Path to browser executable
        """
        self.max_instances = max_instances
        self.min_instances = min_instances
        self.headless = headless
        self.default_proxy = default_proxy
        self.browser_executable = browser_executable

        self._instances: Dict[str, XYSSignService] = {}
        self._instance_queue: deque = deque()
        self._lock = asyncio.Lock()
        self._started = False

        logger.info(
            "xys_manager_initialized",
            max_instances=max_instances,
            min_instances=min_instances,
            headless=headless,
        )

    async def start(self, cookies: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Start the manager and create minimum instances.

        Args:
            cookies: Cookies to inject into all instances
        """
        async with self._lock:
            if self._started:
                return

            logger.info("xys_manager_starting")

            # Create minimum number of instances
            for i in range(self.min_instances):
                try:
                    instance = await self._create_instance(cookies)
                    logger.info(
                        "initial_instance_created",
                        instance_id=instance.instance_id,
                        index=i + 1,
                    )
                except Exception as e:
                    logger.error(
                        "initial_instance_failed",
                        index=i + 1,
                        error=str(e),
                    )

            self._started = True

            logger.info(
                "xys_manager_started",
                instance_count=len(self._instances),
            )

    async def stop(self) -> None:
        """Stop all instances and cleanup."""
        async with self._lock:
            logger.info("xys_manager_stopping")

            # Stop all instances concurrently
            stop_tasks = [
                instance.stop()
                for instance in self._instances.values()
            ]
            await asyncio.gather(*stop_tasks, return_exceptions=True)

            self._instances.clear()
            self._instance_queue.clear()
            self._started = False

            logger.info("xys_manager_stopped")

    async def generate_xys_signature(
        self,
        url: str,
        data: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate XYS signature using an available instance.

        Args:
            url: API URL path
            data: Request body data

        Returns:
            Signature result dict

        Raises:
            XYSSignServiceError: No available instances or generation failed
        """
        instance = await self._get_available_instance()

        if not instance:
            raise BrowserNotReadyError("", "No available instances")

        return await instance.sign(url, data)

    async def create_instance(
        self,
        cookies: Optional[List[Dict[str, Any]]] = None,
        proxy: Optional[Dict[str, str]] = None,
        headless: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Create a new browser instance.

        Args:
            cookies: Cookies to inject
            proxy: Proxy configuration (overrides default)
            headless: Headless mode (overrides default)

        Returns:
            Instance info

        Raises:
            InstanceLimitError: Maximum instances reached
        """
        async with self._lock:
            if len(self._instances) >= self.max_instances:
                raise InstanceLimitError(self.max_instances)

            instance = XYSSignService(
                headless=headless if headless is not None else self.headless,
                proxy=proxy or self.default_proxy,
                browser_executable=self.browser_executable,
            )

            await instance.start(cookies)

            self._instances[instance.instance_id] = instance
            self._instance_queue.append(instance.instance_id)

            logger.info(
                "instance_created",
                instance_id=instance.instance_id,
                total_instances=len(self._instances),
            )

            return instance.get_stats()

    async def stop_instance(self, instance_id: str) -> None:
        """
        Stop and remove a specific instance.

        Args:
            instance_id: Instance ID to stop

        Raises:
            InstanceNotFoundError: Instance not found
        """
        async with self._lock:
            if instance_id not in self._instances:
                raise InstanceNotFoundError(instance_id)

            # Don't allow stopping below minimum
            if len(self._instances) <= self.min_instances:
                raise XYSSignServiceError(
                    f"Cannot stop instance: minimum instances ({self.min_instances}) required",
                    "MIN_INSTANCES_ERROR"
                )

            instance = self._instances.pop(instance_id)
            await instance.stop()

            # Remove from queue
            if instance_id in self._instance_queue:
                self._instance_queue.remove(instance_id)

            logger.info(
                "instance_stopped",
                instance_id=instance_id,
                remaining_instances=len(self._instances),
            )

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on all instances.

        Returns:
            Health status for manager and all instances
        """
        instance_health = {}
        healthy_count = 0

        for instance_id, instance in self._instances.items():
            try:
                health = await instance.health_check()
                instance_health[instance_id] = health
                if health.get("healthy"):
                    healthy_count += 1
            except Exception as e:
                instance_health[instance_id] = {
                    "instance_id": instance_id,
                    "healthy": False,
                    "error": str(e),
                }

        return {
            "manager_status": "running" if self._started else "stopped",
            "total_instances": len(self._instances),
            "healthy_instances": healthy_count,
            "max_instances": self.max_instances,
            "min_instances": self.min_instances,
            "instances": instance_health,
        }

    def get_instances(self) -> List[Dict[str, Any]]:
        """Get stats for all instances."""
        return [
            instance.get_stats()
            for instance in self._instances.values()
        ]

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get stats for a specific instance."""
        instance = self._instances.get(instance_id)
        return instance.get_stats() if instance else None

    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics."""
        total_requests = sum(i.request_count for i in self._instances.values())
        total_errors = sum(i.error_count for i in self._instances.values())

        return {
            "status": "running" if self._started else "stopped",
            "total_instances": len(self._instances),
            "max_instances": self.max_instances,
            "min_instances": self.min_instances,
            "headless": self.headless,
            "has_default_proxy": bool(self.default_proxy),
            "total_requests": total_requests,
            "total_errors": total_errors,
            "overall_success_rate": (
                round((total_requests - total_errors) / total_requests * 100, 2)
                if total_requests > 0 else 100.0
            ),
        }

    async def get_cookies(self) -> Dict[str, str]:
        """
        Get cookies from an available browser instance.
        
        Returns:
            Dict of cookie name -> value (a1, webId, web_session, etc.)
        """
        instance = await self._get_available_instance()
        
        if not instance:
            return {}
        
        return await instance.get_cookies()

    async def _create_instance(
        self,
        cookies: Optional[List[Dict[str, Any]]] = None,
    ) -> XYSSignService:
        """Create and start a new instance (internal)."""
        instance = XYSSignService(
            headless=self.headless,
            proxy=self.default_proxy,
            browser_executable=self.browser_executable,
        )

        await instance.start(cookies)

        self._instances[instance.instance_id] = instance
        self._instance_queue.append(instance.instance_id)

        return instance

    async def _get_available_instance(self) -> Optional[XYSSignService]:
        """Get an available instance using round-robin."""
        async with self._lock:
            if not self._instance_queue:
                return None

            # Round-robin selection
            for _ in range(len(self._instance_queue)):
                instance_id = self._instance_queue.popleft()
                self._instance_queue.append(instance_id)

                instance = self._instances.get(instance_id)
                if instance and instance.status == InstanceStatus.READY:
                    return instance

            return None


# Global manager instance (singleton)
_manager: Optional[XYSSignManager] = None


def get_xys_manager() -> XYSSignManager:
    """Get the global XYS sign service manager."""
    global _manager
    if _manager is None:
        config = get_config()
        _manager = XYSSignManager(
            max_instances=config.max_instances,
            min_instances=config.min_instances,
            headless=config.headless,
            default_proxy=config.proxy_config,
            browser_executable=config.default_browser_executable,
        )
    return _manager


async def init_xys_manager(
    max_instances: int = 5,
    min_instances: int = 2,
    headless: bool = True,
    cookies: Optional[List[Dict[str, Any]]] = None,
    browser_executable: Optional[str] = None,
) -> XYSSignManager:
    """Initialize and start the global XYS sign service manager."""
    global _manager
    _manager = XYSSignManager(
        max_instances=max_instances,
        min_instances=min_instances,
        headless=headless,
        browser_executable=browser_executable,
    )
    await _manager.start(cookies)
    return _manager


async def shutdown_xys_manager() -> None:
    """Shutdown the global XYS sign service manager."""
    global _manager
    if _manager:
        await _manager.stop()
        _manager = None
