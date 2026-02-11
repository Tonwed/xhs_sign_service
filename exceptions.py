"""
XYS Sign Service Custom Exceptions
"""


class XYSSignServiceError(Exception):
    """Base exception for XYS sign service"""

    def __init__(self, message: str, code: str = "XYS_SIGN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
        }


class BrowserNotReadyError(XYSSignServiceError):
    """Browser instance is not ready"""

    def __init__(self, instance_id: str, message: str = "Browser instance is not ready"):
        self.instance_id = instance_id
        super().__init__(message, "BROWSER_NOT_READY")


class SignatureGenerationError(XYSSignServiceError):
    """Failed to generate signature"""

    def __init__(self, message: str = "Failed to generate signature"):
        super().__init__(message, "SIGNATURE_GENERATION_ERROR")


class CookieInjectionError(XYSSignServiceError):
    """Failed to inject cookies"""

    def __init__(self, message: str = "Failed to inject cookies"):
        super().__init__(message, "COOKIE_INJECTION_ERROR")


class HealthCheckError(XYSSignServiceError):
    """Health check failed"""

    def __init__(self, message: str = "Health check failed"):
        super().__init__(message, "HEALTH_CHECK_ERROR")


class PageLoadError(XYSSignServiceError):
    """Page failed to load properly"""

    def __init__(self, message: str = "Page failed to load"):
        super().__init__(message, "PAGE_LOAD_ERROR")


class InstanceLimitError(XYSSignServiceError):
    """Maximum instance limit reached"""

    def __init__(self, max_instances: int):
        self.max_instances = max_instances
        super().__init__(
            f"Maximum instance limit ({max_instances}) reached",
            "INSTANCE_LIMIT_ERROR"
        )


class InstanceNotFoundError(XYSSignServiceError):
    """Instance not found"""

    def __init__(self, instance_id: str):
        self.instance_id = instance_id
        super().__init__(
            f"Instance {instance_id} not found",
            "INSTANCE_NOT_FOUND"
        )


class XSCommonNotFoundError(XYSSignServiceError):
    """X-S-Common not captured"""

    def __init__(self, message: str = "X-S-Common header not captured"):
        super().__init__(message, "XS_COMMON_NOT_FOUND")
