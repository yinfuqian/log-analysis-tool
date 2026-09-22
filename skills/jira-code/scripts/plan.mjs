#!/usr/bin/env node
/**
 * plan.mjs —— 从「开发方案」附件中确定要改哪个 GitLab 仓库、基于哪个分支（确定性提取）。
 *
 * 用法：
 *   node scripts/plan.mjs find <附件目录> [--keyword 开发方案,技术方案]
 *   node scripts/plan.mjs candidates <方案文本文件> [--host https://code.in.wezhuiyi.com/]
 *
 * find        在附件目录里挑出「开发方案」文件（只按文件名与类型打分，不读内容），输出选中文件的绝对路径；
 *             没有候选时以退出码 1 结束，并在 stderr 说明目录里都有哪些文件。
 * candidates  在方案正文里扫出仓库与分支候选，输出 JSON：
 *             { ok, repos:[{url,host,path,raw,line,confidence}], branches:[{name,raw,line,confidence,preferred}],
 *               pairs:[{repo,branch,line,source}], reason }
 *             仓库候选或分支候选为空时 ok=false、退出码 1 —— 调用方据此中断流程，不许自己编仓库或分支。
 *
 * 设计口径：本脚本只做「候选提取」，不做判断。方案是自然语言，最终选哪一条由技能按 SKILL.md 的规则决定，
 * 但候选必须来自本脚本的输出，禁止凭空拼 URL 或分支名。
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { basename, extname, join, resolve } from "node:path";


// 开发方案的常见命名关键词，命中即视为候选（按顺序体现优先级：越靠前越像开发方案）。
const PLAN_KEYWORDS = [
  "开发方案", "开发计划", "技术方案", "技术设计", "实现方案", "设计方案",
  "概要设计", "详细设计", "技术实现", "dev-plan", "devplan", "develop-plan", "design", "方案",
];

// 可读文档类型排在前面，压缩包排在后面（压缩包要先解压再解析，优先级更低）。
const DOC_EXTENSIONS = new Set([".md", ".markdown", ".txt", ".docx", ".pdf", ".doc", ".html", ".htm", ".json", ".yaml", ".yml"]);
const ARCHIVE_EXTENSIONS = new Set([".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".xz", ".bz2"]);
const SKIP_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".mp4", ".mov", ".avi", ".svg"]);

// 行级关键词：命中说明这一行在讲仓库或分支，用于判定「像不像仓库地址」。
const REPO_LINE_KEYS = /(仓库|代码库|代码仓|代码仓库|仓库地址|代码地址|git\s*地址|gitlab|项目地址|服务名|模块|repo|repository)/i;
const BRANCH_LINE_KEYS = /(分支|branch|基线|基于|目标分支|源分支|开发分支|迭代分支|base)/i;
// 形如 code.in.wezhuiyi.com、gitlab.xxx.com 的主机名特征。
const GIT_HOST_HINT = /(gitlab|(^|\.)git\.|^code\.|^git-|gitee|github|bitbucket)/i;
// 明显不是代码仓库的主机（Jira、Wiki、文档站等），直接排除。
const NON_REPO_HOST = /(jira|confluence|wiki|docs\.|office|feishu|yuque|pan\.|drive\.)/i;

// 强特征分支前缀：出现即高置信度。
const PREFIXED_BRANCH = /(?:^|[^A-Za-z0-9._\/-])((?:feature|release|hotfix|bugfix|bugfix|develop|development|iter|sprint)\/[A-Za-z0-9._\/-]+)/g;
// 常见主干分支名：只有在带上「分支」上下文时才采纳，避免把普通英文单词当分支。
const PLAIN_BRANCH = /(?:^|[^A-Za-z0-9._\/-])(master|main|develop|development|dev|test|uat|beta|pre|prod|trunk)(?![A-Za-z0-9._\/-])/g;
// 显式写法：分支：xxx / 目标分支 xxx / 基于 xxx。
const EXPLICIT_BRANCH = /(?:目标分支|源分支|开发分支|迭代分支|基线分支|分支|branch|基线|基于|base)\s*[：:＝=]?\s*([A-Za-z0-9][A-Za-z0-9._\/-]{1,60})/i;
// 显式仓库写法（列表式）：仓库：xxx、代码库：xxx。
const EXPLICIT_REPO = /(?:仓库|代码库|代码仓|代码仓库|仓库路径|仓库名|git\s*地址|项目地址|服务名|模块名)\s*[：:＝=]\s*([A-Za-z0-9][A-Za-z0-9._\/-]{1,120})/i;
// 表格写法：| 仓库 | shop/cart-service | 或 | 分支 | release/2.4 |
const TABLE_REPO = /[|｜]\s*(?:仓库|代码库|代码仓|代码仓库|git\s*地址|项目)\s*[|｜]\s*([A-Za-z0-9][A-Za-z0-9._\/-]{1,120})/i;
const TABLE_BRANCH = /[|｜]\s*(?:分支|目标分支|基线分支|branch)\s*[|｜]\s*([A-Za-z0-9][A-Za-z0-9._\/-]{1,120})/i;
// 文档/代码后缀：只剔除这些明确是文件名的字符串；
// release/2.4、feature/2.4 这类带点号的分支名是合法写法，不能按「带点号 = 文件」一律排除。
const FILE_LIKE = /\.(?:md|markdown|txt|docx?|pdf|xlsx?|pptx?|png|jpe?g|gif|bmp|webp|svg|json|ya?ml|xml|html?|htm|csv|zip|rar|7z|tar|gz|tgz|java|kt|py|js|jsx|ts|tsx|vue|go|rs|c|cc|cpp|h|cs|rb|php|sql|sh|bat|ps1|gradle|properties|ini|conf|log)$/i;


/** 去掉中文/英文语境下常见的尾部标点。 */
function stripTail(text) {
  return String(text || "").replace(/[.,;:、。；：）)\]】》”"']+$/g, "").trim();
}


/** 取出 URL 的主机名，失败时返回空串。 */
function hostOf(url) {
  try {
    return new URL(url).host.toLowerCase();
  } catch (error) {
    return "";
  }
}


/** 把仓库地址规范化：砍掉网页端文件路径、统一 .git 结尾，方便直接 clone。 */
function normalizeRepoUrl(raw) {
  let url = stripTail(raw);
  // /-/blob/xxx、/-/tree/xxx 之类的网页路径要砍掉，只留仓库根。
  url = url.replace(/\/-\/(?:blob|tree|raw|commits|merge_requests|pipelines|issues|wikis|tags|releases).*$/i, "");
  url = url.replace(/\/(?:blob|tree|raw|commits|merge_requests)\/.*$/i, "");
  url = url.replace(/\.git.*$/i, ".git");
  url = url.replace(/\/+$/, "");
  if (/^https?:\/\//i.test(url) && !/\.git$/i.test(url)) url = `${url}.git`;
  return url;
}


/** 判断一个字符串是否像分支名（排除文件名、URL 片段、需求单号等）。 */
function looksLikeBranch(name) {
  const value = stripTail(name);
  if (!value || value.length > 60) return false;
  if (value.includes("..")) return false;
  if (/^https?:/i.test(value) || value.includes("@")) return false;
  if (FILE_LIKE.test(value)) return false;
  return true;
}


/** 判断一个字符串是否像仓库路径（group/repo 或单段仓库名）。 */
function looksLikeRepoPath(value) {
  const text = stripTail(value);
  if (!text || text.length > 120) return false;
  if (/^https?:/i.test(text) || text.includes("@")) return false;
  if (FILE_LIKE.test(text)) return false;
  return /^[A-Za-z0-9][A-Za-z0-9._-]*(?:\/[A-Za-z0-9][A-Za-z0-9._-]*)*$/.test(text);
}


/** 按行扫描方案正文，收集仓库、分支候选与二者在同一行/相邻行的配对关系。 */
function scan(text) {
  const lines = String(text || "").split(/\r?\n/);
  const repos = [];
  const branches = [];
  const repoByLine = new Map();
  const branchByLine = new Map();

  /** 记录一条仓库候选，按 url 或 path 去重。 */
  const pushRepo = (candidate) => {
    const key = candidate.url || candidate.path;
    if (!key) return;
    const hit = repos.find((item) => (item.url || item.path) === key);
    if (hit) {
      hit.count += 1;
      return;
    }
    const stored = { ...candidate, count: 1 };
    repos.push(stored);
    const list = repoByLine.get(stored.line) || [];
    list.push(stored);
    repoByLine.set(stored.line, list);
  };

  /** 记录一条分支候选，按名字去重。 */
  const pushBranch = (candidate) => {
    if (!candidate.name) return;
    const hit = branches.find((item) => item.name === candidate.name);
    if (hit) {
      hit.count += 1;
      hit.preferred = hit.preferred || candidate.preferred;
      return;
    }
    const stored = { ...candidate, count: 1 };
    branches.push(stored);
    const list = branchByLine.get(stored.line) || [];
    list.push(stored);
    branchByLine.set(stored.line, list);
  };

  lines.forEach((line, index) => {
    const lineNo = index + 1;
    const rawLine = line;
    // URL 片段从分支扫描的输入里剔除，避免把地址里的路径当成分支名。
    const lineWithoutUrl = rawLine.replace(/https?:\/\/\S+/g, " ");

    // 1) 仓库：http(s) 地址
    for (const match of rawLine.matchAll(/https?:\/\/[^\s)"'<>，。、；;）】\[\]]+/g)) {
      const raw = match[0];
      const host = hostOf(raw);
      if (!host || NON_REPO_HOST.test(host)) continue;
      const forced = REPO_LINE_KEYS.test(rawLine) || /\.git(\/|$)/i.test(raw);
      if (!forced && !GIT_HOST_HINT.test(host)) continue;
      pushRepo({
        url: normalizeRepoUrl(raw),
        host,
        raw,
        line: lineNo,
        confidence: /\.git(\/|$)/i.test(raw) || EXPLICIT_REPO.test(rawLine) ? "high" : "medium",
      });
    }

    // 2) 仓库：git@host:group/repo.git（SSH）
    for (const match of rawLine.matchAll(/\bgit@[^\s:：,，;；)）]+:[^\s,，;；)）]+/g)) {
      const raw = stripTail(match[0]);
      pushRepo({ url: raw, host: raw.split("@")[1]?.split(":")[0]?.toLowerCase() || "", raw, line: lineNo, confidence: "high" });
    }

    // 3) 仓库：显式「仓库：group/repo」或表格写法
    if (!/https?:\/\//.test(rawLine)) {
      const explicit = rawLine.match(EXPLICIT_REPO) || rawLine.match(TABLE_REPO);
      const value = explicit && explicit[1];
      if (value && looksLikeRepoPath(value)) {
        const path = stripTail(value).replace(/\.git$/i, "");
        pushRepo({ path, raw: value, line: lineNo, confidence: "high" });
      }
    }

    // 4) 分支：显式写法优先
    const explicitBranch = rawLine.match(EXPLICIT_BRANCH) || rawLine.match(TABLE_BRANCH);
    if (explicitBranch && looksLikeBranch(explicitBranch[1])) {
      pushBranch({
        name: stripTail(explicitBranch[1]),
        raw: explicitBranch[0].trim(),
        line: lineNo,
        confidence: "high",
        preferred: /(目标分支|基线|基于|base)/i.test(rawLine),
      });
    }

    // 5) 分支：feature/release 之类的前缀特征（不要求带「分支」字样）
    for (const match of lineWithoutUrl.matchAll(PREFIXED_BRANCH)) {
      if (!looksLikeBranch(match[1])) continue;
      pushBranch({ name: match[1], raw: match[0].trim(), line: lineNo, confidence: "high", preferred: false });
    }

    // 6) 分支：主干名（master/main/develop 等）只在有分支上下文时采纳
    if (BRANCH_LINE_KEYS.test(lineWithoutUrl)) {
      for (const match of lineWithoutUrl.matchAll(PLAIN_BRANCH)) {
        pushBranch({ name: match[1], raw: match[0].trim(), line: lineNo, confidence: "medium", preferred: false });
      }
    }
  });

  // 7) 配对：同一行同时出现仓库与分支 → 直接配对；仓库行的下一行只有分支 → 相邻配对。
  const pairs = [];
  const addPair = (repo, branch, line, source) => {
    const key = `${repo.url || repo.path}#${branch.name}`;
    if (pairs.some((item) => item.key === key)) return;
    pairs.push({ key, repo: repo.url || repo.path, repoRaw: repo.raw, branch: branch.name, line, source });
  };
  for (const [lineNo, lineRepos] of [...repoByLine.entries()].sort((a, b) => a[0] - b[0])) {
    const sameLine = branchByLine.get(lineNo) || [];
    for (const repo of lineRepos) {
      for (const branch of sameLine) addPair(repo, branch, lineNo, "same-line");
    }
    if (lineRepos.length === 1 && !sameLine.length) {
      const nextLine = branchByLine.get(lineNo + 1) || [];
      const nextHasRepo = repoByLine.has(lineNo + 1);
      if (!nextHasRepo && nextLine.length === 1) addPair(lineRepos[0], nextLine[0], lineNo, "neighbor-line");
    }
  }

  return {
    repos: repos.map(({ count, ...item }) => ({ ...item, count })),
    branches: branches.map(({ count, ...item }) => ({ ...item, count })),
    pairs: pairs.map(({ key, ...item }) => item),
  };
}


/** find 子命令：在附件目录里挑出开发方案文件。 */
function pickPlanFile(directory, keywords) {
  const dir = resolve(directory);
  const stat = statSync(dir, { throwIfNoEntry: false });
  if (!stat || !stat.isDirectory()) throw new Error(`附件目录不存在：${dir}`);

  const entries = readdirSync(dir).filter((name) => {
    const target = join(dir, name);
    try {
      const info = statSync(target);
      if (!info.isFile()) return false;
      return !SKIP_EXTENSIONS.has(extname(name).toLowerCase());
    } catch (error) {
      return false;
    }
  });

  const scored = [];
  for (const name of entries) {
    const lower = name.toLowerCase();
    const extension = extname(lower);
    const keywordIndex = keywords.findIndex((word) => lower.includes(String(word).toLowerCase()));
    if (keywordIndex === -1) continue;
    // 关键词越靠前越像开发方案；同关键词下文档优于压缩包，再按文件名排序保证结果稳定。
    const typeRank = DOC_EXTENSIONS.has(extension) ? 0 : ARCHIVE_EXTENSIONS.has(extension) ? 1 : 2;
    scored.push({ name, keywordIndex, typeRank, path: join(dir, name) });
  }
  scored.sort((a, b) => a.keywordIndex - b.keywordIndex || a.typeRank - b.typeRank || a.name.localeCompare(b.name));

  return { picked: scored.length ? scored[0] : null, entries, scored };
}


/** 解析命令行参数，支持位置参数与 --key value。 */
function parseArgs(argv) {
  const positional = [];
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item.startsWith("--")) {
      const next = argv[index + 1];
      if (next === undefined || String(next).startsWith("--")) {
        options[item.slice(2)] = true;
      } else {
        options[item.slice(2)] = next;
        index += 1;
      }
    } else {
      positional.push(item);
    }
  }
  return { positional, options };
}


function main() {
  const [command, ...rest] = process.argv.slice(2);
  const { positional, options } = parseArgs(rest);

  if (command === "find") {
    const directory = positional[0];
    if (!directory) throw new Error("用法：node scripts/plan.mjs find <附件目录> [--keyword 开发方案,技术方案]");
    const keywords = options.keyword
      ? String(options.keyword).split(",").map((item) => item.trim()).filter(Boolean)
      : PLAN_KEYWORDS;
    const { picked, entries, scored } = pickPlanFile(directory, keywords);
    if (!picked) {
      const detail = entries.length ? entries.join("、") : "（目录为空）";
      process.stdout.write(JSON.stringify({ ok: false, reason: "attachment-not-found", directory: resolve(directory), entries }, null, 2) + "\n");
      throw new Error(`附件目录里没有开发方案文件（关键词：${keywords.slice(0, 6).join("/")}）；目录内现有：${detail}`);
    }
    process.stdout.write(JSON.stringify({ ok: true, path: picked.path, name: picked.name, candidates: scored.map((item) => item.name) }, null, 2) + "\n");
    return;
  }

  if (command === "candidates") {
    const file = positional[0];
    if (!file) throw new Error("用法：node scripts/plan.mjs candidates <方案文本文件> [--host <GitLab 地址>]");
    const text = readFileSync(resolve(file), "utf8");
    const result = scan(text);
    const baseHost = options.host ? hostOf(String(options.host).includes("://") ? String(options.host) : `https://${options.host}`) : "";
    const payload = {
      ok: result.repos.length > 0 && result.branches.length > 0,
      textSource: resolve(file),
      baseHost: baseHost || null,
      repos: result.repos,
      branches: result.branches,
      pairs: result.pairs,
    };
    if (!result.repos.length) payload.reason = "repo-not-found";
    else if (!result.branches.length) payload.reason = "branch-not-found";
    process.stdout.write(JSON.stringify(payload, null, 2) + "\n");
    if (!payload.ok) {
      const message = !result.repos.length
        ? "开发方案里没有找到 GitLab 仓库信息"
        : "开发方案里没有找到分支信息";
      throw new Error(`${message}（脚本只认方案正文里的地址或「仓库：/分支：」写法，不要自己编）`);
    }
    return;
  }

  throw new Error("用法：node scripts/plan.mjs <find|candidates> ...");
}


try {
  main();
} catch (error) {
  process.stderr.write(`[开发方案解析失败] ${(error && error.message) || error}\n`);
  process.exitCode = 1;
}
