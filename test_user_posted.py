#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
小红书博主笔记获取测试脚本

使用 Sign Service 获取签名和安全 cookies，结合用户登录 cookies 获取博主发布的笔记

使用方法：
    python test_user_posted.py --user-id 5c2686820000000007031438
    python test_user_posted.py --user-id 5c2686820000000007031438 --num 30
    python test_user_posted.py --user-id 5c2686820000000007031438 --cursor xxxxx
    python test_user_posted.py --help
"""

import asyncio
import aiohttp
import json
import sys
from typing import Dict, Optional
from urllib.parse import urlencode
import re


class XHSUserPostedClient:
    """小红书博主笔记获取客户端"""

    def __init__(self, sign_service_url: str = "http://localhost:8080"):
        self.sign_service_url = sign_service_url
        self.base_url = "https://edith.xiaohongshu.com"

        # 安全 cookies (从签名服务获取)
        self.security_cookies: Dict[str, str] = {}

        # 用户登录 cookies (从 login_cookies.json 加载)
        self.user_cookies: Dict[str, str] = {}

        # 请求头
        self.headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Origin": "https://www.xiaohongshu.com",
            "Referer": "https://www.xiaohongshu.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0",
            "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Microsoft Edge";v="144"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
        }

    def _build_cookie_string(self) -> str:
        """合并安全 cookies 和用户 cookies

        关键：用户登录 cookies 必须覆盖签名服务的 cookies，
        因为 web_session 需要与 a1 等一起使用才能正常认证。
        """
        # 安全 cookies 为基础，用户 cookies 覆盖
        all_cookies = {**self.security_cookies, **self.user_cookies}

        # 强制设置 xsecappid 为 xhs-pc-web（Web 端 API 必需）
        all_cookies["xsecappid"] = "xhs-pc-web"

        return "; ".join([f"{k}={v}" for k, v in all_cookies.items()])

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

    async def fetch_security_cookies(self, session: aiohttp.ClientSession) -> bool:
        """从签名服务获取安全 cookies (a1, webId, gid 等)"""
        try:
            async with session.get(
                f"{self.sign_service_url}/api/cookies",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                result = await resp.json()
                print(f"  Sign Service Cookies Response: {json.dumps(result, indent=2, ensure_ascii=False)}")

                if not result.get("success"):
                    print(f"  Error: {result.get('error', 'Unknown')}")
                    return False

                all_cookies = result.get("all_cookies", {})

                # 获取所有安全 cookies
                self.security_cookies = dict(all_cookies)

                # 确保 xsecappid 设置为 xhs-pc-web (Web 端)
                self.security_cookies["xsecappid"] = "xhs-pc-web"

                return True

        except Exception as e:
            print(f"  Error: {e}")
            return False


    async def get_signature(self, session: aiohttp.ClientSession, url: str, data: str = "") -> dict:
        """获取 XYS 签名"""
        async with session.post(
            f"{self.sign_service_url}/api/sign/xys",
            json={"url": url, "data": data},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            result = await resp.json()
            print(f"  Sign Service Signature Response: {json.dumps(result, indent=2, ensure_ascii=False)}")
            if not result.get("success"):
                raise Exception(f"Sign failed: {result.get('error', 'Unknown')}")
            return {
                "X-s": result["X-s"],
                "X-t": result["X-t"],
                "X-s-common": result.get("X-s-common", "")
            }

    async def get_user_posted(
        self,
        session: aiohttp.ClientSession,
        user_id: str,
        num: int = 30,
        cursor: Optional[str] = None
    ) -> dict:
        """
        获取博主发布的笔记

        Args:
            user_id: 博主用户 ID
            num: 每页数量 (默认 30)
            cursor: 分页游标 (用于获取下一页)
        """
        # 构建查询参数 - 手动构建以避免 urlencode 对逗号进行编码
        parts = [
            f"num={num}",
            f"user_id={user_id}",
            "image_formats=jpg,webp,avif",
        ]

        if cursor:
            # cursor 放在最前面
            parts.insert(0, f"cursor={cursor}")

        query_string = "&".join(parts)
        api_url = f"/api/sns/web/v1/user_posted?{query_string}"

        # 获取签名 (GET 请求，data 为空)
        sign_data = await self.get_signature(session, api_url, "")

        headers = {
            **self.headers,
            "Cookie": self._build_cookie_string(),
            "X-s": sign_data["X-s"],
            "X-t": sign_data["X-t"],
            "X-s-common": sign_data["X-s-common"],
        }

        # Debug: 打印请求信息
        print(f"  API URL: {api_url[:80]}...")

        async with session.get(
            f"{self.base_url}{api_url}",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            return await resp.json()

    def load_cookies_from_file(self, filename: str = "login_cookies.json") -> bool:
        """从文件加载登录 cookies"""
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                cookies = data.get("cookies", {})
                # 更新用户 cookies (排除安全类 cookies)
                security_keys = ["a1", "webId", "gid", "websectiga", "sec_poison_id", "acw_tc", "loadts", "xsecappid"]
                for k, v in cookies.items():
                    if k not in security_keys:
                        self.user_cookies[k] = v
                return True
        except FileNotFoundError:
            return False
        except Exception as e:
            print(f"  Load cookies error: {e}")
            return False


async def main(user_id: str, num: int = 30, cursor: Optional[str] = None):
    """获取博主笔记"""
    print("=" * 60)
    print("  小红书博主笔记获取")
    print("=" * 60)
    print()

    client = XHSUserPostedClient()

    # 从文件加载登录 cookies
    if client.load_cookies_from_file():
        print("[OK] 已从 login_cookies.json 加载登录信息")
    else:
        print("[FAILED] 未找到 login_cookies.json，请先运行 python test_login.py 登录")
        return
    print()

    async with aiohttp.ClientSession() as session:
        # Step 1: 检查签名服务
        print("[1/3] 检查签名服务...")
        if not await client.check_sign_service(session):
            print("  [FAILED] 签名服务未运行")
            print("  请先启动: python server.py")
            return
        print("  [OK] 服务正常")

        # Step 2: 获取安全 cookies
        print("\n[2/3] 获取安全 cookies...")
        if not await client.fetch_security_cookies(session):
            print("  [FAILED] 获取失败")
            return
        print(f"  [OK] a1: {client.security_cookies.get('a1', '')[:20]}...")
        print(f"  [OK] webId: {client.security_cookies.get('webId', '')[:20]}...")

        # Step 3: 获取博主笔记
        cursor_info = f" (cursor: {cursor[:16]}...)" if cursor else ""
        print(f"\n[3/3] 获取博主笔记: {user_id}{cursor_info}...")

        try:
            result = await client.get_user_posted(
                session,
                user_id=user_id,
                num=num,
                cursor=cursor
            )

            print()
            print("=" * 60)

            if result.get("success"):
                data = result.get("data", {})
                notes = data.get("notes", [])
                next_cursor = data.get("cursor", "")
                has_more = data.get("has_more", False)

                print(f"  [SUCCESS] 获取成功! 共 {len(notes)} 条笔记")
                print("=" * 60)
                print()

                for i, note in enumerate(notes, 1):
                    note_id = note.get("note_id", "")
                    title = note.get("display_title", "无标题")
                    note_type = note.get("type", "unknown")
                    user = note.get("user", {})
                    nickname = user.get("nickname", "未知用户")
                    liked_count = note.get("interact_info", {}).get("liked_count", "0")
                    xsec_token = note.get("xsec_token", "")

                    type_emoji = "[VIDEO]" if note_type == "video" else "[IMAGE]"

                    print(f"{i:2d}. {type_emoji} [{note_id[:12]}...]")
                    print(f"    [NOTE] {title[:50]}")
                    print(f"    [USER] {nickname} | [LIKE] {liked_count}")
                    if xsec_token:
                        print(f"    [KEY] xsec_token: {xsec_token[:20]}...")
                    print()

                if has_more and next_cursor:
                    print("-" * 60)
                    print(f"[TIP] 还有更多笔记，使用以下命令获取下一页:")
                    print(f"   python test_user_posted.py --user-id {user_id} --cursor \"{next_cursor}\"")
                    print()
                elif not has_more:
                    print("-" * 60)
                    print("[END] 已获取所有笔记")

            else:
                print("  [FAILED] 获取失败")
                print("=" * 60)
                print(f"\n响应: {json.dumps(result, indent=2, ensure_ascii=False)}")

        except Exception as e:
            print(f"  [FAILED] 获取出错: {e}")
            import traceback
            traceback.print_exc()


def print_usage():
    print("""
小红书博主笔记获取脚本

使用方法:
  python test_user_posted.py --user-id <用户ID>
  python test_user_posted.py --user-id <用户ID> --num 30
  python test_user_posted.py --user-id <用户ID> --cursor <游标>
  python test_user_posted.py --help

参数:
  --user-id ID       博主用户 ID (必填)
  --num N            每页数量 (默认: 30)
  --cursor STR       分页游标 (用于获取下一页)

示例:
  python test_user_posted.py --user-id 5c2686820000000007031438
  python test_user_posted.py --user-id 5c2686820000000007031438 --cursor "6971d904000000000b00802c"

注意:
  - 运行前需要先启动 Sign Service: python server.py
""")


def parse_args():
    """解析命令行参数"""
    args = {
        "user_id": None,
        "num": 30,
        "cursor": None,
    }

    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] in ["--help", "-h"]:
            return None
        elif argv[i] == "--user-id" and i + 1 < len(argv):
            args["user_id"] = argv[i + 1]
            i += 2
        elif argv[i] == "--num" and i + 1 < len(argv):
            try:
                args["num"] = int(argv[i + 1])
            except ValueError:
                print("错误: --num 需要一个数字参数")
                sys.exit(1)
            i += 2
        elif argv[i] == "--cursor" and i + 1 < len(argv):
            args["cursor"] = argv[i + 1]
            i += 2
        else:
            i += 1

    return args


if __name__ == "__main__":
    args = parse_args()

    if args is None or args["user_id"] is None:
        print_usage()
        sys.exit(0)

    asyncio.run(main(
        user_id=args["user_id"],
        num=args["num"],
        cursor=args["cursor"]
    ))
