#!/usr/bin/env node
/**
 * jira-cli.mjs —— jira-code 技能的 Jira 命令行入口（只读单子 + 写评论）。
 *
 * 用法：
 *   node scripts/jira-cli.mjs selftest                    # 令牌与连通性自检
 *   node scripts/jira-cli.mjs get <KEY|URL>               # 输出紧凑 Markdown 摘要（含附件与评论列表）
 *   node scripts/jira-cli.mjs json <KEY|URL>              # 输出规范化 JSON
 *   node scripts/jira-cli.mjs attachments <KEY|URL> <目录> # 下载附件
 *   node scripts/jira-cli.mjs comments <KEY|URL>          # 列出评论（id + 作者 + 摘要），用于核对进度评论
 *   node scripts/jira-cli.mjs comment <KEY|URL> --file <文件>
 *   node scripts/jira-cli.mjs comment-update <KEY|URL> <评论ID> --file <文件>
 *
 * 依赖通道说明：本入口只暴露 jira-code 需要的读取与评论能力；
 * 流转（transition）与门禁字段（gate-set/gate-get）刻意不提供 —— 本技能不改单子状态、不写自定义字段。
 *
 * 令牌来源：--token 参数、JIRA_TOKEN 环境变量，或技能目录下的令牌文件。
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import * as jira from "./jira.mjs";


// 令牌文件候选名，与 jira.mjs 保持一致；这里用跨平台路径拼接，兼容 Linux 容器。
const TOKEN_FILE_NAMES = [".jira-token", ".jira-token.txt", "jira-token.txt"];


const USAGE = `用法：
  node scripts/jira-cli.mjs selftest
  node scripts/jira-cli.mjs get <KEY|URL>
  node scripts/jira-cli.mjs json <KEY|URL>
  node scripts/jira-cli.mjs attachments <KEY|URL> <目录>
  node scripts/jira-cli.mjs comments <KEY|URL>
  node scripts/jira-cli.mjs comment <KEY|URL> --file <文件> [--body <文本>]
  node scripts/jira-cli.mjs comment-update <KEY|URL> <评论ID> --file <文件>`;


/** 解析命令行参数，支持 --key value 形式的选项与位置参数。 */
function parseArgs(argv) {
  const positional = [];
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item.startsWith("--")) {
      const key = item.slice(2);
      const next = argv[index + 1];
      if (next === undefined || String(next).startsWith("--")) {
        options[key] = true;
      } else {
        options[key] = next;
        index += 1;
      }
    } else {
      positional.push(item);
    }
  }
  return { positional, options };
}


/**
 * 在技能目录及其上级目录查找令牌文件，返回解析后的 { token, baseUrl }。
 * jira.mjs 的文件查找使用 Windows 风格路径拼接，在 Linux 容器中不适用，因此这里单独兜底一份跨平台实现。
 */
function readTokenFile() {
  const skillDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const candidates = [];
  for (const name of TOKEN_FILE_NAMES) {
    candidates.push(resolve(skillDir, name));
    candidates.push(resolve(skillDir, "..", name));
  }
  for (const file of candidates) {
    if (!existsSync(file)) continue;
    const text = readFileSync(file, "utf8").trim();
    if (!text) continue;
    if (text.startsWith("{")) {
      try {
        const config = JSON.parse(text);
        if (config.token) return { token: String(config.token).trim(), baseUrl: config.baseUrl };
      } catch (error) {
        continue;
      }
      continue;
    }
    const firstLine = text.split(/\r?\n/).find((line) => line.trim()) || "";
    const token = firstLine.replace(/^JIRA_PAT\s*=\s*/i, "").trim();
    if (token) return { token };
  }
  return null;
}


/** 组装 jira.mjs 需要的调用选项，命令行优先于环境变量。 */
function buildOptions(options) {
  const fromFile = readTokenFile() || {};
  const token = options.token || process.env.JIRA_TOKEN || fromFile.token;
  const baseUrl = options["base-url"] || process.env.JIRA_BASE_URL || fromFile.baseUrl;
  const result = {};
  if (token) result.token = String(token);
  if (baseUrl) result.baseUrl = String(baseUrl);
  return result;
}


/** 读取评论正文：--file 优先，其次 --body。 */
function readBody(options) {
  if (options.file) return readFileSync(resolve(String(options.file)), "utf8");
  if (typeof options.body === "string" && options.body.trim()) return options.body;
  throw new Error("缺少评论正文：请使用 --file <文件> 或 --body <文本>");
}


/** 校验位置参数个数，不足时给出可读提示。 */
function requireArgs(positional, count, usage) {
  if (positional.length < count) throw new Error(`参数不足，用法：node scripts/jira-cli.mjs ${usage}`);
}


async function main() {
  const [command, ...rest] = process.argv.slice(2);
  const { positional, options } = parseArgs(rest);
  const callOptions = buildOptions(options);

  switch (command) {
    case "selftest": {
      const result = await jira.selftest(callOptions);
      const accountStep = (result.steps || []).find((item) => item.step === "校验令牌");
      if (accountStep && !accountStep.ok) {
        result.hint = "若「访问 Jira」步骤已成功，说明地址与网络可用；/myself 返回 401 通常只是该令牌无权访问账户接口，请改用 get <KEY|URL> 验证取数。";
      }
      process.stdout.write(JSON.stringify(result, null, 2) + "\n");
      return;
    }
    case "get": {
      requireArgs(positional, 1, "get <KEY|URL>");
      const issue = await jira.getIssue(positional[0], callOptions);
      process.stdout.write(jira.renderIssueMarkdown(issue) + "\n");
      return;
    }
    case "json": {
      requireArgs(positional, 1, "json <KEY|URL>");
      const issue = await jira.getIssue(positional[0], callOptions);
      process.stdout.write(JSON.stringify(issue, null, 2) + "\n");
      return;
    }
    case "attachments": {
      requireArgs(positional, 2, "attachments <KEY|URL> <目录>");
      const saved = await jira.downloadAttachments(positional[0], positional[1], callOptions);
      process.stdout.write(JSON.stringify(saved, null, 2) + "\n");
      return;
    }
    case "comments": {
      requireArgs(positional, 1, "comments <KEY|URL>");
      const issue = await jira.getIssue(positional[0], callOptions);
      const list = (issue.comments || []).map((item) => ({
        id: item.id,
        author: item.author,
        created: item.created,
        updated: item.updated,
        preview: String(item.body || "").replace(/\s+/g, " ").slice(0, 120),
      }));
      process.stdout.write(JSON.stringify({ key: issue.key, count: list.length, comments: list }, null, 2) + "\n");
      return;
    }
    case "comment": {
      requireArgs(positional, 1, "comment <KEY|URL> --file <文件>");
      const body = readBody(options);
      const result = await jira.addComment(positional[0], body, callOptions);
      process.stdout.write(JSON.stringify({ ok: true, commentId: result && result.id }, null, 2) + "\n");
      return;
    }
    case "comment-update": {
      requireArgs(positional, 2, "comment-update <KEY|URL> <评论ID> --file <文件>");
      const body = readBody(options);
      const result = await jira.updateComment(positional[0], positional[1], body, callOptions);
      process.stdout.write(JSON.stringify({ ok: true, commentId: result && result.id }, null, 2) + "\n");
      return;
    }
    default:
      throw new Error(`未知命令：${command}\n${USAGE}`);
  }
}


main().catch((error) => {
  process.stderr.write(`${String((error && error.message) || error)}\n`);
  process.exitCode = 1;
});
