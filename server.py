"""
XYS Sign Service HTTP Server

FastAPI-based HTTP server for XYS signature generation.
"""

import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from typing import Optional, Dict

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from xys_manager import (
    XYSSignManager,
    get_xys_manager,
    init_xys_manager,
    shutdown_xys_manager,
)
from xys_service import InstanceStatus
from config import get_config, init_config
from exceptions import (
    XYSSignServiceError,
    BrowserNotReadyError,
    SignatureGenerationError,
)

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


# Request/Response models
class SignRequest(BaseModel):
    """XYS signature request"""
    url: str = Field(..., description="API URL path to sign")
    data: str = Field(default="", description="Request body data")


class SignResponse(BaseModel):
    """XYS signature response"""
    success: bool
    x_s: str = Field(default="", alias="X-s")
    x_t: str = Field(default="", alias="X-t")
    x_s_common: str = Field(default="", alias="X-s-common")
    error: Optional[str] = None

    class Config:
        populate_by_name = True


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    manager_status: str
    total_instances: int
    healthy_instances: int
    max_instances: int
    min_instances: int


class StatsResponse(BaseModel):
    """Statistics response"""
    status: str
    total_instances: int
    max_instances: int
    min_instances: int
    headless: bool
    has_default_proxy: bool
    total_requests: int
    total_errors: int
    overall_success_rate: float


class InstanceInfo(BaseModel):
    """Instance information"""
    instance_id: str
    status: str
    headless: bool
    has_proxy: bool
    has_xs_common: bool
    created_at: str
    last_used_at: Optional[str]
    request_count: int
    error_count: int
    consecutive_errors: int
    success_rate: float


# Lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    config = get_config()

    logger.info(
        "starting_xys_sign_service",
        host=config.host,
        port=config.port,
        max_instances=config.max_instances,
        min_instances=config.min_instances,
        headless=config.headless,
    )

    # Initialize manager
    await init_xys_manager(
        max_instances=config.max_instances,
        min_instances=config.min_instances,
        headless=config.headless,
        browser_executable=config.default_browser_executable,
    )

    logger.info("xys_sign_service_ready")

    yield

    # Shutdown
    logger.info("shutting_down_xys_sign_service")
    await shutdown_xys_manager()
    logger.info("xys_sign_service_shutdown_complete")


# Create FastAPI app
app = FastAPI(
    title="XYS Sign Service V2",
    description="High-performance XYS signature generation service for XHS Creator platform",
    version="2.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/sign/xys", response_model=SignResponse)
async def generate_xys_signature(request: SignRequest):
    """
    Generate XYS format signature for XHS API.

    This endpoint generates X-s, X-t, and X-s-common headers
    required for XHS Creator platform APIs.
    """
    try:
        manager = get_xys_manager()
        result = await manager.generate_xys_signature(request.url, request.data)

        return SignResponse(
            success=True,
            **{
                "X-s": result.get("X-s", ""),
                "X-t": result.get("X-t", ""),
                "X-s-common": result.get("X-s-common", ""),
            }
        )

    except BrowserNotReadyError as e:
        logger.warning("sign_request_failed_no_instance", error=str(e))
        return SignResponse(
            success=False,
            error="No available browser instances"
        )

    except SignatureGenerationError as e:
        logger.error("sign_request_failed", error=str(e))
        return SignResponse(
            success=False,
            error=str(e)
        )

    except Exception as e:
        logger.error("sign_request_error", error=str(e))
        return SignResponse(
            success=False,
            error=f"Internal error: {str(e)}"
        )


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """
    Check service health status.

    Returns overall health status and instance information.
    """
    try:
        manager = get_xys_manager()
        health = await manager.health_check()

        return HealthResponse(
            status="healthy" if health["healthy_instances"] > 0 else "unhealthy",
            manager_status=health["manager_status"],
            total_instances=health["total_instances"],
            healthy_instances=health["healthy_instances"],
            max_instances=health["max_instances"],
            min_instances=health["min_instances"],
        )

    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """
    Get service statistics.

    Returns request counts, error rates, and instance information.
    """
    try:
        manager = get_xys_manager()
        stats = manager.get_stats()

        return StatsResponse(**stats)

    except Exception as e:
        logger.error("get_stats_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/api/instances")
async def list_instances():
    """
    List all browser instances.

    Returns detailed information about each instance.
    """
    try:
        manager = get_xys_manager()
        instances = manager.get_instances()

        return {
            "success": True,
            "count": len(instances),
            "instances": instances,
        }

    except Exception as e:
        logger.error("list_instances_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/api/instances/{instance_id}")
async def get_instance(instance_id: str):
    """
    Get information about a specific instance.
    """
    try:
        manager = get_xys_manager()
        instance = manager.get_instance(instance_id)

        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Instance {instance_id} not found"
            )

        return {
            "success": True,
            "instance": instance,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("get_instance_failed", instance_id=instance_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/api/instances")
async def create_instance():
    """
    Create a new browser instance.

    Adds a new instance to the pool if below maximum.
    """
    try:
        manager = get_xys_manager()
        instance = await manager.create_instance()

        return {
            "success": True,
            "message": "Instance created",
            "instance": instance,
        }

    except Exception as e:
        logger.error("create_instance_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.delete("/api/instances/{instance_id}")
async def delete_instance(instance_id: str):
    """
    Stop and remove a browser instance.
    """
    try:
        manager = get_xys_manager()
        await manager.stop_instance(instance_id)

        return {
            "success": True,
            "message": f"Instance {instance_id} stopped",
        }

    except Exception as e:
        logger.error("delete_instance_failed", instance_id=instance_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


class CookieResponse(BaseModel):
    """Cookie response"""
    success: bool
    a1: str = ""
    webId: str = ""
    web_session: str = ""
    all_cookies: Dict[str, str] = {}
    error: Optional[str] = None


@app.get("/api/cookies", response_model=CookieResponse)
async def get_cookies():
    """
    Get browser cookies (a1, webId, web_session, etc.)

    These cookies are required for XHS API authentication.
    """
    try:
        manager = get_xys_manager()
        cookies = await manager.get_cookies()

        if not cookies:
            return CookieResponse(
                success=False,
                error="No cookies available. Browser instances may not be ready."
            )

        return CookieResponse(
            success=True,
            a1=cookies.get("a1", ""),
            webId=cookies.get("webId", ""),
            web_session=cookies.get("web_session", ""),
            all_cookies=cookies,
        )

    except Exception as e:
        logger.error("get_cookies_failed", error=str(e))
        return CookieResponse(
            success=False,
            error=str(e)
        )


class XsecTokenRequest(BaseModel):
    """Request for getting xsec_token"""
    user_id: str


class XsecTokenResponse(BaseModel):
    """Response for xsec_token"""
    success: bool
    xsec_token: str = ""
    error: Optional[str] = None


@app.post("/api/xsec-token", response_model=XsecTokenResponse)
async def get_xsec_token(request: XsecTokenRequest):
    """
    Get xsec_token for a user profile page.

    This navigates to the user's profile page and extracts the xsec_token
    from the rendered page content.
    """
    try:
        manager = get_xys_manager()
        instance = await manager._get_available_instance()

        if not instance or not instance.page:
            return XsecTokenResponse(
                success=False,
                error="No available browser instance"
            )

        try:
            instance.status = InstanceStatus.BUSY
            page = instance.page

            # Navigate to user profile
            profile_url = f"https://www.xiaohongshu.com/user/profile/{request.user_id}"
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=20000)

            # Wait for Vue to render (reduced from 2s)
            await asyncio.sleep(1)

            # Extract xsec_token - simplified and faster
            xsec_token = await page.evaluate("""
                () => {
                    try {
                        // Method 1: Extract from page HTML (URL params) - fastest
                        const match = document.body.innerHTML.match(/xsec_token=([A-Za-z0-9_=%-]+)/);
                        if (match) {
                            return decodeURIComponent(match[1]);
                        }

                        // Method 2: Search for xsecToken in HTML
                        const match2 = document.body.innerHTML.match(/"xsecToken":"([^"]+)"/);
                        if (match2) {
                            return match2[1];
                        }

                        // Method 3: From __INITIAL_STATE__
                        if (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.user) {
                            let notes = window.__INITIAL_STATE__.user.notes;
                            if (notes && notes._rawValue) notes = notes._rawValue;
                            else if (notes && notes._value) notes = notes._value;

                            if (notes && Array.isArray(notes) && notes.length > 0) {
                                const first = Array.isArray(notes[0]) ? notes[0][0] : notes[0];
                                if (first && first.xsecToken) return first.xsecToken;
                                if (first && first.noteCard && first.noteCard.xsecToken) {
                                    return first.noteCard.xsecToken;
                                }
                            }
                        }
                        return null;
                    } catch (e) {
                        return null;
                    }
                }
            """)

            if xsec_token:
                return XsecTokenResponse(
                    success=True,
                    xsec_token=xsec_token
                )
            else:
                return XsecTokenResponse(
                    success=False,
                    error="Could not extract xsec_token from page"
                )

        finally:
            instance.status = InstanceStatus.READY
            # Navigate back to creator page to maintain session
            await page.goto("https://creator.xiaohongshu.com", wait_until="domcontentloaded", timeout=30000)

    except Exception as e:
        logger.error("get_xsec_token_failed", error=str(e), user_id=request.user_id)
        return XsecTokenResponse(
            success=False,
            error=str(e)
        )


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "XYS Sign Service V2",
        "version": "2.0.0",
        "endpoints": {
            "sign": "POST /api/sign/xys",
            "cookies": "GET /api/cookies",
            "xsec_token": "POST /api/xsec-token",
            "health": "GET /api/health",
            "stats": "GET /api/stats",
            "instances": "GET /api/instances",
        }
    }


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="XYS Sign Service V2")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--max-instances", type=int, default=5, help="Maximum browser instances")
    parser.add_argument("--min-instances", type=int, default=2, help="Minimum browser instances")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Run with browser UI")
    parser.add_argument("--log-level", default="INFO", help="Log level")

    args = parser.parse_args()

    # Initialize config
    init_config(
        host=args.host,
        port=args.port,
        max_instances=args.max_instances,
        min_instances=args.min_instances,
        headless=args.headless,
        log_level=args.log_level,
    )

    config = get_config()

    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info("received_shutdown_signal", signal=signum)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run server
    uvicorn.run(
        "server:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
