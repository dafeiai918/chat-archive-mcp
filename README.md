# chat-archive-mcp · 会话归档检索 MCP

**让 AI 直接说：「找到了，9月14日那次 RAG 方案讨论里你提过这个。」**

零依赖 · 单文件 · stdio MCP 服务器 · 全本地检索 · 中文

---

## 它让 AI 能做什么

> 「我上次跟 AI 聊的那个方案在哪？」
> → AI 调用 `search_chats`，全文检索你的历史对话

> 「我都归档了哪些对话？」
> → AI 调用 `list_sessions`

> 「把那次讨论的完整内容调出来」
> → AI 调用 `get_session`

---

## 提供的工具

| 工具 | 作用 |
|---|---|
| `search_chats` | 全文搜索（中文子串匹配，FTS5 + LIKE 兜底） |
| `list_sessions` | 列出归档会话 |
| `get_session` | 读取完整对话 |
| `archive_stats` | 归档统计 |

---

## 安装

```json
{
  "mcpServers": {
    "chat-archive-mcp": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/dafeiai918/chat-archive-mcp", "chat-archive-mcp"]
    }
  }
}
```

零第三方依赖，Python 3.9+。数据来自 [chat-archive](https://github.com/dafeiai918/chat-archive) 的数据库（`~/.chat-archive/archive.db`）。

---

## 数据从哪来

先用命令行版导入会话，MCP 才能搜：

```bash
# 导入 ChatGPT / Claude 官方导出
python chat_archive.py import -f conversations.json
```

导入后，AI 就能通过本 MCP 检索。

---

## 使用场景

| 场景 | 对 AI 说 |
|---|---|
| 找回旧结论 | 「我之前问过向量数据库选型，结论是什么」 |
| 复用方案 | 「上次那个部署步骤，找出来」 |
| 盘点归档 | 「我一共归档了多少对话」 |
| 读全文 | 「把那个会话完整读一遍」 |

---

## 隐私

- 数据全在本机 `~/.chat-archive/`
- 检索在本地 SQLite 完成，**不上传任何内容**
- 只读取归档库，不修改

---

## 相关项目

| 项目 | 用途 |
|---|---|
| [chat-archive](https://github.com/dafeiai918/chat-archive) | 命令行版：导入 ChatGPT/Claude 导出并建索引 |
| [prompt-vault-mcp](https://github.com/dafeiai918/prompt-vault-mcp) | 提示词库 MCP |
| [token-meter-mcp](https://github.com/dafeiai918/token-meter-mcp) | 用量成本分析 MCP |

---

## License

MIT
