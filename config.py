"""
XYS Sign Service Configuration
"""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class XYSServiceConfig(BaseSettings):
    """Configuration for XYS Sign Service"""

    # Server settings
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8080, description="Server port")

    # Instance pool settings
    max_instances: int = Field(default=5, description="Maximum browser instances")
    min_instances: int = Field(default=2, description="Minimum browser instances")

    # Browser settings
    headless: bool = Field(default=True, description="Run browser in headless mode")
    browser_executable: Optional[str] = Field(
        default=None,
        description="Path to browser executable"
    )

    # Timeouts
    page_timeout: int = Field(default=30000, description="Page load timeout in ms")
    sign_timeout: int = Field(default=5000, description="Signature generation timeout in ms")

    # XHS URLs
    creator_url: str = Field(
        default="https://creator.xiaohongshu.com",
        description="XHS Creator platform URL"
    )

    # Proxy settings
    proxy_server: Optional[str] = Field(default=None, description="Proxy server URL")
    proxy_username: Optional[str] = Field(default=None, description="Proxy username")
    proxy_password: Optional[str] = Field(default=None, description="Proxy password")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")

    # Browser data directory
    browser_data_dir: Optional[str] = Field(
        default=None,
        description="Browser user data directory"
    )

    class Config:
        env_prefix = "XYS_"
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def proxy_config(self) -> Optional[dict]:
        """Get proxy configuration dict"""
        if not self.proxy_server:
            return None

        config = {"server": self.proxy_server}
        if self.proxy_username:
            config["username"] = self.proxy_username
        if self.proxy_password:
            config["password"] = self.proxy_password

        return config

    @property
    def default_browser_data_dir(self) -> Path:
        """Get default browser data directory"""
        if self.browser_data_dir:
            return Path(self.browser_data_dir)

        base_dir = Path(__file__).parent
        return base_dir / "browser_data"

    @property
    def default_browser_executable(self) -> Optional[str]:
        """Get default browser executable path"""
        if self.browser_executable:
            return self.browser_executable

        # Check for bundled ungoogled-chromium
        base_dir = Path(__file__).parent
        chromium_path = (
            base_dir / "fingerprint-browser" /
            "ungoogled-chromium_142.0.7444.175-1.1_windows_x64" / "chrome.exe"
        )

        if chromium_path.exists():
            return str(chromium_path)

        return None


# Global config instance
_config: Optional[XYSServiceConfig] = None


def get_config() -> XYSServiceConfig:
    """Get the global config instance"""
    global _config
    if _config is None:
        _config = XYSServiceConfig()
    return _config


def init_config(**kwargs) -> XYSServiceConfig:
    """Initialize config with custom values"""
    global _config
    _config = XYSServiceConfig(**kwargs)
    return _config
