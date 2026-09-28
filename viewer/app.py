"""Local web application for browsing the AI policy dataset."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sqlite3
import threading
import uuid
import webbrowser
from contextlib import contextmanager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from indexer import DB_PATH, FULLTEXT_PATH, ROOT, build_index, index_is_current
from portable import resolve_raw_file


STATIC = Path(__file__).resolve().parent / "static"


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "BAD_REQUEST"):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


@contextmanager
def connect():
    connection = sqlite3.connect(DB_PATH.as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def integer_param(params: dict[str, list[str]], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = params.get(name, [str(default)])[0]
    try:
        result = int(raw)
    except ValueError as exc:
        raise ApiError(f"参数 {name} 必须是整数。") from exc
    if not minimum <= result <= maximum:
        raise ApiError(f"参数 {name} 必须在 {minimum} 到 {maximum} 之间。")
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "AIPolicyViewer/1.0"

    def log_message(self, format: str, *args: object) -> None:
        return

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def json_response(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        request_id = uuid.uuid4().hex[:12]
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self.json_response({"status": "ok", "records": self.record_count()})
            elif parsed.path == "/api/stats":
                self.stats()
            elif parsed.path == "/api/search":
                self.search(parse_qs(parsed.query, keep_blank_values=True))
            elif parsed.path.startswith("/api/policies/"):
                self.policy_route(parsed.path, parse_qs(parsed.query))
            else:
                self.static_file(parsed.path)
        except ApiError as exc:
            self.json_response({"code": exc.code, "message": exc.message, "request_id": request_id}, exc.status)
        except Exception as exc:
            print(json.dumps({"level": "error", "request_id": request_id, "error": str(exc)}, ensure_ascii=False), flush=True)
            self.json_response({"code": "INTERNAL_ERROR", "message": "读取数据时出现异常。", "request_id": request_id}, 500)

    @staticmethod
    def record_count() -> int:
        with connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM policies").fetchone()[0]

    def stats(self) -> None:
        with connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
            countries = connection.execute("SELECT COUNT(DISTINCT country_or_org) FROM policies WHERE country_or_org<>''").fetchone()[0]
            languages = connection.execute("SELECT COUNT(DISTINCT language) FROM policies WHERE language<>''").fetchone()[0]
            pdf_count = connection.execute("SELECT COUNT(*) FROM policies WHERE LOWER(raw_file) LIKE '%.pdf'").fetchone()[0]
            relevance_counts = dict(connection.execute("SELECT relevance_level,COUNT(*) FROM policies GROUP BY relevance_level"))
            years = connection.execute("SELECT MIN(year),MAX(year) FROM policies WHERE year<>''").fetchone()
            top_countries = [dict(row) for row in connection.execute(
                "SELECT country_or_org AS name,COUNT(*) AS count FROM policies WHERE country_or_org<>'' GROUP BY country_or_org ORDER BY count DESC LIMIT 12"
            )]
            facets = {}
            for field in ("country_or_org", "language", "policy_type", "year"):
                facets[field] = [dict(row) for row in connection.execute(
                    f"SELECT {field} AS value,COUNT(*) AS count FROM policies WHERE {field}<>'' GROUP BY {field} ORDER BY count DESC,{field} LIMIT 300"
                )]
            category_facets = {}
            for dimension in ("政策主题", "政策手段", "应用领域"):
                category_facets[dimension] = [dict(row) for row in connection.execute(
                    """SELECT c.name AS value,COUNT(*) AS count
                       FROM categories c JOIN policy_categories pc ON pc.category_id=c.id
                       WHERE c.dimension=? GROUP BY c.id ORDER BY c.sort_order""",
                    (dimension,),
                )]
        self.json_response({
            "total": total, "jurisdictions": countries, "languages": languages,
            "pdf_count": pdf_count, "non_pdf_count": total - pdf_count,
            "relevance_counts": relevance_counts,
            "year_min": years[0] or "—", "year_max": years[1] or "—",
            "top_countries": top_countries, "facets": facets, "category_facets": category_facets,
        })

    def search(self, params: dict[str, list[str]]) -> None:
        query = params.get("q", [""])[0].strip()[:200]
        page = integer_param(params, "page", 1, 1, 10000)
        page_size = integer_param(params, "page_size", 20, 5, 50)
        clauses: list[str] = []
        values: list[object] = []
        join = ""
        if query:
            if len(query) >= 3:
                join = " JOIN policy_fts f ON f.rowid=p.id "
                clauses.append("f.search_text MATCH ?")
                values.append('"' + query.replace('"', '""') + '"')
            else:
                like = f"%{query}%"
                clauses.append("(p.title_original LIKE ? OR p.title_zh LIKE ? OR p.country_or_org LIKE ? OR p.issuer LIKE ? OR p.content_summary_original LIKE ?)")
                values.extend([like] * 5)
        for parameter, column in (("country", "country_or_org"), ("language", "language"), ("policy_type", "policy_type"), ("year", "year")):
            selected = params.get(parameter, [""])[0].strip()[:100]
            if selected:
                clauses.append(f"p.{column}=?")
                values.append(selected)
        file_type = params.get("file_type", [""])[0].strip()
        if file_type not in {"", "pdf", "non_pdf"}:
            raise ApiError("文件类型筛选值无效。")
        if file_type == "pdf":
            clauses.append("LOWER(p.raw_file) LIKE '%.pdf'")
        elif file_type == "non_pdf":
            clauses.append("LOWER(p.raw_file) NOT LIKE '%.pdf'")
        relevance = params.get("relevance", ["all"])[0].strip()
        if relevance not in {"all", "relevant", "high", "ai_related", "review", "unrelated"}:
            raise ApiError("AI 相关性筛选值无效。")
        if relevance == "relevant":
            clauses.append("p.relevance_level IN ('明确相关','AI复核相关')")
        elif relevance == "high":
            clauses.append("p.relevance_level IN ('明确相关','AI复核相关')")
        elif relevance == "ai_related":
            clauses.append("p.relevance_level='AI复核相关'")
        elif relevance == "review":
            clauses.append("p.relevance_level='待人工复核'")
        elif relevance == "unrelated":
            clauses.append("p.relevance_level='AI复核无关'")
        for parameter, dimension in (("topic_category", "政策主题"), ("instrument_category", "政策手段"), ("sector_category", "应用领域")):
            selected = params.get(parameter, [""])[0].strip()[:100]
            if selected:
                clauses.append("""EXISTS (
                    SELECT 1 FROM policy_categories pc JOIN categories c ON c.id=pc.category_id
                    WHERE pc.policy_row_id=p.id AND c.dimension=? AND c.name=?
                )""")
                values.extend([dimension, selected])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with connect() as connection:
            total = connection.execute(f"SELECT COUNT(*) FROM policies p {join} {where}", values).fetchone()[0]
            rows = connection.execute(
                f"""SELECT p.policy_id,p.title_original,p.title_zh,p.country_or_org,p.issuer,p.policy_type,
                    p.legal_status,p.published_date,p.language,p.topics,p.content_summary_original,
                    p.fulltext_char_count,p.official_url,p.official_url_final,
                    p.relevance_level,p.relevance_score,p.relevance_reason,
                    p.ai_review_decision,p.ai_review_reason,p.ai_title_probability,p.ai_content_probability
                    FROM policies p {join} {where}
                    ORDER BY CASE WHEN p.published_date='' THEN 1 ELSE 0 END,p.published_date DESC,p.id
                    LIMIT ? OFFSET ?""",
                values + [page_size, (page - 1) * page_size],
            ).fetchall()
        self.json_response({"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size})

    def policy_route(self, path: str, params: dict[str, list[str]]) -> None:
        parts = path.strip("/").split("/")
        if len(parts) < 3:
            raise ApiError("缺少政策编号。", 404, "NOT_FOUND")
        policy_id = unquote(parts[2])[:200]
        if len(parts) == 4 and parts[3] == "body":
            self.body(policy_id, params)
        elif len(parts) == 4 and parts[3] == "raw":
            self.raw_file(policy_id)
        elif len(parts) == 3:
            with connect() as connection:
                row = connection.execute("SELECT * FROM policies WHERE policy_id=?", (policy_id,)).fetchone()
                categories = connection.execute(
                    """SELECT c.dimension,c.name FROM categories c
                       JOIN policy_categories pc ON pc.category_id=c.id
                       JOIN policies p ON p.id=pc.policy_row_id
                       WHERE p.policy_id=? ORDER BY c.dimension,c.sort_order""",
                    (policy_id,),
                ).fetchall()
            if row is None:
                raise ApiError("没有找到这条政策。", 404, "NOT_FOUND")
            payload = dict(row)
            payload["classifications"] = {}
            for category in categories:
                payload["classifications"].setdefault(category["dimension"], []).append(category["name"])
            self.json_response(payload)
        else:
            raise ApiError("接口不存在。", 404, "NOT_FOUND")

    def body(self, policy_id: str, params: dict[str, list[str]]) -> None:
        offset_chars = integer_param(params, "offset", 0, 0, 100_000_000)
        limit = integer_param(params, "limit", 30_000, 1000, 100_000)
        with connect() as connection:
            row = connection.execute("SELECT body_offset,body_bytes FROM policies WHERE policy_id=?", (policy_id,)).fetchone()
        if row is None or row["body_offset"] is None:
            raise ApiError("这条政策没有可读取的正文。", 404, "BODY_NOT_FOUND")
        with FULLTEXT_PATH.open("rb") as handle:
            handle.seek(row["body_offset"])
            record = json.loads(handle.read(row["body_bytes"]))
        text = str(record.get("fulltext", ""))
        self.json_response({
            "text": text[offset_chars:offset_chars + limit], "offset": offset_chars,
            "next_offset": min(len(text), offset_chars + limit), "total_chars": len(text),
            "has_more": offset_chars + limit < len(text),
        })

    def raw_file(self, policy_id: str) -> None:
        with connect() as connection:
            row = connection.execute("SELECT raw_file FROM policies WHERE policy_id=?", (policy_id,)).fetchone()
        if row is None or not row["raw_file"]:
            raise ApiError("没有对应的原始文件。", 404, "RAW_NOT_FOUND")
        path = resolve_raw_file(row["raw_file"])
        if path is None:
            raise ApiError("原始附件尚未连接。请运行 python scripts/configure_raw.py，选择旧数据包的 data/raw 目录；政策正文仍可正常阅读。", 404, "RAW_NOT_FOUND")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{path.name}")
        if path.suffix.lower() in {".html", ".htm"}:
            self.send_header("Content-Security-Policy", "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:")
        self.end_headers()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                self.wfile.write(chunk)

    def static_file(self, route: str) -> None:
        relative = "index.html" if route in ("", "/") else unquote(route.lstrip("/"))
        path = (STATIC / relative).resolve()
        if STATIC.resolve() not in path.parents or not path.is_file():
            raise ApiError("页面不存在。", 404, "NOT_FOUND")
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", (mimetypes.guess_type(path.name)[0] or "application/octet-stream") + ("; charset=utf-8" if path.suffix in {".html", ".css", ".js"} else ""))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 政策数据集检索窗口")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not index_is_current():
        print("首次启动或数据有更新，正在建立检索索引……", flush=True)
        build_index()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"AI 政策检索窗口已启动：{url}", flush=True)
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
