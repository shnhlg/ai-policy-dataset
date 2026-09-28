"""Build the local SQLite search index for the AI policy viewer."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from pathlib import Path

from taxonomy import VERSION as TAXONOMY_VERSION, category_rows, classify
from relevance import VERSION as RELEVANCE_VERSION, evaluate
from translation_quality import VERSION as TRANSLATION_REVIEW_VERSION, polish
from finalize_ai_review import VERSION as AI_REVIEW_VERSION, finalized_reviews
from portable import resolve_raw_file
from quality import VERSION as QUALITY_VERSION, clean_summary, country, language


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = Path(os.environ.get("AI_POLICY_DATA_DIR", ROOT / "data" / "processed"))
CSV_PATH = PROCESSED / "ai_policies_content_master.csv"
FULLTEXT_PATH = PROCESSED / "policy_fulltexts.jsonl"
DB_PATH = Path(os.environ.get("AI_POLICY_DB", Path(__file__).resolve().parent / "policy_search.db"))
TEMP_DB = DB_PATH.with_suffix(".building.db")
TRANSLATIONS_PATH = Path(__file__).resolve().parent / "title_translations.jsonl"
AI_REVIEW_PATH = Path(__file__).resolve().parent / "ai_review_results.jsonl"
INDEXED_BODY_CHARS = 0
SCHEMA_VERSION = "2026-09-28-1"


FIELDS = [
    "policy_id", "title_original", "country_or_org", "jurisdiction_level",
    "issuer", "policy_type", "legal_status", "published_date", "language",
    "topics", "official_url", "official_url_final", "raw_file",
    "content_summary_original", "policy_objectives", "policy_measures",
    "regulatory_requirements", "target_entities", "sectors_extracted",
    "technologies_extracted", "content_extraction_status",
    "content_extraction_error", "fulltext_char_count",
]


def value(row: dict[str, str], name: str) -> str:
    return (row.get(name) or "").strip()


def load_title_translations() -> dict[str, str]:
    translations: dict[str, str] = {}
    if TRANSLATIONS_PATH.exists():
        with TRANSLATIONS_PATH.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    translations[record["title_original"]] = polish(record["title_original"], record["title_zh"])
    return translations


def build_index() -> None:
    if not CSV_PATH.exists() or not FULLTEXT_PATH.exists():
        raise FileNotFoundError("未找到正文主库或完整原文库。")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMP_DB.unlink(missing_ok=True)
    connection = sqlite3.connect(TEMP_DB)
    try:
        connection.executescript("""
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=MEMORY;
            CREATE TABLE policies (
                id INTEGER PRIMARY KEY,
                policy_id TEXT NOT NULL UNIQUE,
                title_original TEXT NOT NULL,
                title_zh TEXT,
                country_or_org TEXT,
                jurisdiction_level TEXT,
                issuer TEXT,
                policy_type TEXT,
                legal_status TEXT,
                published_date TEXT,
                year TEXT,
                language TEXT,
                topics TEXT,
                official_url TEXT,
                official_url_final TEXT,
                raw_file TEXT,
                content_summary_original TEXT,
                policy_objectives TEXT,
                policy_measures TEXT,
                regulatory_requirements TEXT,
                target_entities TEXT,
                sectors_extracted TEXT,
                technologies_extracted TEXT,
                content_extraction_status TEXT,
                content_extraction_error TEXT,
                fulltext_char_count INTEGER DEFAULT 0,
                relevance_level TEXT NOT NULL,
                relevance_score INTEGER NOT NULL,
                relevance_reason TEXT NOT NULL,
                ai_review_decision TEXT,
                ai_review_reason TEXT,
                ai_title_probability REAL,
                ai_content_probability REAL,
                ai_review_model TEXT,
                ai_review_version TEXT,
                body_offset INTEGER,
                body_bytes INTEGER,
                raw_available INTEGER NOT NULL DEFAULT 0,
                raw_is_pdf INTEGER NOT NULL DEFAULT 0,
                summary_status TEXT,
                summary_source TEXT,
                country_original TEXT,
                language_original TEXT,
                is_relevant INTEGER NOT NULL DEFAULT 0,
                date_missing INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX idx_country ON policies(country_or_org);
            CREATE INDEX idx_year ON policies(year);
            CREATE INDEX idx_language ON policies(language);
            CREATE INDEX idx_policy_type ON policies(policy_type);
            CREATE INDEX idx_default_order ON policies(is_relevant,date_missing,published_date DESC,id);
            CREATE INDEX idx_date_order ON policies(date_missing,published_date DESC,id);
            CREATE INDEX idx_relevance ON policies(relevance_level);
            CREATE INDEX idx_raw_pdf ON policies(raw_is_pdf);
            CREATE VIRTUAL TABLE policy_fts USING fts5(
                search_text, tokenize='trigram case_sensitive 0'
            );
            CREATE TABLE categories (
                id INTEGER PRIMARY KEY,
                dimension TEXT NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                UNIQUE(dimension,name)
            );
            CREATE TABLE policy_categories (
                policy_row_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                PRIMARY KEY(policy_row_id,category_id)
            );
            CREATE INDEX idx_policy_categories_category ON policy_categories(category_id,policy_row_id);
            CREATE TABLE index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        connection.executemany(
            "INSERT INTO categories(dimension,name,sort_order) VALUES (?,?,?)",
            category_rows(),
        )
        category_ids = {
            (row[0], row[1]): row[2]
            for row in connection.execute("SELECT dimension,name,id FROM categories")
        }
        search_parts: dict[str, str] = {}
        id_by_policy: dict[str, int] = {}
        title_translations = load_title_translations()
        ai_reviews = finalized_reviews()
        with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for number, row in enumerate(reader, start=1):
                policy_id = value(row, "policy_id")
                values = [value(row, field) for field in FIELDS]
                title_zh = title_translations.get(value(row, "title_original"), "")
                date = value(row, "published_date")
                year = date[:4] if len(date) >= 4 and date[:4].isdigit() else ""
                relevance_level, relevance_score, relevance_reason = evaluate(
                    value(row, "title_original"), value(row, "topics"),
                    value(row, "content_summary_original"),
                    "\n".join([
                        value(row, "policy_objectives"), value(row, "policy_measures"),
                        value(row, "regulatory_requirements"), value(row, "target_entities"),
                    ]),
                )
                ai_review = ai_reviews.get(policy_id)
                if relevance_level == "明确相关":
                    effective_level = "明确相关"
                elif ai_review:
                    effective_level = ai_review["ai_review_decision"]
                else:
                    effective_level = "待人工复核"
                connection.execute(
                    """INSERT INTO policies (
                        policy_id,title_original,title_zh,country_or_org,jurisdiction_level,issuer,
                        policy_type,legal_status,published_date,year,language,topics,
                        official_url,official_url_final,raw_file,content_summary_original,
                        policy_objectives,policy_measures,regulatory_requirements,target_entities,
                        sectors_extracted,technologies_extracted,content_extraction_status,
                        content_extraction_error,fulltext_char_count,
                        relevance_level,relevance_score,relevance_reason,ai_review_decision,
                        ai_review_reason,ai_title_probability,ai_content_probability,
                        ai_review_model,ai_review_version
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    values[:2] + [title_zh] + values[2:8] + [year] + values[8:-1]
                    + [int(values[-1] or 0), effective_level, relevance_score, relevance_reason,
                       ai_review.get("ai_review_decision", "") if ai_review else "规则明确相关",
                       ai_review.get("ai_review_reason", "") if ai_review else "第一轮规则已确认",
                       ai_review.get("title_ai_probability") if ai_review else None,
                       ai_review.get("content_ai_probability") if ai_review else None,
                       ai_review.get("model", "") if ai_review else "",
                       ai_review.get("ai_review_version", "") if ai_review else ""],
                )
                row_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
                source_summary = value(row, "content_summary_original")
                summary, summary_status = clean_summary(source_summary, value(row, "content_extraction_status"))
                raw = resolve_raw_file(value(row, "raw_file"))
                connection.execute(
                    """UPDATE policies SET raw_available=?,raw_is_pdf=?,summary_status=?,summary_source=?,
                       country_original=?,language_original=?,country_or_org=?,language=?,
                       content_summary_original=?,is_relevant=?,date_missing=? WHERE id=?""",
                    (int(raw is not None), int(raw is not None and raw.suffix.lower() == '.pdf'),
                     summary_status, source_summary, value(row, "country_or_org"), value(row, "language"),
                     country(value(row, "country_or_org")), language(value(row, "language")), summary,
                     int(effective_level in ('明确相关', 'AI复核相关')), int(not date), row_id),
                )
                id_by_policy[policy_id] = row_id
                search_text = "\n".join([
                    value(row, "title_original"), title_zh, value(row, "country_or_org"),
                    value(row, "issuer"), value(row, "topics"),
                    value(row, "content_summary_original"), value(row, "policy_objectives"),
                    value(row, "policy_measures"), value(row, "regulatory_requirements"),
                    value(row, "target_entities"), value(row, "sectors_extracted"),
                    value(row, "technologies_extracted"),
                ])
                search_parts[policy_id] = "\n".join(
                    clean_summary(part)[0] for part in search_text.split("\n")
                )
                sector_text = "\n".join([
                    value(row, "title_original"), value(row, "topics"), value(row, "policy_type"),
                ])
                classifications = classify(search_text, sector_text)
                connection.executemany(
                    "INSERT INTO policy_categories(policy_row_id,category_id) VALUES (?,?)",
                    [
                        (row_id, category_ids[(dimension, category)])
                        for dimension, categories in classifications.items()
                        for category in categories
                    ],
                )
                if number % 1000 == 0:
                    print(f"已载入元数据 {number:,} 条", flush=True)
        indexed: set[str] = set()
        with FULLTEXT_PATH.open("rb", buffering=1024 * 1024) as handle:
            number = 0
            while True:
                offset = handle.tell()
                line = handle.readline()
                if not line:
                    break
                number += 1
                record = json.loads(line)
                policy_id = str(record.get("policy_id", ""))
                row_id = id_by_policy.get(policy_id)
                if row_id is None:
                    raise ValueError(f"正文编号不在主表中：{policy_id}")
                if policy_id in indexed:
                    raise ValueError(f"正文编号重复：{policy_id}")
                body = str(record.get("fulltext", ""))
                expected = connection.execute("SELECT fulltext_char_count,content_extraction_status FROM policies WHERE id=?", (row_id,)).fetchone()
                if len(body) != expected[0]:
                    raise ValueError(f"正文字数不一致：{policy_id}")
                if expected[1] in {"non_body", "mixed_source", "ocr_required"} and body.strip():
                    raise ValueError(f"隔离记录仍含正文：{policy_id}")
                connection.execute(
                    "UPDATE policies SET body_offset=?, body_bytes=? WHERE id=?",
                    (offset, len(line), row_id),
                )
                connection.execute(
                    "INSERT INTO policy_fts(rowid, search_text) VALUES (?, ?)",
                    (row_id, search_parts.get(policy_id, "")),
                )
                indexed.add(policy_id)
                if number % 500 == 0:
                    print(f"已核对正文位置 {number:,} / {len(id_by_policy):,}", flush=True)
        if indexed != set(id_by_policy):
            raise ValueError("主表与正文编号集合不一致")
        for policy_id, row_id in id_by_policy.items():
            if policy_id not in indexed:
                connection.execute(
                    "INSERT INTO policy_fts(rowid, search_text) VALUES (?, ?)",
                    (row_id, search_parts.get(policy_id, "")),
                )
        meta = {
            "schema_version": SCHEMA_VERSION,
            "quality_version": QUALITY_VERSION,
            "sqlite_version": sqlite3.sqlite_version,
            "record_count": str(len(id_by_policy)),
            "csv_mtime_ns": str(CSV_PATH.stat().st_mtime_ns),
            "fulltext_mtime_ns": str(FULLTEXT_PATH.stat().st_mtime_ns),
            "indexed_body_chars": str(INDEXED_BODY_CHARS),
            "taxonomy_version": TAXONOMY_VERSION,
            "translations_mtime_ns": str(TRANSLATIONS_PATH.stat().st_mtime_ns if TRANSLATIONS_PATH.exists() else 0),
            "relevance_version": RELEVANCE_VERSION,
            "translation_review_version": TRANSLATION_REVIEW_VERSION,
            "ai_review_version": AI_REVIEW_VERSION,
            "ai_review_mtime_ns": str(AI_REVIEW_PATH.stat().st_mtime_ns if AI_REVIEW_PATH.exists() else 0),
        }
        connection.executemany("INSERT INTO index_meta(key,value) VALUES (?,?)", meta.items())
        connection.commit()
        connection.execute("INSERT INTO policy_fts(policy_fts) VALUES ('optimize')")
        connection.commit()
        connection.execute("INSERT INTO policy_fts(policy_fts) VALUES ('integrity-check')")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("索引完整性校验失败")
        connection.execute("ANALYZE")
        connection.commit()
    finally:
        connection.close()
    os.replace(TEMP_DB, DB_PATH)
    print(f"索引完成：{DB_PATH}", flush=True)


def index_is_current() -> bool:
    if not DB_PATH.exists():
        return False
    try:
        with sqlite3.connect(DB_PATH.as_uri() + '?mode=ro', uri=True) as connection:
            meta = dict(connection.execute("SELECT key,value FROM index_meta"))
        return (
            meta.get("schema_version") == SCHEMA_VERSION
            and meta.get("quality_version") == QUALITY_VERSION
            and meta.get("sqlite_version") == sqlite3.sqlite_version
            and meta.get("csv_mtime_ns") == str(CSV_PATH.stat().st_mtime_ns)
            and meta.get("fulltext_mtime_ns") == str(FULLTEXT_PATH.stat().st_mtime_ns)
            and meta.get("taxonomy_version") == TAXONOMY_VERSION
            and meta.get("translations_mtime_ns") == str(TRANSLATIONS_PATH.stat().st_mtime_ns if TRANSLATIONS_PATH.exists() else 0)
            and meta.get("relevance_version") == RELEVANCE_VERSION
            and meta.get("translation_review_version") == TRANSLATION_REVIEW_VERSION
            and meta.get("ai_review_version") == AI_REVIEW_VERSION
            and meta.get("ai_review_mtime_ns") == str(AI_REVIEW_PATH.stat().st_mtime_ns if AI_REVIEW_PATH.exists() else 0)
            and meta.get("indexed_body_chars") == str(INDEXED_BODY_CHARS)
        )
    except (OSError, sqlite3.Error):
        return False


if __name__ == "__main__":
    build_index()
