# 技能目录

本目录存放可供「技能执行接口」调用的 Codex Skill。每个子目录就是一个技能，目录名即接口使用的 `skill_id`。

## 目录约定

```
skills/
  <skill_id>/
    SKILL.md          # 必需：技能定义、判定标准与执行步骤
    runtime.json      # 可选：覆盖提示词模板、超时时间、必填输入
    scripts/          # 可选：技能脚本
    references/       # 可选：判定清单等参考资料
```

`runtime.json` 支持的字段：

```json
{
  "prompt_template": "请使用 {skill_id} 处理 {jira_url}，技能目录 {skill_dir}",
  "timeout_seconds": 1800,
  "required_inputs": ["jira_url"]
}
```

未提供 `runtime.json` 时使用接口内置的默认模板，并把 `skill_id`、`jira_url`、`inputs` 一起交给 Codex。

## 已内置技能

- `jira-gate-1`：Jira 需求准入检查（G1），产出难度分级与达标结论，把逐项打标记的检查项清单写入需求单评论；不达标时流转到「评审中」并在评论里 @ 流转人；最后调用 `review-jira-songlizhi` 生成 OpenSpec 评审报告，作为附件上传到需求单（文件名以「宋立志」结尾）。
- `review-jira-songlizhi`：按 OpenSpec 好需求标准评审需求质量，产出 Markdown 报告。**对 Jira 只读**，由 `jira-gate-1` 调用；报告落盘后由 `jira-gate-1` 的 `scripts/jira-cli.mjs attach` 上传为附件。

## 服务器环境说明

服务器容器内没有 `node_repl` 等桌面工具，技能脚本需通过 shell 直接执行。`jira-gate-1` 已提供 `scripts/jira-cli.mjs` 作为命令行入口，其能力与桌面环境的 `node_repl` 通道一致。

技能目录在容器内只读挂载到 `/data/skills`，因此 `jira-gate-1` 统一用绝对路径 `/data/skills/review-jira-songlizhi` 调用另一个技能；`review-jira-songlizhi` 的产物落在技能工作区（`/data/skill-workspace/reports/`），不写进技能目录。`review-jira-songlizhi` 读 `JIRA_PAT`，容器里注入的是 `JIRA_TOKEN`，调用前按它的 `SKILL.md` 做凭据桥接。

技能所需的令牌（例如 Jira 访问令牌）不要提交到仓库，部署时通过挂载文件或环境变量注入。
