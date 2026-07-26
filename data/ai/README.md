# AI 助手配置目录

`data/ai/` 是 OmicHub 的 AI 助手配置根目录：

- `*.yaml`：内置 Agent 定义；每个 Agent 用 `prompt_file` 指向详细提示词，并用 `tool_packs` 绑定可用工具。
- `prompts/`：提示词注册表和各类系统提示词。根目录中的 `general.md`、`rnaseq.md` 等是 Agent 的权威提示词；`legacy_agents/` 仅保留迁移前版本供比对，不参与运行时加载。
- `tools/`：可复用的工具包 YAML；说明见 `tools/README.md`。
- `mas/`：多 Agent 编排能力与工具执行策略。
- `providers.yaml` 与 `provider_templates.yaml`：模型提供方配置和内置模板。
- `runtime_images.yaml` 与 `studio.yaml`：AI 工作台运行时镜像和沙盒配置。
- `skills/` 与 `skill_marketplace/`：已安装技能与内置技能市场。内置 Agent 在 YAML
  的 `skill_ids` 中声明并在技能市场存在的 Skill，会在启动初始化时自动安装、挂载到
  对应 Agent；技能正文随后由模型通过 `use_skill` 按需加载。

所有路径由 `src/omichub/core/config.py` 中的默认设置统一管理；可通过环境变量覆盖。
