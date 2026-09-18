#!/usr/bin/env node
/**
 * Jira 技能命令行入口。
 *
 * 用途：在没有 node_repl 等桌面工具的运行环境（服务器容器、codex exec）中，
 * 直接通过 shell 调用 jira.mjs 的导出能力完成取数、下载附件与写入评论。
 *
 * 用法：
 *   node scripts/jira-cli.mjs selftest                       # 令牌与连通性自检
 *   node scripts/jira-cli.mjs get <KEY|URL>                  # 输出紧凑 Markdown 摘要
 *   node scripts/jira-cli.mjs json <KEY|URL>                 # 输出规范化 JSON
 *   node scripts/jira-cli.mjs attachments <KEY|URL> <目录>    # 下载附件
 *   node scripts/jira-cli.mjs comment <KEY|URL> --file <文件> # 新增评论
 *   node scripts/jira-cli.mjs comment-update <KEY|URL> <评论ID> --file <文件>
 *   node scripts/jira-cli.mjs reviews <KEY|URL>              # 查找历史复审评论
 *   node scripts/jira-cli.mjs gate-get <KEY|URL>             # 读取门禁字段
 *   node scripts/jira-cli.mjs gate-set <KEY|URL> --file <JSON>
 *
 * 令牌来源：--token 参数、JIRA_TOKEN 环境变量，或 jira.mjs 默认查找的令牌文件。
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
  node scripts/jira-cli.mjs comment <KEY|URL> --file <文件> [--body <文本>]
  node scripts/jira-cli.mjs comment-update <KEY|URL> <评论ID> --file <文件>
  node scripts/jira-cli.mjs reviews <KEY|URL>
  node scripts/jira-cli.mjs gate-get <KEY|URL>
  node scripts/jira-cli.mjs gate-set <KEY|URL> --file <JSON文件>`;


/**
 * 解析命令行参数，支持 --key value 形式的选项与位置参数。
 */
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
 *
 * jira.mjs 的文件查找使用 Windows 风格路径拼接，在 Linux 容器中不适用，
 * 因此命令行入口单独实现一份跨平台版本作为兜底。
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


/**
 * 组装 jira.mjs 需要的调用选项，命令行优先于环境变量。
 */
function buildOptions(options) {
  const result = {};
  const fromFile = readTokenFile() || {};
  const token = options.token || process.env.JIRA_TOKEN || fromFile.token;
  const baseUrl = options["base-url"] || process.env.JIRA_BASE_URL || fromFile.baseUrl;
  if (token) result.token = String(token);
  if (baseUrl) result.baseUrl = String(baseUrl);
  return result;
}


/**
 * 读取评论或结果正文：优先 --file 文件内容，否则使用 --body 文本。
 */
function readBody(options) {
  if (typeof options.file === "string" && options.file) {
    return readFileSync(options.file, "utf8");
  }
  if (typeof options.body === "string") {
    return options.body;
  }
  throw new Error("缺少正文：请使用 --file <文件> 或 --body <文本> 传入");
}


/**
 * 校验位置参数数量，缺失时给出明确的使用提示。
 */
function requireArgs(positional, count, usage) {
  if (positional.length < count) {
    throw new Error(`参数不足：${usage}`);
  }
}


async function main() {
  const { positional, options } = parseArgs(process.argv.slice(2));
  const command = positional.shift();
  if (!command || command === "help" || options.help) {
    console.log(USAGE);
    return;
  }

  const callOptions = buildOptions(options);
  switch (command) {
    case "selftest": {
      const result = await jira.selftest(callOptions);
      // Jira 站点可能禁止普通账号访问 /myself；只要站点可达，仍应继续用 get 验证取数能力。
      const accountStep = (result.steps || []).find((item) => item.step === "校验令牌");
      if (accountStep && !accountStep.ok) {
        result.hint = "若“访问 Jira”步骤已成功，说明地址与网络可用；/myself 返回 401 通常只是该令牌无权访问账户接口，请改用 get <KEY|URL> 验证取数，不要因此判定令牌失效。";
      }
      console.log(JSON.stringify(result, null, 2));
      return;
    }
    case "get": {
      requireArgs(positional, 1, "get <KEY|URL>");
      const issue = await jira.getIssue(positional[0], callOptions);
      console.log(jira.renderIssueMarkdown(issue));
      return;
    }
    case "json": {
      requireArgs(positional, 1, "json <KEY|URL>");
      const issue = await jira.getIssue(positional[0], callOptions);
      console.log(JSON.stringify(issue, null, 2));
      return;
    }
    case "attachments": {
      requireArgs(positional, 2, "attachments <KEY|URL> <目录>");
      const saved = await jira.downloadAttachments(positional[0], positional[1], callOptions);
      console.log(JSON.stringify(saved, null, 2));
      return;
    }
    case "comment": {
      requireArgs(positional, 1, "comment <KEY|URL> --file <文件>");
      const body = readBody(options);
      const result = await jira.addComment(positional[0], body, callOptions);
      console.log(JSON.stringify({ ok: true, commentId: result && result.id }, null, 2));
      return;
    }
    case "comment-update": {
      requireArgs(positional, 2, "comment-update <KEY|URL> <评论ID> --file <文件>");
      const body = readBody(options);
      const result = await jira.updateComment(positional[0], positional[1], body, callOptions);
      console.log(JSON.stringify({ ok: true, commentId: result && result.id }, null, 2));
      return;
    }
    case "reviews": {
      requireArgs(positional, 1, "reviews <KEY|URL>");
      console.log(JSON.stringify(await jira.findPreviousReviews(positional[0], callOptions), null, 2));
      return;
    }
    case "gate-get": {
      requireArgs(positional, 1, "gate-get <KEY|URL>");
      console.log(JSON.stringify(await jira.getGateResult(positional[0], callOptions), null, 2));
      return;
    }
    case "gate-set": {
      requireArgs(positional, 1, "gate-set <KEY|URL> --file <JSON文件>");
      const payload = JSON.parse(readBody(options));
      console.log(JSON.stringify(await jira.setGateResult(positional[0], payload, callOptions), null, 2));
      return;
    }
    default:
      throw new Error(`未知命令：${command}\n${USAGE}`);
  }
}


main().catch((error) => {
  console.error(String((error && error.message) || error));
  process.exit(1);
});
