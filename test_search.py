#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
小红书笔记搜索测试脚本

使用 Sign Service 获取签名和安全 cookies，结合用户登录 cookies 进行搜索

使用方法：
    python test_search.py "关键词"
    python test_search.py "关键词" --page 2
    python test_search.py --help
"""

import asyncio
import aiohttp
import json
import sys
from typing import Dict, Optional, List


class XHSSearchClient:
    """小红书笔记搜索客户端"""

    def __init__(self, sign_service_url: str = "http://localhost:8080"):
        self.sign_service_url = sign_service_url
        self.base_url = "https://edith.xiaohongshu.com"
        
        # 安全 cookies (从签名服务获取)
        self.security_cookies: Dict[str, str] = {}

        # 用户登录 cookies (从 login_cookies.json 加载)
        self.user_cookies: Dict[str, str] = {}
        
        # 请求头
        self.headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://www.xiaohongshu.com",
            "Referer": "https://www.xiaohongshu.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _build_cookie_string(self) -> str:
        """合并安全 cookies 和用户 cookies"""
        all_cookies = {**self.security_cookies, **self.user_cookies}
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
                
                if not result.get("success"):
                    print(f"  Error: {result.get('error', 'Unknown')}")
                    return False
                
                all_cookies = result.get("all_cookies", {})
                
                # 只取安全相关的 cookies
                security_keys = ["a1", "webId", "gid", "websectiga", "sec_poison_id", "acw_tc", "loadts", "xsecappid"]
                self.security_cookies = {k: v for k, v in all_cookies.items() if k in security_keys or k not in self.user_cookies}
                
                # 确保 xsecappid 设置为 xhs-pc-web (Web 端)
                self.security_cookies["xsecappid"] = "xhs-pc-web"
                
                return True
                
        except Exception as e:
            print(f"  Error: {e}")
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

    async def search_notes(
        self,
        session: aiohttp.ClientSession,
        keyword: str,
        page: int = 1,
        page_size: int = 20,
        sort: str = "general",
        note_type: int = 0
    ) -> dict:
        """
        搜索小红书笔记
        
        Args:
            keyword: 搜索关键词
            page: 页码
            page_size: 每页数量
            sort: 排序方式 (general/hot/time)
            note_type: 笔记类型 (0=全部, 1=视频, 2=图文)
        """
        api_url = "/api/sns/web/v1/search/notes"
        
        # 生成随机 search_id
        import random
        import string
        search_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=21))
        
        request_body = json.dumps({
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "search_id": search_id,
            "sort": sort,
            "note_type": note_type,
            "ext_flags": [],
            "geo": "",
            "image_formats": ["jpg", "webp", "avif"]
        }, separators=(",", ":"))

        # 获取签名
        sign_data = await self.get_signature(session, api_url, request_body)
        
        headers = {
            **self.headers,
            "Cookie": self._build_cookie_string(),
            "X-s": sign_data["X-s"],
            "X-t": sign_data["X-t"],
            "X-s-common": sign_data["X-s-common"],
        }

        async with session.post(
            f"{self.base_url}{api_url}",
            headers=headers,
            data=request_body,
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


async def main(keyword: str, page: int = 1):
    """搜索笔记"""
    print("=" * 60)
    print("  小红书笔记搜索")
    print("=" * 60)
    print()

    client = XHSSearchClient()
    
    # 从文件加载登录 cookies
    if client.load_cookies_from_file():
        print("✓ 已从 login_cookies.json 加载登录信息")
    else:
        print("✗ 未找到 login_cookies.json，请先运行 python test_login.py 登录")
        return
    print()

    async with aiohttp.ClientSession() as session:
        # Step 1: 检查签名服务
        print("[1/3] 检查签名服务...")
        if not await client.check_sign_service(session):
            print("  ❌ 签名服务未运行")
            print("  请先启动: python server.py")
            return
        print("  ✓ 服务正常")

        # Step 2: 获取安全 cookies
        print("\n[2/3] 获取安全 cookies...")
        if not await client.fetch_security_cookies(session):
            print("  ❌ 获取失败")
            return
        print(f"  ✓ a1: {client.security_cookies.get('a1', '')[:20]}...")
        print(f"  ✓ webId: {client.security_cookies.get('webId', '')[:20]}...")

        # Step 3: 搜索笔记
        print(f"\n[3/3] 搜索: {keyword} (第 {page} 页)...")
        try:
            result = await client.search_notes(session, keyword, page=page)
            
            print()
            print("=" * 60)
            
            if result.get("success"):
                items = result.get("data", {}).get("items", [])
                has_more = result.get("data", {}).get("has_more", False)
                
                print(f"  ✅ 搜索成功! 找到 {len(items)} 条结果")
                print("=" * 60)
                print()
                
                for i, item in enumerate(items[:10], 1):  # 只显示前10条
                    note_card = item.get("note_card", {})
                    note_id = item.get("id", "")
                    title = note_card.get("display_title", "无标题")
                    user = note_card.get("user", {})
                    nickname = user.get("nickname", "未知用户")
                    liked_count = note_card.get("interact_info", {}).get("liked_count", "0")
                    
                    print(f"{i}. [{note_id[:8]}...] {title[:40]}")
                    print(f"   👤 {nickname} | ❤️ {liked_count}")
                    print()
                
                if len(items) > 10:
                    print(f"... 还有 {len(items) - 10} 条结果")
                
                if has_more:
                    print(f"\n💡 还有更多结果，使用 --page {page + 1} 查看下一页")
            else:
                print("  ❌ 搜索失败")
                print("=" * 60)
                print(f"\n响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
                
        except Exception as e:
            print(f"  ❌ 搜索出错: {e}")


def print_usage():
    print("""
小红书笔记搜索脚本

使用方法:
  python test_search.py "关键词"
  python test_search.py "关键词" --page 2
  python test_search.py --help

参数:
  关键词        搜索的关键词
  --page N      页码 (默认: 1)

示例:
  python test_search.py "美食"
  python test_search.py "旅行攻略" --page 3

注意:
  运行前需要先启动 Sign Service: python server.py
""")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ["--help", "-h"]:
        print_usage()
        sys.exit(0)
    
    keyword = sys.argv[1]
    page = 1
    
    # 解析 --page 参数
    if "--page" in sys.argv:
        try:
            page_idx = sys.argv.index("--page")
            page = int(sys.argv[page_idx + 1])
        except (ValueError, IndexError):
            print("错误: --page 需要一个数字参数")
            sys.exit(1)
    
    asyncio.run(main(keyword, page))
