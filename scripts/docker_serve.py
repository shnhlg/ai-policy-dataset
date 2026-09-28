"""Docker 入口：在容器内 0.0.0.0 上启动 AI 政策检索窗口。"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 政策数据集检索窗口（容器版）")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    from prepare_runtime import prepare
    if prepare() is not None:
        # Indexer imported during staging must not retain the temporary directory.
        os.execv(sys.executable, [sys.executable, str(ROOT / 'viewer' / 'app.py'),
                                 '--host', args.host, '--port', str(args.port), '--no-browser'])

    if sys.version_info < (3, 11):
        raise SystemExit("需要 Python 3.11+")
    with sqlite3.connect(":memory:") as db:
        try:
            db.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='trigram')")
        except sqlite3.Error as exc:
            raise SystemExit("SQLite 需要 FTS5 trigram 支持") from exc

    for name in ("data/processed/ai_policies_content_master.csv",
                 "data/processed/policy_fulltexts.jsonl", "viewer/static/index.html"):
        if not (ROOT / name).is_file():
            raise SystemExit(f"缺少文件：{name}")

    sys.path.insert(0, str(ROOT / "viewer"))
    from indexer import build_index, index_is_current
    if not index_is_current():
        print("索引不是最新，正在重建……", flush=True)
        build_index()

    from http.server import ThreadingHTTPServer
    from app import Handler
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"AI 政策检索窗口已启动：http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
