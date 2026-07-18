"""Skill 域服务"""

from omichub.domain.skill.entities import Skill
from omichub.infrastructure.config.prompt_loader import render_prompt


class SkillDomainService:
    """技能域服务 — 纯领域逻辑"""

    @staticmethod
    def build_prompt(skills: list[Skill]) -> str:
        """将启用技能组装为 system prompt 注入文本"""
        if not skills:
            return ""
        content = "\n\n".join(
            f"## {skill.name}\n{skill.description}\n{skill.prompt}" for skill in skills
        )
        return render_prompt("skills.wrapper", skills=content)
