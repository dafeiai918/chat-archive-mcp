#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chat-archive-mcp · 会话归档检索 MCP
让 AI 直接搜你的历史对话：「上次说的那个方案在哪」
零依赖 stdio MCP 服务器（读 chat-archive 的数据库）
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

__version__ = "1.0.0"
PROTOCOL_VERSION = "2025-06-18"
DB_PATH = Path.home() / ".chat-archive" / "archive.db"


# ================= MCP 内核 =================

class MCPServer:
    def __init__(self, name: str, version: str, tools: list):
        self.name, self.version, self.tools = name, version, tools

    def _send(self, msg: dict) -> None:
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def _result(self, id_, result) -> None:
        self._send({"jsonrpc": "2.0", "id": id_, "result": result})

    def _error(self, id_, code: int, message: str) -> None:
        self._send({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})

    def handle(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        method, id_ = msg.get("method"), msg.get("id")
        if method == "initialize":
            self._result(id_, {"protocolVersion": PROTOCOL_VERSION,
                               "capabilities": {"tools": {"listChanged": False}},
                               "serverInfo": {"name": self.name, "version": self.version}})
        elif method in ("notifications/initialized", "initialized", "notifications/cancelled"):
            return
        elif method == "ping":
            self._result(id_, {})
        elif method == "tools/list":
            self._result(id_, {"tools": [
                {"name": t["name"], "description": t["description"],
                 "inputSchema": t.get("inputSchema") or {"type": "object", "properties": {}}}
                for t in self.tools]})
        elif method == "tools/call":
            params = msg.get("params") or {}
            tool = next((t for t in self.tools if t["name"] == params.get("name")), None)
            if tool is None:
                self._error(id_, -32602, f"未知工具: {params.get('name')}")
                return
            try:
                out = tool["handler"](params.get("arguments") or {})
                self._result(id_, {"content": [{"type": "text", "text": str(out)}], "isError": False})
            except Exception as exc:
                self._result(id_, {"content": [{"type": "text",
                                                "text": f"错误: {type(exc).__name__}: {exc}"}],
                                   "isError": True})
        elif id_ is not None:
            self._error(id_, -32601, f"不支持的方法: {method}")

    def serve(self) -> None:
        for raw in sys.stdin:
            raw = raw.strip()
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            for item in (msg if isinstance(msg, list) else [msg]):
                self.handle(item)


# ================= 数据层 =================

def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"归档数据库不存在：{DB_PATH}\n"
            "先用 chat-archive 导入会话：chat-archive import -f conversations.json")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def has_table(conn: sqlite3.Connection, name: str) -> bool:
    try:
        conn.execute(f"SELECT 1 FROM {name} LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def fts_search(conn: sqlite3.Connection, keyword: str, limit: int) -> list[dict]:
    if has_table(conn, "messages_fts"):
        try:
            rows = conn.execute("""
                SELECT m.session_id AS sid, s.title AS title, m.role AS role,
                       snippet(messages_fts, 0, '<<', '>>', '…', 40) AS snip
                FROM messages_fts f
                JOIN messages m ON m.id = f.rowid
                JOIN sessions s ON s.id = m.session_id
                WHERE messages_fts MATCH ? ORDER BY rank LIMIT ?
            """, (f'"{keyword.replace(chr(34), chr(34) * 2)}"', limit)).fetchall()
            if rows:
                return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            pass
    rows = conn.execute("""
        SELECT m.session_id AS sid, s.title AS title, m.role AS role, m.content AS content
        FROM messages m JOIN sessions s ON s.id = m.session_id
        WHERE m.content LIKE ? LIMIT ?
    """, (f"%{keyword}%", limit)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        content = item.pop("content") or ""
        idx = content.find(keyword)
        start = max(0, idx - 20)
        item["snip"] = (("…" if start else "") + content[start:start + 40]
                        + ("…" if start + 40 < len(content) else ""))
        item["snip"] = item["snip"].replace(keyword, f"<<{keyword}>>", 1)
        out.append(item)
    return out


def fmt_ts(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M") if ts else "-"
    except Exception:
        return "-"


# ================= 工具 =================

def tool_search_chats(args: dict) -> str:
    keyword = (args.get("keyword") or "").strip()
    if not keyword:
        return "需要 keyword。"
    limit = int(args.get("limit") or 15)
    conn = connect()
    rows = fts_search(conn, keyword, limit)
    if not rows:
        conn.close()
        return f"没有匹配「{keyword}」的内容。"
    lines = [f"搜索「{keyword}」命中 {len(rows)} 条：", ""]
    for row in rows:
        snip = (row.get("snip") or "").replace("<<", "【").replace(">>", "】")
        lines.append(f"[会话 {row['sid']}] {row['title']}  ({row['role']})")
        lines.append(f"  {snip}")
        lines.append("")
    lines.append("用 get_session 可以读某个会话的完整内容。")
    conn.close()
    return "\n".join(lines)


def tool_list_sessions(args: dict) -> str:
    limit = int(args.get("limit") or 20)
    conn = connect()
    rows = conn.execute("""
        SELECT id, source, title, created, msg_count FROM sessions
        ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    if not rows:
        conn.close()
        return "归档还是空的。用 chat-archive 导入会话文件。"
    lines = [f"最近 {len(rows)} 个归档会话：", ""]
    for row in rows:
        lines.append(f"- [{row['id']}] {row['title']}  "
                     f"({row['msg_count']} 条 · {row['source']} · {fmt_ts(row['created'])})")
    conn.close()
    return "\n".join(lines)


def tool_get_session(args: dict) -> str:
    raw_id = args.get("id")
    if raw_id in (None, ""):
        return "需要会话 id（用 list_sessions 查）。"
    try:
        sid = int(raw_id)
    except (TypeError, ValueError):
        return f"id 必须是数字，收到：{raw_id}"
    conn = connect()
    session = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not session:
        conn.close()
        return f"未找到会话 {sid}。"
    lines = [f"【{session['title']}】  来源 {session['source']} · "
             f"{session['msg_count']} 条 · {fmt_ts(session['created'])}", ""]
    for row in conn.execute("SELECT role, content FROM messages WHERE session_id=? ORDER BY id",
                            (sid,)):
        content = row["content"] or ""
        if len(content) > 1500:
            content = content[:1500] + f"\n…（截断，原长 {len(row['content'])} 字）"
        lines.append(f"【{row['role']}】")
        lines.append(content)
        lines.append("")
    conn.close()
    return "\n".join(lines)


def tool_archive_stats(args: dict) -> str:
    conn = connect()
    sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    chars = conn.execute("SELECT COALESCE(SUM(LENGTH(content)),0) FROM messages").fetchone()[0]
    by_source = conn.execute(
        "SELECT source, COUNT(*) FROM sessions GROUP BY source ORDER BY 2 DESC").fetchall()
    lines = [f"归档统计",
             f"- 会话：{sessions}",
             f"- 消息：{messages}",
             f"- 字符：{chars:,}（约 {chars / 10000:.0f} 万字）", ""]
    if by_source:
        lines.append("按来源：")
        for row in by_source:
            lines.append(f"- {row[0] or '(未知)'}：{row[1]} 个会话")
    lines.append(f"\n数据库：{DB_PATH}")
    conn.close()
    return "\n".join(lines)


TOOLS = [
    {"name": "search_chats",
     "description": "全文搜索历史对话内容。用户问「我上次跟AI聊的那个方案在哪」"
                    "「搜一下我之前问过的」时使用。",
     "inputSchema": {"type": "object", "properties": {
         "keyword": {"type": "string", "description": "搜索关键词"},
         "limit": {"type": "integer", "description": "最多返回条数，默认15"}},
         "required": ["keyword"]},
     "handler": tool_search_chats},
    {"name": "list_sessions",
     "description": "列出已归档的会话。用户问「我归档了哪些对话」时使用。",
     "inputSchema": {"type": "object", "properties": {
         "limit": {"type": "integer", "description": "默认20"}}},
     "handler": tool_list_sessions},
    {"name": "get_session",
     "description": "读取某个归档会话的完整对话内容。",
     "inputSchema": {"type": "object", "properties": {
         "id": {"type": "integer", "description": "会话 id"}},
         "required": ["id"]},
     "handler": tool_get_session},
    {"name": "archive_stats",
     "description": "归档统计：会话数、消息数、字数、来源分布。",
     "inputSchema": {"type": "object", "properties": {}},
     "handler": tool_archive_stats},
]


def main() -> int:
    if os.name == "nt":
        try:
            sys.stdin.reconfigure(encoding="utf-8")
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    MCPServer("chat-archive-mcp", __version__, TOOLS).serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
