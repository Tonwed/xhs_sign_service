# XYS Sign Service

小红书 Creator 平台签名服务，提供 XYS 格式签名生成能力。

## 快速开始

```bash
# 安装依赖
pip install playwright aiohttp fastapi uvicorn structlog pydantic pydantic-settings
playwright install chromium

# 启动服务 (默认 http://localhost:8080)
python server.py

# 登录 (cookies 保存到 login_cookies.json)
python test_login.py
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/sign/xys` | 生成签名 (`X-s`, `X-t`, `X-s-common`) |
| `GET` | `/api/cookies` | 获取浏览器安全 cookies |
| `POST` | `/api/xsec-token` | 获取用户 xsec_token |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/stats` | 服务统计 |
| `GET` | `/api/instances` | 实例列表 |

**签名请求示例：**

```bash
curl -X POST http://localhost:8080/api/sign/xys \
  -H "Content-Type: application/json" \
  -d '{"url": "/api/sns/web/v1/search/notes", "data": "{\"keyword\":\"美食\"}"}'
```

## 测试脚本

```bash
python test_login.py                              # 登录
python test_login.py --sign-only                   # 仅测试签名
python test_search.py "关键词"                      # 搜索笔记
python test_user_posted.py --user-id <用户ID>       # 获取博主笔记
```

搜索和博主笔记脚本需要先完成登录，自动从 `login_cookies.json` 加载凭证。

## 签名原理

服务通过 Playwright 驱动 Chromium 浏览器，访问 `creator.xiaohongshu.com` 页面获取签名运行环境，核心流程如下：

```
请求参数 (url + data)
       │
       ▼
  ┌──────────┐
  │ MD5 哈希  │  payload = url + data → MD5(payload)
  └────┬─────┘
       │
       ▼
  ┌──────────┐
  │  mnsv2   │  调用页面内置 window.mnsv2(payload, hash) 生成核心签名
  └────┬─────┘
       │
       ▼
  ┌──────────────────────────────────┐
  │ 构建签名对象                      │
  │  {                               │
  │    x0: "4.2.8"      // 版本号    │
  │    x1: "ugc"        // 应用标识  │
  │    x2: "Windows"    // 平台      │
  │    x3: mnsResult    // 核心签名  │
  │    x4: typeof(data) // 数据类型  │
  │  }                               │
  └────┬─────────────────────────────┘
       │
       ▼
  JSON.stringify → UTF-8 编码 (Af) → 自定义 Base64 编码 (TF)
       │
       ▼
  X-s = "XYS_" + encoded
```

## 配置

支持命令行参数、环境变量（`XYS_` 前缀）和 `.env` 文件：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `host` | `0.0.0.0` | 监听地址 |
| `port` | `8080` | 端口 |
| `min_instances` | `2` | 最小浏览器实例数 |
| `max_instances` | `5` | 最大浏览器实例数 |
| `headless` | `true` | 无头模式 |
| `sign_timeout` | `5000` | 签名超时 (ms) |
| `proxy_server` | - | 代理服务器 |
| `browser_executable` | - | 自定义浏览器路径 |

## 项目结构

```
xhs_sign-service/
├── server.py           # FastAPI HTTP 服务器
├── xys_manager.py      # 多实例管理器
├── xys_service.py      # 签名服务核心逻辑
├── xys_scripts.py      # 浏览器注入脚本
├── config.py           # 配置管理
├── exceptions.py       # 自定义异常
├── stealth.min.js      # 浏览器反检测脚本
├── test_login.py       # 登录脚本
├── test_search.py      # 笔记搜索脚本
└── test_user_posted.py # 博主笔记脚本
```
