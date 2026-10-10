# -*- coding: utf-8 -*-
"""chat-archive-mcp 测试：协议 + 检索，用临时 SQLite 库"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chat_archive_mcp as ca  # noqa: E402

SCHEMA = """
CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, fingerprint TEXT UNIQUE,
  source TEXT, title TEXT, created REAL, imported REAL, msg_count INTEGER);
CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER,
  role TEXT, content TEXT, ts REAL);
CREATE VIRTUAL TABLE messages_fts USING fts5(content, content='messages',
  content_rowid='id', tokenize='trigram');
CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content); END;
"""


class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.server = ca.MCPServer("t", "1.0", ca.TOOLS)
        self.server._send = lambda m: self.sent.append(m)

    def _call(self, method, **kw):
        msg = {"jsonrpc": "2.0", "id": 1, "method": method}
        if kw:
            msg["params"] = kw
        self.server.handle(msg)
        return self.sent[-1]

    def test_initialize(self):
        self.assertEqual(self._call("initialize")["result"]["serverInfo"]["name"], "t")

    def test_tools_list(self):
        names = [t["name"] for t in self._call("tools/list")["result"]["tools"]]
        self.assertEqual(sorted(names),
                         ["archive_stats", "get_session", "list_sessions", "search_chats"])

    def test_unknown_tool(self):
        self.assertEqual(self._call("tools/call", name="x", arguments={})["error"]["code"], -32602)

    def test_missing_db_becomes_iserror(self):
        out = self._call("tools/call", name="archive_stats", arguments={})
        self.assertTrue(out["result"]["isError"])
        self.assertIn("chat-archive", out["result"]["content"][0]["text"])


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = ca.DB_PATH
        ca.DB_PATH = Path(self.tmp.name) / "archive.db"
        conn = sqlite3.connect(str(ca.DB_PATH))
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO sessions (fingerprint, source, title, created, msg_count) "
                     "VALUES ('f1','chatgpt','向量数据库选型',1700000000,2)")
        conn.execute("INSERT INTO messages (session_id, role, content, ts) VALUES "
                     "(1,'user','我想用向量数据库存文档切片，用哪个好？',1700000000)")
        conn.execute("INSERT INTO messages (session_id, role, content, ts) VALUES "
                     "(1,'assistant','小规模推荐 Chroma，大规模用 Milvus。',1700000001)")
        conn.commit()
        conn.close()

    def tearDown(self):
        ca.DB_PATH = self._orig
        self.tmp.cleanup()

    def test_search_hits(self):
        text = ca.tool_search_chats({"keyword": "向量数据库"})
        self.assertIn("向量数据库选型", text)
        self.assertIn("【", text)

    def test_search_miss(self):
        self.assertIn("没有匹配", ca.tool_search_chats({"keyword": "完全不存在zzz"}))

    def test_search_requires_keyword(self):
        self.assertIn("需要 keyword", ca.tool_search_chats({}))

    def test_list_sessions(self):
        text = ca.tool_list_sessions({})
        self.assertIn("向量数据库选型", text)
        self.assertIn("2 条", text)

    def test_get_session(self):
        text = ca.tool_get_session({"id": 1})
        self.assertIn("Chroma", text)
        self.assertIn("【user】", text)

    def test_get_session_bad_id(self):
        self.assertIn("没有找到" if False else "未找到", ca.tool_get_session({"id": 999}))
        self.assertIn("必须是数字", ca.tool_get_session({"id": "abc"}))
        self.assertIn("需要会话 id", ca.tool_get_session({}))

    def test_stats(self):
        text = ca.tool_archive_stats({})
        self.assertIn("会话：1", text)
        self.assertIn("消息：2", text)

    def test_fmt_ts(self):
        self.assertEqual(ca.fmt_ts(0), "-")
        self.assertIn("20", ca.fmt_ts(1700000000))


if __name__ == "__main__":
    unittest.main(verbosity=2)
