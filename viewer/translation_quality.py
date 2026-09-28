"""Human-authored terminology corrections and selected policy-title translations."""

from __future__ import annotations

import re


VERSION = "2026-07-v3"


MANUAL_OVERRIDES = {
    "Executive Order 14110 of October 30 2023 Safe Secure and Trustworthy Development and Use of Artificial Intelligence": "2023年10月30日第14110号行政命令：安全、可靠、可信地开发和使用人工智能",
    "Removing Barriers to American Leadership in Artificial Intelligence": "消除美国人工智能领导地位面临的障碍",
    "Artificial Intelligence Risk Management Framework AI RMF 1.0": "人工智能风险管理框架（AI RMF 1.0）",
    "Artificial Intelligence Risk Management Framework Generative Artificial Intelligence Profile": "人工智能风险管理框架：生成式人工智能应用指南",
    "Advancing Governance Innovation and Risk Management for Agency Use of Artificial Intelligence": "推进联邦机构使用人工智能的治理创新与风险管理",
    "Defence Artificial Intelligence Strategy": "国防人工智能战略",
    "Artificial intelligence skills for all": "面向全民的人工智能技能",
    "Understanding artificial intelligence ethics and safety": "理解人工智能伦理与安全",
    "Managing your artificial intelligence project": "人工智能项目管理",
    "Planning and preparing for artificial intelligence implementation": "人工智能实施规划与准备",
    "Assessing if artificial intelligence is the right solution": "评估人工智能是否为合适的解决方案",
    "Use of artificial intelligence in casework evidence": "在案件证据处理中使用人工智能",
    "Guidelines for using generative artificial intelligence if you’re a software developer": "软件开发人员使用生成式人工智能指南",
    "A guide to using artificial intelligence in the public sector": "公共部门人工智能使用指南",
    "Turing Artificial Intelligence Fellowships": "图灵人工智能研究员计划",
    "Artificial Intelligence and Public Standards: government response to report": "《人工智能与公共标准》报告：政府回应",
    "Joint statement from founding members of the Global Partnership on Artificial Intelligence": "全球人工智能伙伴关系创始成员联合声明",
    "Generative artificial intelligence (AI) in education": "教育领域的生成式人工智能（AI）",
    "Medical devices: software and artificial intelligence (AI)": "医疗器械：软件与人工智能（AI）",
    "Artificial intelligence malpractice and assessment - advice note": "人工智能不当使用与评估：建议说明",
    "Artificial Intelligence Act": "人工智能法",
    "National Artificial Intelligence Strategy": "国家人工智能战略",
    "National AI Strategy": "国家人工智能战略",
    "AI regulation a pro-innovation approach": "人工智能监管：促进创新的方法",
    "Voluntary Code of Conduct on the Responsible Development and Management of Advanced Generative AI Systems": "先进生成式人工智能系统负责任开发与管理自愿行为准则",
    "Declaration of the United States of America and the United Kingdom of Great Britain and Northern Ireland on Cooperation in AI Research and Development": "美利坚合众国与大不列颠及北爱尔兰联合王国关于人工智能研发合作的声明",
    "AI and Public Standards – Terms of Reference": "人工智能与公共标准：职权范围",
    "CSPL submission to Science and Technology Committee inquiry on Governance of AI": "公共生活标准委员会就人工智能治理向科学与技术委员会提交的意见",
    "Impact of AI on the regulation of medical products": "人工智能对医疗产品监管的影响",
    "Human-centred ways of working with AI in intelligence analysis": "情报分析中以人为本的人工智能协作方式",
    "The government’s code of practice on copyright and AI": "政府关于版权与人工智能的行为准则",
    "Using AI in education: support for school and college leaders": "教育领域使用人工智能：为学校和学院负责人提供支持",
    "Understanding AI in education: module 1": "理解教育领域的人工智能：模块一",
    "AI in the UK: ready, willing and able? - government response to the select committee report": "英国的人工智能：是否准备充分、意愿明确且能力具备？——政府对特别委员会报告的回应",
    "G7 Cyber Expert Group Statement on AI and Cybersecurity": "七国集团网络专家组关于人工智能与网络安全的声明",
    "Introduction to AI with a focus on counter fraud": "人工智能概论：聚焦反欺诈",
    "Joint Statement on competition in generative AI foundation models and AI products": "关于生成式人工智能基础模型与人工智能产品竞争的联合声明",
    "AI in coursework: resources for schools": "课程作业中的人工智能：学校资源",
    "Responsible AI in Recruitment guide": "招聘领域负责任人工智能指南",
    "The role of AI in addressing misinformation on social media platforms": "人工智能在治理社交媒体平台虚假信息中的作用",
    "AI action plan for justice": "司法领域人工智能行动计划",
    "AI for Science Strategy": "人工智能促进科学发展战略",
    "100 radical innovation breakthroughs for the future.": "面向未来的100项突破性创新",
    "Request for Information and Comment on Financial Institutions' Use of Artificial Intelligence, Including Machine Learning": "关于金融机构使用人工智能（包括机器学习）的信息征询及意见征集",
    "Solicitation of Written Comments by the National Security Commission on Artificial Intelligence": "美国国家人工智能安全委员会征集书面意见",
    "Notice Pursuant to the National Cooperative Research and Production Act of 1993-AI Infrastructure Alliance, Inc.": "依据《1993年国家合作研究与生产法》发布的通知——人工智能基础设施联盟公司",
}


def polish(source: str, translated: str) -> str:
    if source in MANUAL_OVERRIDES:
        return MANUAL_OVERRIDES[source]
    result = translated.strip()
    replacements = {
        "人工情报": "人工智能", "人造情报": "人工智能", "人工情報": "人工智能",
        "人为情报": "人工智能", "基因人工智能": "生成式人工智能",
        "产生式人工智能": "生成式人工智能", "一般用途人工智能": "通用人工智能",
        "基础模型": "基础模型", "大型语言模型": "大语言模型",
        "可信赖人工智能": "可信人工智能", "可信任人工智能": "可信人工智能",
    }
    for wrong, right in replacements.items():
        result = result.replace(wrong, right)
    if re.search(r"\bartificial intelligence\b", source, re.I):
        result = re.sub(r"人工(情报|情報)|人造情报", "人工智能", result)
    if re.search(r"\bgenerative (artificial intelligence|ai)\b", source, re.I):
        if "生成式人工智能" not in result:
            result = result.replace("人工智能", "生成式人工智能", 1)
    if re.search(r"(?<![A-Za-z])AI(?![A-Za-z])", source):
        result = result.replace("大赦国际", "人工智能").replace("大赦组织", "人工智能")
        result = result.replace("国际特赦组织", "人工智能")
    result = re.sub(r"\s+([，。；：！？])", r"\1", result)
    return result
