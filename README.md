# HumanChatApi V1.0

将你装进兼容标准 OpenAI 接口的 LLM 里扮演Assistant与用户聊天。

真人工智能llm：纯人工没有智能🌚🌚🌚
- 纯人工回复的llm大模型
- 兼容标准 OpenAI 接口
- 支持自动回复和手动回复
- 支持/v1/models拉取模型列表

**HumanChatApi** 是一款可以 **纯人工接管的模拟大模型 API 服务** 的项目，完全兼容标准 OpenAI 接口。所有对话请求不会经过任何AI模型，将由你 **自己** 在后台 **扮演AI大模型** 与用户聊天。
**轻量化单文件部署，自带可视化管理后台。**
- （这么猎奇的项目思路不来给我点点star）

- 后端：Python **标准库** `http.server`（**零第三方依赖**）
- 前端：原生 HTML + JS（零框架，由**后端直接渲染**完整页面）
- 存储：内存会话队列（断电清空）

---

## 快速开始

### 1. 直接启动（无需安装任何包）

```bash
cd humanchatapi
python3 StartServer.py
```

> ✅ **零依赖**：只用了 Python 标准库（`http.server` / `threading` / `json` / `urllib`），
> Android Termux、桌面 Linux、Windows 的 Python 3.8+ 都可以直接跑，**不需要 pip install**。

### 2. 访问

| 地址 | 用途 |
| --- | --- |
| `http://127.0.0.1:1234/v1` | OpenAI 客户端 `base_url` |
| `http://127.0.0.1:1234/admin` | 人工管理后台 |

---

## 会话生命周期（重要）

```
客户端请求 → 创建会话(waiting) → 管理员后台回复 → 客户端收到回复
     ↓
会话【不删除】，状态变为 completed，保留在后台供回看完整上下文
     ↓
只有管理员在后台【手动关闭会话】，才从内存中删除
```

- ✅ **单次持久化**：回复完成后会话依然保留在后台（首页「已回复会话」区），可随时点开回看完整历史（含图片）
- ✅ **手动关闭**：会话详情页提供「关闭会话」按钮，关闭后才从内存移除
- ✅ **内存存储**：服务重启后全部清空

---

## 功能边界（V1.0 锁定）

### ✅ 必须支持
- 标准文本对话上下文
- GPT4V 图片输入解析（`image_url` 网络链接 / `base64` 内嵌）
- `GET /v1/models` 标准模型探测接口
- WebUI 后台自动渲染图片，管理员可看图作答

### ❌ 绝对不支持（代码强制）
- 视频 / 音频解析（代码层拦截丢弃）
- ToolCall / FunctionCall（`tools`、`function_call` 字段强制清空）
- 流式输出（仅完整阻塞返回）
- 鉴权（本机 / 局域网可直接访问）

---

## 接口

| 接口 | 方法 | 用途 |
| --- | --- | --- |
| `/v1/chat/completions` | POST | OpenAI 兼容对话接口 |
| `/v1/models` | GET | 标准模型探测接口 |
| `/admin` | GET | 后台首页（后端渲染统计 + 服务模式 + 待处理 + 已回复卡片） |
| `/admin/chat?sid=xxx` | GET | 会话详情回复页（后端渲染完整历史 + 图片 + 回复表单） |
| `/admin/submit` | POST | 提交人工回复（唤醒请求线程，会话保留） |
| `/admin/close` | POST | 手动关闭会话（唯一删除途径） |
| `/admin/set_mode` | POST | 切换服务模式：`mode=manual`（人工回复）/ `mode=auto`（自动回复） |

### 服务模式（人工回复 / 自动回复）

后台首页统计区下方显示**当前状态**，可一键切换：

- **人工回复**：请求进入会话队列，阻塞等待你在后台手动回复（默认模式）
- **自动回复**：不管客户端请求发过来什么，一律直接回复
  `我暂时不在线，请等待我上线后再使用吧`（不进入人工队列）

### OpenAI 客户端调用示例（文本）

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:1234/v1", api_key="not-needed")
resp = client.chat.completions.create(
    model="any-name",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)
```

### 图文混合（GPT4V）

```json
{
  "model": "humanchatapi",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "描述这张图片"},
        {"type": "image_url", "image_url": {"url": "https://xxx.png"}}
      ]
    }
  ]
}
```

也完整支持 base64 内嵌图片格式。

---

## 项目结构

```
humanchatapi/
├── StartServer.py              # 最终启动文件（导入各模块并启动整个项目）
├── app/
│   ├── __init__.py
│   ├── main.py                 # 标准库 HTTP 服务 + 路由分发（ThreadingHTTPServer）
│   ├── models.py               # 数据模型（dataclass）
│   ├── session_manager.py      # 会话管理（单次持久化，手动关闭才删除）
│   ├── message_filter.py       # 消息清洗规则
│   ├── api_routes.py           # /v1 OpenAI 兼容接口
│   ├── admin_routes.py         # /admin 后台路由（后端渲染 WebUI）
│   ├── webui/
│   │   ├── admin_index.html    # 后台首页模板（占位符）
│   │   ├── admin_chat.html     # 会话回复页模板（占位符）
│   │   └── HumanChatApi.png    # 后台 logo 图片
│   └── utils.py                # 工具函数
├── requirements.txt            # 说明文件（零依赖）
└── README.md                   # 说明文档
```

---

## 并发模型

- `ThreadingHTTPServer`：每个请求一个独立线程
- 对话请求线程创建会话后 `threading.Event.wait()` **阻塞等待**
- 管理员在后台提交回复 → `event.set()` 唤醒对应请求线程 → 返回标准 OpenAI 响应
- `threading.Lock` 保护会话字典，保证并发安全

---

## 注意事项

- 会话数据存于内存，**只有手动关闭或重启服务才消失**
- 外网部署需自行配置内网穿透暴露 `1234` 端口
- V1.0 不实现接口鉴权