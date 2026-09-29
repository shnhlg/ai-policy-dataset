"""Web application for browsing the AI policy dataset."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import threading
import time
import uuid
import webbrowser
from contextlib import contextmanager
from functools import lru_cache
from email.utils import formatdate
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from indexer import DB_PATH, FULLTEXT_PATH, ROOT, build_index, index_is_current
from portable import resolve_raw_file


STATIC = Path(__file__).resolve().parent / "static"
STATS_LOCK = threading.Lock()


def accepts_gzip(header: str) -> bool:
    qualities = {}
    for entry in header.lower().split(','):
        coding, *parameters = entry.strip().split(';')
        quality = 1.0
        for parameter in parameters:
            key, _, value = parameter.strip().partition('=')
            if key == 'q':
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        qualities[coding] = quality
    return qualities.get('gzip', qualities.get('*', 0.0)) > 0


@lru_cache(maxsize=24)
def static_content(path: Path, modified: int, size: int, compressed: bool) -> tuple[bytes, str]:
    body = path.read_bytes()
    if compressed:
        body = gzip.compress(body, compresslevel=5, mtime=0)
    return body, '"' + hashlib.sha256(body).hexdigest() + '"'


def dataset_version() -> tuple[int, int]:
    stat = DB_PATH.stat()
    return stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=2)
def read_body(version: tuple[int, int], offset: int, size: int) -> str:
    with FULLTEXT_PATH.open('rb') as handle:
        handle.seek(offset)
        return str(json.loads(handle.read(size)).get('fulltext', ''))


def byte_range(header: str, size: int) -> tuple[int, int]:
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
    if not match or not any(match.groups()) or size == 0:
        raise ValueError('Invalid range')
    first, last = match.groups()
    if not first:
        count = int(last)
        if count <= 0:
            raise ValueError('Invalid suffix range')
        return max(0, size - count), size - 1
    start, end = int(first), min(int(last), size - 1) if last else size - 1
    if start >= size or start > end:
        raise ValueError('Unsatisfiable range')
    return start, end


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "BAD_REQUEST"):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


@contextmanager
def connect():
    connection = sqlite3.connect(DB_PATH.as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA cache_size=-8192')
    connection.create_function('ai_word', 1, lambda text: bool(re.search(r'(?<![a-z0-9])ai(?![a-z0-9])', text or '', re.I)), deterministic=True)
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
    timeout = 30

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_response(self, code: int, message: str | None = None) -> None:
        self._response_started = True
        self._status = code
        super().send_response(code, message)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def json_response(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode("utf-8")
        compressed = len(body) >= 1024 and accepts_gzip(self.headers.get('Accept-Encoding', ''))
        if compressed:
            body = gzip.compress(body, compresslevel=5, mtime=0)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header('Vary', 'Accept-Encoding')
        if compressed:
            self.send_header('Content-Encoding', 'gzip')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        request_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()
        self._response_started = False
        self._status = 200
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
        except (BrokenPipeError, ConnectionResetError):
            self._status = 499
        except ApiError as exc:
            self.json_response({"code": exc.code, "message": exc.message, "request_id": request_id}, exc.status)
        except Exception as exc:
            print(json.dumps({"level": "error", "request_id": request_id, "error": str(exc)}, ensure_ascii=False), flush=True)
            if not self._response_started:
                self.json_response({"code": "INTERNAL_ERROR", "message": "读取数据时出现异常。", "request_id": request_id}, 500)
        finally:
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            if elapsed > 200 or self._status >= 400:
                print(json.dumps({'event': 'request', 'path': urlparse(self.path).path,
                                  'status': self._status, 'ms': elapsed, 'request_id': request_id}), flush=True)

    @staticmethod
    def record_count() -> int:
        with connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM policies").fetchone()[0]

    def stats(self) -> None:
        with STATS_LOCK:
            result = self.statistics(dataset_version())
        self.json_response(result)

    @staticmethod
    @lru_cache(maxsize=2)
    def statistics(version: tuple[int, int]) -> dict:
        with connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
            countries = connection.execute("SELECT COUNT(DISTINCT country_or_org) FROM policies WHERE country_or_org<>''").fetchone()[0]
            languages = connection.execute("SELECT COUNT(DISTINCT language) FROM policies WHERE language NOT IN ('','und')").fetchone()[0]
            pdf_count = connection.execute("SELECT COUNT(*) FROM policies WHERE raw_is_pdf=1").fetchone()[0]
            raw_count = connection.execute("SELECT COUNT(*) FROM policies WHERE raw_available=1").fetchone()[0]
            non_pdf_count = raw_count - pdf_count
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
        return {
            "total": total, "jurisdictions": countries, "languages": languages,
            "pdf_count": pdf_count, "non_pdf_count": non_pdf_count,
            "raw_available": raw_count, "raw_missing": total - raw_count,
            "facet_scope": "all", "dataset_version": f"{version[0]}-{version[1]}",
            "relevance_counts": relevance_counts,
            "year_min": years[0] or "—", "year_max": years[1] or "—",
            "top_countries": top_countries, "facets": facets, "category_facets": category_facets,
        }

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
                if query.lower() == 'ai':
                    clauses.append("ai_word(p.title_original || ' ' || COALESCE(p.title_zh,'') || ' ' || COALESCE(p.content_summary_original,'') || ' ' || COALESCE(p.issuer,''))")
                else:
                    like = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
                    clauses.append("(p.title_original LIKE ? ESCAPE '\\' OR p.title_zh LIKE ? ESCAPE '\\' OR p.country_or_org LIKE ? ESCAPE '\\' OR p.issuer LIKE ? ESCAPE '\\' OR p.content_summary_original LIKE ? ESCAPE '\\')")
                    values.extend([like] * 5)
        for parameter, column in (("country", "country_or_org"), ("language", "language"), ("policy_type", "policy_type"), ("year", "year")):
            selected = params.get(parameter, [""])[0].strip()[:100]
            if selected:
                clauses.append(f"p.{column}=?")
                values.append(selected)
        file_type = params.get("file_type", [""])[0].strip()
        if file_type not in {"", "pdf", "non_pdf", "missing"}:
            raise ApiError("文件类型筛选值无效。")
        if file_type == "pdf":
            clauses.append("p.raw_is_pdf=1")
        elif file_type == "non_pdf":
            clauses.append("p.raw_available=1 AND p.raw_is_pdf=0")
        elif file_type == 'missing':
            clauses.append("p.raw_available=0")
        body_status = params.get('body_status', [''])[0].strip()
        if body_status not in {'', 'extracted', 'non_body', 'mixed_source', 'ocr_required'}:
            raise ApiError('正文状态筛选值无效。')
        if body_status:
            clauses.append('p.content_extraction_status=?')
            values.append(body_status)
        relevance = params.get("relevance", ["all"])[0].strip()
        if relevance not in {"all", "relevant", "high", "ai_related", "review", "unrelated"}:
            raise ApiError("AI 相关性筛选值无效。")
        if relevance == "relevant":
            clauses.append("p.is_relevant=1")
        elif relevance == "high":
            clauses.append("p.is_relevant=1")
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
                    p.fulltext_char_count,p.content_extraction_status,p.official_url,p.official_url_final,
                    p.relevance_level,p.relevance_score,p.relevance_reason,
                    p.ai_review_decision,p.ai_review_reason,p.ai_title_probability,p.ai_content_probability,
                    p.raw_available,p.raw_is_pdf,p.summary_status
                    FROM policies p {join} {where}
                    ORDER BY p.date_missing,p.published_date DESC,p.id
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
            raw = resolve_raw_file(payload.get('raw_file') or '')
            payload['raw_available'] = raw is not None
            payload['raw_is_pdf'] = raw is not None and raw.suffix.lower() == '.pdf'
            payload['body_available'] = payload['fulltext_char_count'] > 0 and payload['content_extraction_status'] == 'extracted'
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
        text = read_body(dataset_version(), row["body_offset"], row["body_bytes"])
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
            raise ApiError("尚未收录此原件，可尝试官方来源链接。", 404, "RAW_NOT_FOUND")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        stat = path.stat()
        etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        modified = formatdate(stat.st_mtime, usegmt=True)
        if self.headers.get('If-None-Match') == etag:
            self.send_response(304)
            self.send_header('ETag', etag)
            self.end_headers()
            return
        start, end = 0, stat.st_size - 1
        range_header = self.headers.get('Range')
        if self.headers.get('If-Range') not in (None, etag, modified):
            range_header = None
        if range_header:
            try:
                start, end = byte_range(range_header, stat.st_size)
            except ValueError:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{stat.st_size}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
        self.send_response(206 if range_header else HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(max(0, end - start + 1)))
        self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(path.name)}")
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('ETag', etag)
        self.send_header('Last-Modified', modified)
        self.send_header('Cache-Control', 'private, max-age=0, must-revalidate')
        if range_header:
            self.send_header('Content-Range', f'bytes {start}-{end}/{stat.st_size}')
        if path.suffix.lower() in {".html", ".htm"}:
            self.send_header("Content-Security-Policy", "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:")
        self.end_headers()
        if self.command == 'HEAD':
            return
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining > 0 and (chunk := handle.read(min(1024 * 1024, remaining))):
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def static_file(self, route: str) -> None:
        relative = "index.html" if route in ("", "/") else unquote(route.lstrip("/"))
        path = (STATIC / relative).resolve()
        if STATIC.resolve() not in path.parents or not path.is_file():
            raise ApiError("页面不存在。", 404, "NOT_FOUND")
        stat = path.stat()
        compressed = stat.st_size >= 1024 and path.suffix in {'.html', '.css', '.js', '.svg'} and accepts_gzip(self.headers.get('Accept-Encoding', ''))
        body, etag = static_content(path, stat.st_mtime_ns, stat.st_size, compressed)
        validators = [tag.strip().removeprefix('W/') for tag in self.headers.get('If-None-Match', '').split(',')]
        not_modified = etag in validators or '*' in validators
        self.send_response(304 if not_modified else HTTPStatus.OK)
        self.send_header('ETag', etag)
        self.send_header('Vary', 'Accept-Encoding')
        self.send_header('Cache-Control', 'public, no-cache')
        if not_modified:
            self.end_headers()
            return
        self.send_header("Content-Type", (mimetypes.guess_type(path.name)[0] or "application/octet-stream") + ("; charset=utf-8" if path.suffix in {".html", ".css", ".js"} else ""))
        self.send_header("Content-Length", str(len(body)))
        if compressed:
            self.send_header('Content-Encoding', 'gzip')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 政策数据集检索窗口")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not index_is_current():
        if os.environ.get('AI_POLICY_RUNTIME'):
            raise SystemExit('运行版本与代码环境不匹配，请重新准备版本或使用匹配的镜像；未修改已发布数据。')
        print("首次启动或数据有更新，正在建立检索索引……", flush=True)
        build_index()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
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
