"""Skill 域服务"""

from omichub.domain.skill.entities import Skill


class SkillDomainService:
    """技能域服务 — 纯领域逻辑"""

    @staticmethod
    def build_prompt(skills: list[Skill]) -> str:
        """将启用技能组装为 system prompt 注入文本"""
        if not skills:
            return ""
        lines = ["\n\n# 可用技能"]
        for s in skills:
            lines.append(f"## {s.name}\n{s.description}\n{s.prompt}")
        return "\n".join(lines)
