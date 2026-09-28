"""Collect original-language AI policy documents from Shanghai's official AI topic pages."""
from __future__ import annotations

import csv, hashlib, re, time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
import io

ROOT = Path(__file__).resolve().parents[1]
OUT, RAW = ROOT / "data" / "processed", ROOT / "data" / "raw"
BASE = "https://www.shanghai.gov.cn"
SECTIONS = ["/yshqrgzn/", "/rgznsj/index.html", "/rgznqj/index.html"]
EXTRA_SOURCES = {
    "https://www.hlj.gov.cn/hlj/c116016nbc/202603/c00_31928047.shtml": "黑龙江省深入实施“人工智能+”行动的实施方案",
    "https://www.hlj.gov.cn/hlj/c116016nbc/202603/c00_31928049.shtml": "黑龙江省“人工智能＋”政务深化应用工作方案",
    "https://www.baoding.gov.cn/zwgkdocnr-888888712-539095.html": "保定市推动“人工智能+”行动方案",
    "https://www.wuxi.gov.cn/doc/2025/05/08/4558749.shtml": "无锡市关于建设“人工智能＋”标杆城市的政策意见",
    "https://www.cac.gov.cn/2025-10/10/c_1761819469929310.htm": "政务领域人工智能大模型部署应用指引",
    "https://www.gs.gov.cn/gsszf/c100054/202601/174267551/files/057d0b2c21c644529c52276c83a6a458.pdf": "甘肃省深入实施“人工智能＋”行动方案",
    "https://3g.wuhan.gov.cn/zwgk/xxgk/zfwj/bgtwj/202603/t20260323_2743481.shtml": "武汉市推动“人工智能+”行动方案",
    "https://www.yantai.gov.cn/col/col99960/art/2026/art_133d0383f24a48e389e4cbd994c7acee.html?type=4JnkXemNbirDhO2Om8bBC": "烟台市“人工智能+”三年行动方案",
    "https://wap.cq.gov.cn/zwgk/zfxxgkml/szfwj/xzgfxwj/szfbgt/202512/W020251217415210095636.pdf": "重庆市推动“人工智能+”行动方案",
    "https://www.suzhou.gov.cn/szsrmzf/szfgfxwjk/202503/ce173340fc83433cb2828894d377ad56/files/60f9598e004442a2b271f6e4c3d5b1a9.pdf": "苏州市高水平建设“人工智能+”创新发展试验区的若干措施",
    "https://quanzhou.gov.cn/xsdmyjjfwzq/zqztfwrk/jjjy/zcdlb/zc/cyfz/202410/P020241105539630520393.pdf": "泉州市支持人工智能产业发展若干措施",
    "https://law.nstc.gov.tw/LawContent.aspx?id=GL000592&kw=": "人工智慧基本法",
    "https://moda.gov.tw/major-policies/ai/governance/19248": "AI基本法｜治理與評測",
    "https://moda.gov.tw/major-policies/ai/governance/19246": "AI應用影響評估",
    "https://moda.gov.tw/major-policies/policy-elucidation/1305": "數位發展部施政說明",
    "https://www.ey.gov.tw/Page/5A8A0CB5B41DA11E/0a421b36-2e94-4392-8d69-c798b8669d4f": "公部門AI人才培育與智慧政府",
    "https://www.ey.gov.tw/Page/5A8A0CB5B41DA11E/b6fbf240-2d1a-4252-9f81-28144acb1d64": "制定人工智慧基本法—建構AI發展與應用良善環境",
    "https://moda.gov.tw/press/press-releases/15428": "數發部推出多項舉措推動AI產業發展",
    "https://www.digitalpolicy.gov.hk/tc/our_work/data_governance/policies_standards/ethical_ai_framework/doc/Ethical_AI_Framework_tc.pdf": "人工智能道德框架第2.0版",
    "https://www.digitalpolicy.gov.hk/tc/our_work/data_governance/policies_standards/ethical_ai_framework/doc/Quick_Reference_Guide-Ethical_AI_Framework_tc.pdf": "人工智能道德框架簡易參考指南",
}
HEAD = {"User-Agent": "AIPolicyDatasetBot/0.1 (public-policy research; respectful collection)"}
AI_RE = re.compile(r"人工智能|智能体|大模型|生成式|深度合成|算法", re.I)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def page_text(body: bytes) -> str:
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return clean(soup.get_text(" ", strip=True))


def source_text(body: bytes, content_type: str) -> tuple[str, str]:
    if "pdf" in content_type.lower() or body[:4] == b"%PDF":
        return clean("\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(body)).pages)), "pdf"
    return page_text(body), "html"


def date_from(text: str) -> str:
    match = re.search(r"(?:成文日期|发布日期|公开日期|印发日期)[：:\s]*([12]\d{3}[-年/.]\d{1,2}[-月/.]\d{1,2})", text)
    if not match:
        fallback = re.search(r"\b(20\d{2})\b", text)
        return fallback.group(1) if fallback else ""
    return re.sub(r"年|/|\.", "-", match.group(1)).replace("月", "-").replace("日", "")


def jurisdiction(url: str) -> str:
    if ".gov.hk" in url:
        return "香港"
    if ".gov.mo" in url:
        return "澳门"
    if ".gov.tw" in url or ".nstc.gov.tw" in url:
        return "台湾"
    return "中国"


def main() -> int:
    session = requests.Session(); session.headers.update(HEAD)
    candidates: dict[str, str] = {}
    for section in SECTIONS:
        response = session.get(urljoin(BASE, section), timeout=30); response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        for link in soup.select("a[href]"):
            title = clean(link.get("title") or link.get_text(" ", strip=True))
            url = urljoin(BASE, link["href"])
            if url.startswith(BASE) and url.endswith(".html") and AI_RE.search(title):
                candidates[url] = title
    candidates.update(EXTRA_SOURCES)
    rows, failed = [], []
    RAW.mkdir(parents=True, exist_ok=True)
    for index, (url, listed_title) in enumerate(candidates.items(), 1):
        try:
            response = session.get(url, timeout=30); response.raise_for_status()
            body = response.content
            text, _parser = source_text(body, response.headers.get("content-type", ""))
            if len(text) < 500 or not AI_RE.search(text):
                raise requests.RequestException("No usable AI-policy body text")
            digest = hashlib.sha256(body).hexdigest(); pid = f"CN-SH-{index:04d}"
            raw = RAW / f"{pid}__{digest[:16]}{'.pdf' if body[:4] == b'%PDF' else '.html'}"; raw.write_bytes(body)
            title_node = BeautifulSoup(body, "html.parser").select_one("h1")
            title = clean(title_node.get_text(" ", strip=True)) if title_node else listed_title
            if not title or title in {"數位發展部全球資訊網", "數位發展部 Ministry of Digital Affairs"}:
                title = listed_title
            place = jurisdiction(url)
            rows.append({"policy_id": pid, "title_original": title, "country_or_org": place, "jurisdiction_level": "subnational" if place == "中国" else "national", "issuer": "上海市有关部门" if place == "中国" else f"{place}政府有关部门", "policy_type": "政策文件", "legal_status": "unknown", "published_date": date_from(text), "language": "zh", "topics": "人工智能", "official_url": url, "official_url_final": response.url, "source_domain": urlparse(response.url).netloc, "content_sha256": digest, "raw_file": str(raw.relative_to(ROOT)).replace("\\", "/"), "fetched_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(), "fulltext_char_count": len(text), "content_extraction_status": "extracted", "content_summary_original": text[:500], "verification_status": "verified_http"})
            print(f"[{index}/{len(candidates)}] OK {pid}")
        except requests.RequestException as exc:
            failed.append({"title_original": listed_title, "official_url": url, "error": clean(str(exc))})
        time.sleep(.25)
    for name, records in (("shanghai_ai_verified.csv", rows), ("shanghai_ai_failed.csv", failed)):
        fields = list(records[0]) if records else ["title_original", "official_url", "error"]
        with (OUT / name).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(records)
    print(f"Shanghai official AI policies: {len(rows)} verified, {len(failed)} failed")


if __name__ == "__main__":
    main()
