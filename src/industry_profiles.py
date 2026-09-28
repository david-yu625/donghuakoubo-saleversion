"""Industry profiles shared by the UI and every AI prompt builder."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndustryProfile:
    key: str
    label: str
    expert_role: str
    audience: str
    focus: str
    visual_examples: str


INDUSTRY_PROFILES = (
    IndustryProfile(
        "computer",
        "计算机与互联网",
        "计算机与互联网领域的资深从业者",
        "普通电脑、互联网产品和数字工具用户",
        "软件、硬件、网络、人工智能、数据和数字产品中的真实机制、操作方法与常见误区",
        "软件界面、设备、数据、网络连接、代码结构和数字产品流程",
    ),
    IndustryProfile(
        "finance",
        "金融财经",
        "金融财经领域的资深从业者",
        "需要理解金融产品、经济现象和个人财务决策的普通用户",
        "金融产品、经济现象、风险判断、个人财务和常见金融误区",
        "账本、合同、资金流、价格变化、风险对比和清晰的数据关系",
    ),
    IndustryProfile(
        "health",
        "医疗健康",
        "医疗健康领域的专业科普作者",
        "希望获得可靠健康知识的普通人",
        "身体机制、健康习惯、常见误区和就医判断；避免诊断和夸大承诺",
        "人体结构、生活场景、检查指标、习惯对比和清晰的因果关系",
    ),
    IndustryProfile(
        "education",
        "教育学习",
        "教育与学习方法领域的资深教研者",
        "学生、家长和需要提升学习效率的人",
        "学习机制、知识理解、记忆方法、教学场景和常见学习误区",
        "书本、课堂、知识结构、学习步骤、对比和可执行的方法示意",
    ),
    IndustryProfile(
        "workplace",
        "职场效率",
        "职场效率与管理领域的资深实践者",
        "职场新人、管理者和需要提升工作效率的人",
        "工作流程、沟通协作、管理决策、效率工具和职场常见误区",
        "任务、会议、流程、角色关系、时间安排和结果对比",
    ),
    IndustryProfile(
        "automotive",
        "汽车交通",
        "汽车与交通领域的专业科普作者",
        "车主、驾驶者和关注出行安全的人",
        "汽车结构、驾驶原理、养护判断、交通规则和出行安全",
        "车辆结构、道路、交通参与者、仪表信息和安全关系",
    ),
    IndustryProfile(
        "daily_life",
        "生活常识",
        "生活科学与实用知识领域的科普作者",
        "希望解决日常问题的普通用户",
        "日常用品、生活现象、实用方法、消费判断和常见误区",
        "生活用品、家庭场景、操作步骤、前后对比和因果关系",
    ),
)

DEFAULT_INDUSTRY = INDUSTRY_PROFILES[0].key
INDUSTRY_CHOICES = tuple((profile.label, profile.key) for profile in INDUSTRY_PROFILES)


def resolve_industry(value: str = "") -> IndustryProfile:
    normalized = value.strip().casefold()
    for profile in INDUSTRY_PROFILES:
        if normalized in {profile.key.casefold(), profile.label.casefold()}:
            return profile
    return INDUSTRY_PROFILES[0]


def industry_prompt(value: str = "") -> str:
    profile = resolve_industry(value)
    return (
        f"当前行业：{profile.label}\n"
        f"专家身份：{profile.expert_role}\n"
        f"目标受众：{profile.audience}\n"
        f"内容重点：{profile.focus}"
    )
