const $ = (selector) => document.querySelector(selector);
const state = { page: 1, pageSize: 20, total: 0, q: "", country: "", year: "", language: "", policyType: "", fileType: "", topicCategory: "", instrumentCategory: "", sectorCategory: "", relevance: "high", titleMode: localStorage.getItem("titleMode") || "zh" };
const numberFormat = new Intl.NumberFormat("zh-CN");

function node(tag, className = "", text = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== "") element.textContent = text;
  return element;
}

async function api(path) {
  const response = await fetch(path);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.message || "无法读取本地数据，请确认检索窗口仍在运行。");
  return body;
}

function fillSelect(selector, items) {
  const select = $(selector);
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = `${item.value}（${numberFormat.format(item.count)}）`;
    select.append(option);
  }
}

async function loadStats() {
  const stats = await api("/api/stats");
  $("#stat-total").textContent = numberFormat.format(stats.total);
  $("#stat-jurisdictions").textContent = numberFormat.format(stats.jurisdictions);
  $("#stat-languages").textContent = numberFormat.format(stats.languages);
  $("#stat-years").textContent = `${stats.year_min}—${stats.year_max}`;
  fillSelect("#filter-country", stats.facets.country_or_org);
  fillSelect("#filter-year", stats.facets.year);
  fillSelect("#filter-language", stats.facets.language);
  fillSelect("#filter-type", stats.facets.policy_type);
  fillSelect("#filter-topic-category", stats.category_facets["政策主题"]);
  fillSelect("#filter-instrument-category", stats.category_facets["政策手段"]);
  fillSelect("#filter-sector-category", stats.category_facets["应用领域"]);
  $("#filter-file").options[1].textContent = `仅有 PDF（${numberFormat.format(stats.pdf_count)}）`;
  $("#filter-file").options[2].textContent = `非 PDF（${numberFormat.format(stats.non_pdf_count)}）`;
  const relevanceCounts = stats.relevance_counts || {};
  $("#filter-relevance").options[0].textContent = `清洗后相关（推荐，${numberFormat.format((relevanceCounts["明确相关"] || 0) + (relevanceCounts["AI复核相关"] || 0))}）`;
  $("#filter-relevance").options[1].textContent = `仅 AI 新复核相关（${numberFormat.format(relevanceCounts["AI复核相关"] || 0)}）`;
  $("#filter-relevance").options[2].textContent = `待人工复核（${numberFormat.format(relevanceCounts["待人工复核"] || 0)}）`;
  $("#filter-relevance").options[3].textContent = `AI 复核无关 / 隔离（${numberFormat.format(relevanceCounts["AI复核无关"] || 0)}）`;
  renderCountryChart(stats.top_countries.slice(0, 8));
}

function renderCountryChart(items) {
  const chart = $("#country-chart");
  chart.replaceChildren();
  const maximum = Math.max(...items.map(item => item.count), 1);
  for (const item of items) {
    const row = node("div", "bar-row");
    const copy = node("div", "bar-copy");
    copy.append(node("span", "", item.name), node("span", "", numberFormat.format(item.count)));
    const track = node("div", "bar-track");
    const fill = node("div", "bar-fill");
    fill.style.width = `${Math.max(3, item.count / maximum * 100)}%`;
    track.append(fill);
    row.append(copy, track);
    chart.append(row);
  }
}

function params() {
  const query = new URLSearchParams({ page: state.page, page_size: state.pageSize });
  if (state.q) query.set("q", state.q);
  if (state.country) query.set("country", state.country);
  if (state.year) query.set("year", state.year);
  if (state.language) query.set("language", state.language);
  if (state.policyType) query.set("policy_type", state.policyType);
  if (state.fileType) query.set("file_type", state.fileType);
  if (state.topicCategory) query.set("topic_category", state.topicCategory);
  if (state.instrumentCategory) query.set("instrument_category", state.instrumentCategory);
  if (state.sectorCategory) query.set("sector_category", state.sectorCategory);
  if (state.relevance !== "all") query.set("relevance", state.relevance);
  return query;
}

let requestNumber = 0;
async function loadResults() {
  const currentRequest = ++requestNumber;
  $("#loading").hidden = false;
  $("#result-list").hidden = true;
  $("#error-banner").hidden = true;
  updateActiveFilters();
  try {
    const result = await api(`/api/search?${params()}`);
    if (currentRequest !== requestNumber) return;
    state.total = result.total;
    renderResults(result.items);
    renderPagination();
    const prefix = state.q ? `“${state.q}” 找到` : "当前共有";
    $("#result-summary").textContent = `${prefix} ${numberFormat.format(result.total)} 条政策`;
  } catch (error) {
    $("#error-banner").textContent = error.message;
    $("#error-banner").hidden = false;
  } finally {
    if (currentRequest === requestNumber) {
      $("#loading").hidden = true;
      $("#result-list").hidden = false;
    }
  }
}

function renderResults(items) {
  const list = $("#result-list");
  list.replaceChildren();
  if (!items.length) {
    const empty = node("div", "empty-state");
    empty.append(node("h3", "", "没有找到匹配的政策"), node("p", "", "试试更短的关键词，或清除部分筛选条件。"));
    list.append(empty);
    return;
  }
  for (const item of items) {
    const card = node("article", "result-card");
    card.tabIndex = 0;
    const date = node("div", "result-date", item.published_date?.slice(0, 4) || "未注明");
    if (item.published_date?.length > 4) date.append(node("small", "", item.published_date.slice(5)));
    const content = node("div");
    const translated = item.title_zh?.trim();
    const original = item.title_original || "无标题政策";
    const primaryTitle = state.titleMode === "original" ? original : (translated || original);
    content.append(node("h4", "", primaryTitle));
    if (state.titleMode === "bilingual" && translated && translated !== original) content.append(node("p", "original-title", original));
    const meta = node("div", "result-meta");
    const relevance = node("span", `relevance-badge${["待人工复核", "AI复核无关"].includes(item.relevance_level) ? " review" : ""}`, item.relevance_level || "未评估");
    meta.append(relevance);
    [item.country_or_org, item.issuer, item.language, item.policy_type].filter(Boolean).forEach(value => meta.append(node("span", "", value)));
    content.append(meta);
    if (item.content_summary_original) content.append(node("p", "result-summary", item.content_summary_original));
    const tags = (item.topics || "").split(/[;,]/).map(value => value.trim()).filter(Boolean).slice(0, 4);
    for (const tag of tags) content.append(node("span", "tag", tag));
    card.append(date, content, node("span", "result-arrow", "→"));
    card.addEventListener("click", () => openDetail(item.policy_id));
    card.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") openDetail(item.policy_id); });
    list.append(card);
  }
}

function renderPagination() {
  const container = $("#pagination");
  container.replaceChildren();
  const pages = Math.max(1, Math.ceil(state.total / state.pageSize));
  if (pages <= 1) return;
  const addButton = (label, page, disabled = false, current = false) => {
    const button = node("button", "", label);
    button.disabled = disabled;
    if (current) button.setAttribute("aria-current", "page");
    button.addEventListener("click", () => { state.page = page; loadResults(); window.scrollTo({ top: $(".workspace").offsetTop - 150, behavior: "smooth" }); });
    container.append(button);
  };
  addButton("‹", Math.max(1, state.page - 1), state.page === 1);
  const start = Math.max(1, Math.min(state.page - 2, pages - 4));
  const end = Math.min(pages, start + 4);
  for (let page = start; page <= end; page += 1) addButton(String(page), page, false, page === state.page);
  addButton("›", Math.min(pages, state.page + 1), state.page === pages);
}

function updateActiveFilters() {
  const count = [state.country, state.year, state.language, state.policyType, state.fileType, state.topicCategory, state.instrumentCategory, state.sectorCategory].filter(Boolean).length;
  $("#active-filter-count").textContent = String(count + (state.relevance === "high" ? 0 : 1));
}

function detailSection(title, value) {
  if (!value) return null;
  const section = node("section", "detail-section");
  section.append(node("h3", "", title), node("p", "", value));
  return section;
}

async function openDetail(policyId) {
  const drawer = $("#detail-drawer");
  $("#drawer-backdrop").hidden = false;
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  const content = $("#detail-content");
  content.replaceChildren(node("p", "", "正在读取政策详情…"));
  try {
    const item = await api(`/api/policies/${encodeURIComponent(policyId)}`);
    content.replaceChildren();
    const translated = item.title_zh?.trim();
    const original = item.title_original || "无标题政策";
    const primaryTitle = state.titleMode === "original" ? original : (translated || original);
    content.append(node("p", "section-kicker", item.policy_id), node("h2", "", primaryTitle));
    if (state.titleMode === "bilingual" && translated && translated !== original) content.append(node("p", "detail-original-title", original));
    const meta = node("div", "detail-meta");
    meta.append(node("span", "relevance-badge", `${item.relevance_level} · ${item.relevance_score}分`));
    [item.country_or_org, item.issuer, item.published_date, item.language, item.policy_type, item.legal_status].filter(Boolean).forEach(value => meta.append(node("span", "", value)));
    content.append(meta);
    const actions = node("div", "detail-actions");
    const officialUrl = item.official_url_final || item.official_url;
    if (officialUrl) {
      const link = node("a", "", "打开官方网页 ↗");
      link.href = officialUrl; link.target = "_blank"; link.rel = "noopener noreferrer";
      actions.append(link);
    }
    const raw = node("a", "secondary", "查看原始文件");
    raw.href = `/api/policies/${encodeURIComponent(policyId)}/raw`; raw.target = "_blank";
    actions.append(raw);
    content.append(actions);
    if (item.classifications && Object.keys(item.classifications).length) {
      const classificationSection = node("section", "detail-section");
      classificationSection.append(node("h3", "", "中文内容分类"));
      const grid = node("div", "classification-grid");
      for (const [dimension, categories] of Object.entries(item.classifications)) {
        const row = node("div", "classification-row");
        row.append(node("strong", "", dimension), node("span", "", categories.join("、")));
        grid.append(row);
      }
      classificationSection.append(grid);
      content.append(classificationSection);
    }
    const sections = [
      detailSection("内容摘要", item.content_summary_original), detailSection("政策目标", item.policy_objectives),
      detailSection("第一轮规则判断", item.relevance_reason),
      detailSection("AI 语义复核", item.ai_review_reason || "第一轮规则已明确确认，无需二次语义复核"),
      detailSection("政策措施", item.policy_measures), detailSection("监管要求", item.regulatory_requirements),
      detailSection("适用对象", item.target_entities), detailSection("主题与标签", [item.topics, item.sectors_extracted, item.technologies_extracted].filter(Boolean).join(" · ")),
    ].filter(Boolean);
    sections.forEach(section => content.append(section));
    const bodySection = node("section", "detail-section");
    bodySection.append(node("h3", "", "政策正文"));
    const bodyBox = node("div", "body-text", "正在载入正文…");
    bodySection.append(bodyBox);
    content.append(bodySection);
    await loadBody(policyId, bodyBox, bodySection, 0);
  } catch (error) {
    content.replaceChildren(node("div", "error-banner", error.message));
  }
}

async function loadBody(policyId, bodyBox, section, offset) {
  try {
    const data = await api(`/api/policies/${encodeURIComponent(policyId)}/body?offset=${offset}&limit=30000`);
    if (offset === 0) bodyBox.textContent = data.text || "正文为空。";
    else bodyBox.textContent += data.text;
    section.querySelector(".load-more")?.remove();
    if (data.has_more) {
      const more = node("button", "load-more", `继续加载（已显示 ${numberFormat.format(data.next_offset)} / ${numberFormat.format(data.total_chars)} 字符）`);
      more.addEventListener("click", () => loadBody(policyId, bodyBox, section, data.next_offset));
      section.append(more);
    }
  } catch (error) {
    bodyBox.textContent = error.message;
  }
}

function closeDrawer() {
  $("#detail-drawer").classList.remove("open");
  $("#detail-drawer").setAttribute("aria-hidden", "true");
  $("#drawer-backdrop").hidden = true;
  document.body.style.overflow = "";
}

function applySearch() {
  state.q = $("#search-input").value.trim();
  state.page = 1;
  loadResults();
}

$("#search-button").addEventListener("click", applySearch);
$("#search-input").addEventListener("keydown", event => { if (event.key === "Enter") applySearch(); });
$("#reset-button").addEventListener("click", () => {
  $("#search-input").value = "";
  ["#filter-country", "#filter-year", "#filter-language", "#filter-type", "#filter-file", "#filter-topic-category", "#filter-instrument-category", "#filter-sector-category"].forEach(selector => { $(selector).value = ""; });
  $("#filter-relevance").value = "high";
  Object.assign(state, { page: 1, q: "", country: "", year: "", language: "", policyType: "", fileType: "", topicCategory: "", instrumentCategory: "", sectorCategory: "", relevance: "high" });
  loadResults();
});
[["#filter-country", "country"], ["#filter-year", "year"], ["#filter-language", "language"], ["#filter-type", "policyType"], ["#filter-file", "fileType"], ["#filter-topic-category", "topicCategory"], ["#filter-instrument-category", "instrumentCategory"], ["#filter-sector-category", "sectorCategory"], ["#filter-relevance", "relevance"]].forEach(([selector, key]) => {
  $(selector).addEventListener("change", event => { state[key] = event.target.value; state.page = 1; loadResults(); });
});
$("#page-size").addEventListener("change", event => { state.pageSize = Number(event.target.value); state.page = 1; loadResults(); });
$("#title-mode").value = state.titleMode;
$("#title-mode").addEventListener("change", event => { state.titleMode = event.target.value; localStorage.setItem("titleMode", state.titleMode); loadResults(); });
$("#close-drawer").addEventListener("click", closeDrawer);
$("#drawer-backdrop").addEventListener("click", closeDrawer);
document.addEventListener("keydown", event => { if (event.key === "Escape") closeDrawer(); });

Promise.all([loadStats(), loadResults()]).catch(error => {
  $("#error-banner").textContent = error.message;
  $("#error-banner").hidden = false;
});
