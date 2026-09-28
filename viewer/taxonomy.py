"""Chinese multi-dimensional taxonomy for AI policy records."""

from __future__ import annotations


VERSION = "2026-07-v2"


TAXONOMY: dict[str, list[tuple[str, list[str]]]] = {
    "政策主题": [
        ("综合战略与规划", ["发展规划", "战略规划", "行动计划", "国家战略", "人工智能战略", "ai strategy", "national strategy", "strategic plan", "action plan", "stratégie", "strategie", "estrategia"]),
        ("人工智能治理与伦理", ["人工智能治理", "伦理治理", "伦理准则", "负责任人工智能", "治理框架", "ai governance", "artificial intelligence governance", "ai ethics", "ethical ai", "responsible ai", "ethics guidelines", "gouvernance", "éthique"]),
        ("算法监管与透明度", ["算法监管", "算法推荐", "算法备案", "算法透明", "自动化决策", "算法歧视", "algorithmic accountability", "algorithmic transparency", "automated decision", "recommendation algorithm", "algorithm audit", "automated systems"]),
        ("数据治理与隐私保护", ["数据治理", "数据安全", "个人信息保护", "隐私保护", "数据跨境", "训练数据", "data governance", "data protection", "data privacy", "personal data", "privacy", "datenschutz", "protection des données", "vie privée"]),
        ("生成式人工智能与大模型", ["生成式人工智能", "生成式ai", "大语言模型", "大模型", "基础模型", "generative ai", "generative artificial intelligence", "large language model", "foundation model", "general-purpose ai", "general purpose ai", "chatgpt", "deep synthesis", "deepfake"]),
        ("安全、风险与可信AI", ["人工智能安全", "安全评估", "风险管理", "高风险人工智能", "可信人工智能", "模型安全", "红队测试", "ai safety", "ai risk", "risk management", "high-risk ai", "trustworthy ai", "safety institute", "sûreté", "sécurité de l'intelligence artificielle"]),
        ("标准、测试与认证", ["标准体系", "技术标准", "标准化", "检测认证", "符合性评估", "基准测试", "standardization", "standardisation", "technical standard", "conformity assessment", "certification", "benchmarking", "testing and evaluation"]),
        ("知识产权与版权", ["知识产权", "著作权", "版权", "专利", "训练数据版权", "intellectual property", "copyright", "patent", "droit d’auteur", "propriété intellectuelle"]),
        ("科研创新与技术研发", ["科学研究", "技术研发", "科技创新", "基础研究", "研发计划", "research and development", "scientific research", "innovation programme", "research program", "forschung", "recherche scientifique"]),
        ("算力、芯片与基础设施", ["算力", "计算基础设施", "数据中心", "智能芯片", "半导体", "超算", "compute infrastructure", "computing capacity", "data centre", "data center", "semiconductor", "ai chip", "supercomputer"]),
        ("产业发展与商业应用", ["产业发展", "产业促进", "商业应用", "企业应用", "人工智能产业", "industrial development", "commercial application", "business adoption", "ai industry", "competitiveness", "productivity"]),
        ("国际合作与全球治理", ["国际合作", "全球治理", "国际公约", "多边合作", "international cooperation", "global governance", "multilateral", "international agreement", "g7", "g20", "united nations", "联合国"]),
        ("政府应用与公共治理", ["政务服务", "数字政府", "政府人工智能", "公共部门人工智能", "行政管理", "government use", "public sector ai", "public administration", "digital government", "government agency"]),
    ],
    "政策手段": [
        ("法律法规与监管规则", ["法律", "法规", "条例", "办法", "规定", "监管规则", "立法", "law", "act of", "regulation", "regulatory rule", "legal framework", "legislation", "règlement", "loi", "verordnung"]),
        ("战略规划与行动方案", ["战略", "规划", "行动方案", "行动计划", "路线图", "strategy", "strategic plan", "action plan", "roadmap", "programme of work", "stratégie", "plan d'action"]),
        ("指导意见与原则框架", ["指导意见", "指导原则", "伦理准则", "政策框架", "实施意见", "guidance", "guideline", "principles", "framework", "recommendation", "code of practice"]),
        ("标准规范与技术指南", ["标准", "规范", "技术指南", "评测指南", "standard", "specification", "technical guidance", "protocol", "certification", "conformity assessment"]),
        ("资金资助与税收激励", ["专项资金", "财政支持", "资金支持", "补贴", "基金", "税收优惠", "grant", "funding", "subsidy", "tax credit", "financial support", "investment fund"]),
        ("政府采购与公共投资", ["政府采购", "公共采购", "公共投资", "采购指南", "government procurement", "public procurement", "public investment", "acquisition policy"]),
        ("试点示范与监管沙盒", ["试点", "示范区", "先行先试", "监管沙盒", "pilot program", "pilot programme", "regulatory sandbox", "testbed", "demonstration project"]),
        ("监督执法与合规审查", ["监督检查", "执法", "合规审查", "备案", "处罚", "审计", "enforcement", "compliance review", "audit", "inspection", "penalty", "registration requirement"]),
        ("人才培养与能力建设", ["人才培养", "人才引进", "教育培训", "能力建设", "技能提升", "workforce development", "skills training", "capacity building", "talent programme", "digital skills"]),
        ("研究报告与政策倡议", ["研究报告", "白皮书", "咨询报告", "政策倡议", "意见征集", "report", "white paper", "consultation", "policy initiative", "discussion paper", "study on"]),
        ("国际协议与合作机制", ["国际协议", "合作备忘录", "联合声明", "国际合作机制", "international agreement", "memorandum of understanding", "joint declaration", "cooperation framework", "convention"]),
    ],
    "应用领域": [
        ("教育与人才", ["教育", "学校", "高校", "教师", "学生", "人才", "education", "school", "university", "student", "teacher", "éducation", "bildung"]),
        ("医疗与生命科学", ["医疗", "健康", "医院", "药品", "生命科学", "healthcare", "health", "medical", "hospital", "medicine", "life science", "santé", "gesundheit"]),
        ("金融与保险", ["金融", "银行", "证券", "保险", "信贷", "finance", "financial service", "banking", "insurance", "credit scoring", "fintech"]),
        ("工业与制造", ["工业", "制造业", "工厂", "智能制造", "manufacturing", "factory", "industry 4.0", "production system"]),
        ("交通与自动驾驶", ["交通", "自动驾驶", "智能网联汽车", "无人驾驶", "航空", "transport", "autonomous vehicle", "self-driving", "connected vehicle", "aviation", "mobility"]),
        ("农业与食品", ["农业", "农村", "农产品", "食品安全", "agriculture", "farming", "food safety", "agricultural", "rural development"]),
        ("能源与环境", ["能源", "电力", "气候", "环境保护", "碳排放", "energy", "electricity", "climate", "environment", "emission", "sustainability"]),
        ("政务与公共服务", ["政务", "公共服务", "行政管理", "政府部门", "public service", "public administration", "government service", "civil service"]),
        ("公共安全与司法", ["公共安全", "公安", "警务", "司法", "法院", "执法", "public safety", "police", "law enforcement", "judicial", "court", "criminal justice"]),
        ("国防与国家安全", ["国防", "军队", "军事", "国家安全", "defence", "defense", "military", "national security", "armed forces"]),
        ("文化、媒体与内容", ["文化", "媒体", "新闻", "出版", "广告", "视听", "journalism", "publishing", "advertising", "audiovisual", "creative industries"]),
        ("就业与劳动", ["就业", "劳动者", "劳动力", "招聘", "工作场所", "employment", "worker", "workforce", "hiring", "workplace", "labour", "labor"]),
        ("城市治理与智慧城市", ["城市治理", "智慧城市", "城市规划", "社区治理", "smart city", "urban planning", "municipal", "local government"]),
        ("通信与互联网平台", ["电信", "通信", "互联网平台", "社交平台", "网络服务", "telecommunications", "online platform", "social media", "internet service", "digital platform"]),
        ("消费者权益保护", ["消费者", "消费权益", "产品安全", "虚假宣传", "consumer protection", "consumer rights", "product safety", "unfair practice"]),
    ],
}


FALLBACK = {"政策主题": "其他政策主题", "政策手段": "其他政策手段", "应用领域": "综合或其他领域"}


def classify(text: str, sector_text: str | None = None) -> dict[str, list[str]]:
    haystack = text.casefold()
    sector_haystack = (sector_text if sector_text is not None else text).casefold()
    result: dict[str, list[str]] = {}
    for dimension, categories in TAXONOMY.items():
        source = sector_haystack if dimension == "应用领域" else haystack
        matches = [name for name, keywords in categories if any(keyword.casefold() in source for keyword in keywords)]
        result[dimension] = matches or [FALLBACK[dimension]]
    return result


def category_rows() -> list[tuple[str, str, int]]:
    rows: list[tuple[str, str, int]] = []
    for dimension, categories in TAXONOMY.items():
        for order, (name, _) in enumerate(categories, start=1):
            rows.append((dimension, name, order))
        rows.append((dimension, FALLBACK[dimension], len(categories) + 1))
    return rows
