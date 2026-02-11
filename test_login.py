#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
小红书 Creator 平台登录脚本

功能：
1. 从 Sign Service 获取浏览器 cookies (a1, webId, gid 等)
2. 使用 Sign Service 生成 XYS 签名
3. 发送手机验证码
4. 使用验证码完成登录
5. 保存登录后的 cookies 到文件

使用方法：
    python test_login.py              # 完整登录流程
    python test_login.py --sign-only  # 仅测试签名功能
    python test_login.py --cookies    # 仅获取当前 cookies

依赖：
    pip install aiohttp

注意：
    运行前需要先启动 Sign Service: python server.py
"""

import asyncio
import aiohttp
import json
import sys
import os
from datetime import datetime
from typing import Dict, Optional, List


class XHSCreatorLogin:
    """小红书 Creator 平台登录客户端"""

    def __init__(self, sign_service_url: str = "http://localhost:8080"):
        self.sign_service_url = sign_service_url
        self.base_url = "https://customer.xiaohongshu.com"
        self.service_url = "https://creator.xiaohongshu.com"
        
        # Cookies from sign service
        self.cookies: Dict[str, str] = {}
        
        # 请求头
        self.headers = {
            "Content-Type": "application/json",
            "Origin": self.service_url,
            "Referer": f"{self.service_url}/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "authorization": "",
            "x-ratelimit-meta": "host=creator.xiaohongshu.com",
        }

    def _build_cookie_string(self) -> str:
        """构建 Cookie 请求头字符串"""
        return "; ".join([f"{k}={v}" for k, v in self.cookies.items()])

    async def check_sign_service(self, session: aiohttp.ClientSession) -> bool:
        """检查签名服务是否可用"""
        try:
            async with session.get(
                f"{self.sign_service_url}/api/health", 
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                result = await resp.json()
                return result.get("status") == "healthy"
        except Exception as e:
            print(f"  Error: {e}")
            return False

    async def fetch_cookies(self, session: aiohttp.ClientSession) -> bool:
        """从签名服务获取所有 cookies"""
        try:
            async with session.get(
                f"{self.sign_service_url}/api/cookies", 
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                result = await resp.json()
                
                if not result.get("success"):
                    print(f"  Error: {result.get('error', 'Unknown error')}")
                    return False
                
                # 使用所有从 sign service 获取的 cookies
                all_cookies = result.get("all_cookies", {})
                
                # 添加必要的固定 cookie
                all_cookies["xsecappid"] = "ugc"
                
                self.cookies = all_cookies
                
                # 检查关键 cookies
                key_cookies = ["a1", "webId", "gid", "websectiga", "sec_poison_id"]
                missing = [k for k in key_cookies if not self.cookies.get(k)]
                if missing:
                    print(f"  Warning: Missing cookies: {', '.join(missing)}")
                    
                return True
                
        except Exception as e:
            print(f"  Error fetching cookies: {e}")
            return False

    async def get_signature(self, session: aiohttp.ClientSession, url: str, data: str) -> dict:
        """获取 XYS 签名"""
        async with session.post(
            f"{self.sign_service_url}/api/sign/xys",
            json={"url": url, "data": data},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            result = await resp.json()
            if not result.get("success"):
                raise Exception(f"Sign failed: {result.get('error', 'Unknown')}")
            return {
                "X-s": result["X-s"],
                "X-t": result["X-t"],
                "X-s-common": result.get("X-s-common", "")
            }

    async def send_verify_code(self, session: aiohttp.ClientSession, phone: str, zone: str = "86") -> dict:
        """发送手机验证码"""
        api_url = "/api/cas/customer/web/verify-code"
        request_body = json.dumps({
            "service": self.service_url,
            "phone": phone,
            "zone": zone
        }, separators=(",", ":"))

        sign_data = await self.get_signature(session, api_url, request_body)
        headers = {
            **self.headers,
            "Cookie": self._build_cookie_string(),
            "X-s": sign_data["X-s"],
            "X-t": sign_data["X-t"],
            "X-S-Common": sign_data["X-s-common"],
        }

        async with session.post(
            f"{self.base_url}{api_url}",
            headers=headers,
            data=request_body,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            return await resp.json()

    async def login_with_code(self, session: aiohttp.ClientSession, phone: str, code: str, zone: str = "86") -> dict:
        """使用验证码登录"""
        api_url = "/api/cas/customer/web/service-ticket"
        
        request_body = json.dumps({
            "service": self.service_url,
            "zone": zone,
            "phone": phone,
            "verify_code": code,
            "source": "",
            "type": "phoneVerifyCode"
        }, separators=(",", ":"))

        try:
            sign_data = await self.get_signature(session, api_url, request_body)
            headers = {
                **self.headers,
                "Cookie": self._build_cookie_string(),
                "X-s": sign_data["X-s"],
                "X-t": sign_data["X-t"],
                "X-S-Common": sign_data["X-s-common"],
            }

            async with session.post(
                f"{self.base_url}{api_url}",
                headers=headers,
                data=request_body,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                result = await resp.json()
                set_cookies = resp.headers.getall("Set-Cookie", [])
                return {
                    "success": result.get("success", False),
                    "response": result,
                    "cookies": self._parse_cookies(set_cookies)
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _parse_cookies(self, set_cookie_headers: List[str]) -> Dict[str, str]:
        """解析 Set-Cookie 响应头"""
        cookies = {}
        for header in set_cookie_headers:
            # 取第一个分号前的部分
            cookie_part = header.split(";")[0]
            if "=" in cookie_part:
                name, value = cookie_part.split("=", 1)
                cookies[name.strip()] = value.strip()
        return cookies

    def save_cookies(self, login_cookies: Dict[str, str], filename: str = "login_cookies.json"):
        """保存登录后的 cookies 到文件"""
        # 合并原有 cookies 和登录返回的 cookies
        all_cookies = {**self.cookies, **login_cookies}
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "cookies": all_cookies
        }
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return filename


def sync_input(prompt: str) -> str:
    """同步读取用户输入"""
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


async def main():
    """完整登录流程"""
    print("=" * 60)
    print("  小红书 Creator 平台登录")
    print("=" * 60)
    print()

    client = XHSCreatorLogin()
    connector = aiohttp.TCPConnector(limit=10)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        # Step 1: 检查签名服务
        print("[1/5] 检查签名服务...")
        if not await client.check_sign_service(session):
            print("  ❌ 签名服务未运行")
            print("  请先启动: python server.py")
            return
        print("  ✓ 服务正常")

        # Step 2: 获取 cookies
        print("\n[2/5] 获取浏览器 cookies...")
        if not await client.fetch_cookies(session):
            print("  ❌ 获取 cookies 失败")
            return
        print(f"  ✓ 获取 {len(client.cookies)} 个 cookies")
        print(f"    a1: {client.cookies.get('a1', '')[:20]}..." if client.cookies.get('a1') else "    a1: (empty)")
        print(f"    webId: {client.cookies.get('webId', '')[:20]}..." if client.cookies.get('webId') else "    webId: (empty)")

        # Step 3: 输入手机号
        print("\n[3/5] 输入手机号")
        loop = asyncio.get_event_loop()
        phone = await loop.run_in_executor(None, sync_input, "  手机号: ")
        if not phone:
            print("  已取消")
            return

        # Step 4: 发送验证码
        print("\n[4/5] 发送验证码...")
        result = await client.send_verify_code(session, phone)
        if not result.get("success"):
            print(f"  ❌ 发送失败: {result}")
            return
        print("  ✓ 验证码已发送，请查收短信")

        # Step 5: 输入验证码并登录
        print("\n[5/5] 登录")
        code = await loop.run_in_executor(None, sync_input, "  验证码: ")
        if not code:
            print("  已取消")
            return

        print("  正在登录...")
        result = await client.login_with_code(session, phone, code)
        
        print()
        print("=" * 60)
        if result.get("success"):
            print("  ✅ 登录成功!")
            print("=" * 60)
            
            # 显示获取的 cookies
            login_cookies = result.get("cookies", {})
            print("\n获取的登录 cookies:")
            for name, value in login_cookies.items():
                display_value = value[:40] + "..." if len(value) > 40 else value
                print(f"  {name}: {display_value}")
            
            # 保存 cookies
            filename = client.save_cookies(login_cookies)
            print(f"\n✓ Cookies 已保存到: {filename}")
        else:
            print("  ❌ 登录失败")
            print("=" * 60)
            print(f"\n响应: {json.dumps(result.get('response', result), indent=2, ensure_ascii=False)}")


async def test_sign():
    """测试签名功能"""
    print("=" * 60)
    print("  XYS 签名测试")
    print("=" * 60)
    
    client = XHSCreatorLogin()
    
    async with aiohttp.ClientSession() as session:
        print("\n[1/3] 检查签名服务...")
        if not await client.check_sign_service(session):
            print("  ❌ 签名服务未运行")
            return
        print("  ✓ 服务正常")
        
        print("\n[2/3] 获取 cookies...")
        if not await client.fetch_cookies(session):
            print("  ❌ 失败")
            return
        print(f"  ✓ 获取 {len(client.cookies)} 个 cookies")
        
        print("\n[3/3] 测试签名生成...")
        test_url = "/api/cas/customer/web/verify-code"
        test_data = '{"service":"https://creator.xiaohongshu.com","phone":"13800138000","zone":"86"}'
        
        try:
            sign = await client.get_signature(session, test_url, test_data)
            print(f"  ✓ 签名生成成功")
            print(f"    X-s: {sign['X-s'][:50]}...")
            print(f"    X-t: {sign['X-t']}")
            print(f"    X-s-common: {sign['X-s-common'][:50]}..." if sign['X-s-common'] else "    X-s-common: (empty)")
        except Exception as e:
            print(f"  ❌ 失败: {e}")


async def test_cookies():
    """测试 cookies 获取"""
    print("=" * 60)
    print("  Cookies 获取测试")
    print("=" * 60)
    
    client = XHSCreatorLogin()
    
    async with aiohttp.ClientSession() as session:
        print("\n[1/2] 检查签名服务...")
        if not await client.check_sign_service(session):
            print("  ❌ 签名服务未运行")
            return
        print("  ✓ 服务正常")
        
        print("\n[2/2] 获取 cookies...")
        if not await client.fetch_cookies(session):
            print("  ❌ 失败")
            return
            
        print(f"\n共获取 {len(client.cookies)} 个 cookies:")
        print("-" * 40)
        for name, value in sorted(client.cookies.items()):
            if value:
                display_value = value[:50] + "..." if len(value) > 50 else value
                print(f"  {name}: {display_value}")
            else:
                print(f"  {name}: (empty)")


def print_usage():
    """打印使用说明"""
    print("""
小红书 Creator 平台登录脚本

使用方法:
  python test_login.py              完整登录流程
  python test_login.py --sign-only  仅测试签名功能
  python test_login.py --cookies    仅获取当前 cookies
  python test_login.py --help       显示此帮助信息

注意:
  运行前需要先启动 Sign Service:
    python server.py
""")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--sign-only":
            asyncio.run(test_sign())
        elif arg == "--cookies":
            asyncio.run(test_cookies())
        elif arg in ["--help", "-h"]:
            print_usage()
        else:
            print(f"未知选项: {arg}")
            print_usage()
    else:
        asyncio.run(main())
