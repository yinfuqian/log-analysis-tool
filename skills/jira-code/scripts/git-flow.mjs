#!/usr/bin/env node
/**
 * git-flow.mjs —— jira-code 技能专用的 Git 操作入口。
 *
 * 用法：
 *   node scripts/git-flow.mjs creds
 *   node scripts/git-flow.mjs prepare --repo <URL|group/repo> --base <基线分支> --key <KEY> [--dir <检出目录>] [--base-url <GitLab地址>]
 *   node scripts/git-flow.mjs status  [--dir <检出目录>]
 *   node scripts/git-flow.mjs commit  --dir <检出目录> (--message <提交信息> | --message-file <文件>)
 *   node scripts/git-flow.mjs push    --dir <检出目录> [--force-with-lease]
 *   node scripts/git-flow.mjs cleanup --dir <检出目录> [--key <KEY>] [--verify-remote] [--force]
 *
 * 硬约束（对应 SKILL.md 的凭据与安全口径）：
 *   1. 令牌只作为本次命令的临时参数传给 git，**不写进 .git/config**，也不出现在任何输出里；
 *      仓库的 origin 始终保存不含凭据的干净地址。
 *   2. feature 分支名由本脚本按 `feature/<KEY>` 生成，避免各处口径不一致。
 *   3. 只在确有改动时提交；默认只做普通 push，禁止用 force 覆盖远端（--force-with-lease 需显式传入）。
 *   4. 推送成功后用 cleanup 删除本地检出目录，不在工作区留代码副本；cleanup 只认本技能 prepare 写下的标记，
 *      并在仍有未推送提交时拒绝删除，避免把没推上去的代码删掉。
 */

import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, join, parse as parsePath, resolve } from "node:path";
import { fileURLToPath } from "node:url";


const FEATURE_PREFIX = "feature/";
const DEFAULT_AUTHOR_NAME = "jira-code";
const DEFAULT_AUTHOR_EMAIL = "jira-code@noreply.local";
// 检出目录的平级标记文件：记录这次检出由本技能创建，cleanup 只删带标记的目录。
const CHECKOUT_MARKER_SUFFIX = ".jira-code-checkout.json";
// 远端地址在输出里一律脱敏：//user:pass@ 只保留 //***@
const CREDENTIAL_IN_URL = /(https?:\/\/)[^/@\s]+@/gi;


/** 读取环境变量，缺失时返回空字符串。 */
function env(name) {
  const value = process.env[name];
  return value ? String(value).trim() : "";
}


/** 检出目录对应的标记文件路径：与检出目录平级，避免被 git add -A 带进提交。 */
function markerPathOf(dir) {
  return join(dirname(dir), `${basename(dir)}${CHECKOUT_MARKER_SUFFIX}`);
}


/** 写入/刷新检出标记，cleanup 依据它判断目录确实是本技能拉下来的。 */
function writeCheckoutMarker(dir, payload) {
  const target = markerPathOf(dir);
  const body = { skill: "jira-code", markerVersion: 1, dir, createdAt: new Date().toISOString(), ...payload };
  writeFileSync(target, `${JSON.stringify(body, null, 2)}\n`, "utf8");
  return target;
}


/** 把输出里的凭据清干净，再交给日志或 JSON。 */
export function redact(text, secrets = []) {
  let output = String(text == null ? "" : text).replace(CREDENTIAL_IN_URL, "$1***@");
  for (const secret of secrets) {
    if (secret && String(secret).length >= 4) output = output.split(String(secret)).join("***");
  }
  return output;
}


/** Git 操作失败时抛出的错误，带可读 reason 便于写进 Jira 评论。 */
export class GitFlowError extends Error {
  constructor(message, reason, status) {
    super(message);
    this.name = "GitFlowError";
    this.reason = reason || "unknown";
    this.status = status;
  }
}


/** 把 git 的报错文本归类成可读原因，便于在评论里说明失败环节。 */
export function classifyGitError(text) {
  const value = String(text || "").toLowerCase();
  if (/could not read username|authentication failed|invalid username or password|http 401|403 forbidden|permission denied|access denied/.test(value)) {
    return "auth-failed";
  }
  if (/protected branch|pre-receive hook declined|you are not allowed to push|push is not allowed/.test(value)) {
    return "push-rejected";
  }
  if (/non-fast-forward|fetch first|updates were rejected/.test(value)) {
    return "non-fast-forward";
  }
  if (/could not resolve host|failed to connect|connection timed out|network is unreachable|operation timed out|ssl/.test(value)) {
    return "network";
  }
  if (/repository not found|does not exist|not found/.test(value)) {
    return "repo-not-found";
  }
  return "unknown";
}


/**
 * 解析 GitLab 凭据。优先级：GITLAB_PRIVATE_TOKEN（GitLab 约定用户名 oauth2，可用 GITLAB_USER 覆盖）
 * 高于 GIT_USER + GIT_PASSWORD；都没有时返回 mode=none，仍允许走本机已有的 credential helper。
 */
export function resolveCredential() {
  const token = env("GITLAB_PRIVATE_TOKEN");
  const user = env("GIT_USER");
  const password = env("GIT_PASSWORD");
  const baseUrl = env("GIT_BASE_URL");
  if (token) {
    return { mode: "private-token", username: env("GITLAB_USER") || user || "oauth2", token, baseUrl };
  }
  if (user && password) {
    return { mode: "user-password", username: user, password, baseUrl };
  }
  return { mode: "none", baseUrl };
}


/** 把不带凭据的仓库地址补上凭据，仅用于本次 git 命令。 */
function withCredential(url, credential) {
  if (!/^https?:\/\//i.test(url)) return url;
  if (credential.mode === "none") return url;
  try {
    const parsed = new URL(url);
    const secret = credential.mode === "private-token" ? credential.token : credential.password;
    parsed.username = encodeURIComponent(credential.username);
    parsed.password = encodeURIComponent(secret);
    return parsed.toString();
  } catch (error) {
    return url;
  }
}


/** 该凭据里的所有明文，用于日志脱敏。 */
function credentialSecrets(credential) {
  return [credential.token, credential.password].filter(Boolean);
}


/**
 * 把方案里写的仓库标识规范化成可 clone 的干净地址。
 * 支持三种输入：完整 http(s) 地址、git@ SSH 地址、以及「group/repo」这种路径写法（需要 GIT_BASE_URL 补主机）。
 */
export function resolveRepoUrl(input, options = {}) {
  const raw = String(input || "").trim();
  if (!raw) throw new GitFlowError("缺少仓库地址", "repo-missing");
  if (/^git@[^:]+:/i.test(raw) || /^ssh:\/\//i.test(raw)) {
    return { url: raw, label: raw, transport: "ssh" };
  }
  // 本地路径或 file:// 地址（CI 演练、离线验证用）：原样交给 git，不再补主机。
  if (/^file:\/\//i.test(raw) || /^[A-Za-z]:[\\/]/.test(raw) || /^[\\/]/.test(raw) || /^\.{1,2}[\\/]/.test(raw)) {
    return { url: raw, label: raw, transport: "local" };
  }
  if (/^https?:\/\//i.test(raw)) {
    const url = raw.replace(/\.git.*$/i, ".git").replace(/\/+$/, "");
    return { url: /\.git$/i.test(url) ? url : `${url}.git`, label: url, transport: "https" };
  }
  // 路径写法：用 GIT_BASE_URL（或 --base-url）补主机。
  const baseUrl = String(options.baseUrl || "").trim().replace(/\/+$/, "");
  if (!baseUrl) {
    throw new GitFlowError(
      `方案里只写了仓库路径「${raw}」，需要 GIT_BASE_URL 或 --base-url 指定 GitLab 地址才能 clone`,
      "repo-needs-base-url",
    );
  }
  const base = /^https?:\/\//i.test(baseUrl) ? baseUrl : `https://${baseUrl}`;
  const path = raw.replace(/^\/+/, "").replace(/\.git$/i, "");
  return { url: `${base}/${path}.git`, label: `${base}/${path}.git`, transport: "https" };
}


/**
 * 执行 git 命令。GIT_TERMINAL_PROMPT=0 保证没有凭据时立即失败，而不是卡在交互式输入上。
 * 关闭 credential.helper 是为了避免机器上配置的图形化助手弹窗或缓存到错误凭据。
 */
function git(args, options = {}) {
  const credential = options.credential || null;
  const secrets = credential ? credentialSecrets(credential) : [];
  const result = spawnSync("git", args, {
    cwd: options.cwd,
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
    env: {
      ...process.env,
      GIT_TERMINAL_PROMPT: "0",
      // 提交作者固定为技能标识，避免容器内没有全局 git 身份导致 commit 失败。
      GIT_AUTHOR_NAME: env("GIT_AUTHOR_NAME") || DEFAULT_AUTHOR_NAME,
      GIT_AUTHOR_EMAIL: env("GIT_AUTHOR_EMAIL") || DEFAULT_AUTHOR_EMAIL,
      GIT_COMMITTER_NAME: env("GIT_COMMITTER_NAME") || env("GIT_AUTHOR_NAME") || DEFAULT_AUTHOR_NAME,
      GIT_COMMITTER_EMAIL: env("GIT_COMMITTER_EMAIL") || env("GIT_AUTHOR_EMAIL") || DEFAULT_AUTHOR_EMAIL,
    },
  });
  const stdout = redact(result.stdout || "", secrets);
  const stderr = redact(result.stderr || "", secrets);
  if (result.error) {
    throw new GitFlowError(`无法执行 git：${result.error.message}`, "git-unavailable");
  }
  if (result.status !== 0 && !options.allowFail) {
    const detail = (stderr || stdout).trim().slice(0, 800) || `git ${args[0]} 退出码 ${result.status}`;
    throw new GitFlowError(detail, classifyGitError(detail), result.status);
  }
  return { status: result.status, stdout, stderr };
}


/** 检出目录下的 .git 是否已初始化。 */
function isRepo(dir) {
  return existsSync(resolve(dir, ".git"));
}


/**
 * 拉取基线分支。容器内 git 支持 --no-write-fetch-head（不把远端地址写进 FETCH_HEAD），
 * 老版本 git（例如 2.28）会以用法错误拒绝，此时退回普通 fetch 并在事后擦掉 FETCH_HEAD 里的凭据。
 */
function fetchBranch(dir, authUrl, base, credential) {
  const refspec = `+refs/heads/${base}:refs/remotes/origin/${base}`;
  const common = ["-c", "credential.helper=", "fetch", "--no-tags", "--prune"];
  try {
    return git([...common, "--no-write-fetch-head", authUrl, refspec], { cwd: dir, credential });
  } catch (error) {
    if (error instanceof GitFlowError && /no-write-fetch-head|unknown option|usage:/i.test(error.message)) {
      const result = git([...common, authUrl, refspec], { cwd: dir, credential });
      scrubFetchHead(dir, credential);
      return result;
    }
    throw error;
  }
}


/** 把 FETCH_HEAD 里可能残留的带凭据地址擦掉；没有该文件时静默跳过。 */
function scrubFetchHead(dir, credential) {
  const target = resolve(dir, ".git", "FETCH_HEAD");
  if (!existsSync(target)) return;
  try {
    const text = readFileSync(target, "utf8");
    const cleaned = redact(text, credentialSecrets(credential));
    if (cleaned !== text) writeFileSync(target, cleaned, "utf8");
  } catch (error) {
    // 擦除失败不影响主流程，但要在 stderr 留痕，便于排查凭据落盘问题。
    process.stderr.write(`[git-flow] 清理 FETCH_HEAD 失败：${redact(error.message, credentialSecrets(credential))}\n`);
  }
}


/** 列出远端分支名（用于基线分支不存在时给出可读提示）。 */
function listRemoteBranches(authUrl, credential) {
  try {
    const result = git(["-c", "credential.helper=", "ls-remote", "--heads", authUrl], { cwd: undefined, credential });
    return result.stdout
      .split(/\r?\n/)
      .map((line) => line.split("refs/heads/")[1])
      .filter(Boolean);
  } catch (error) {
    return [];
  }
}


/**
 * 检出目录的代码快照：分支、改动文件数、最近一次提交。
 * 心跳脚本复用它，让 Jira 里的进度评论带上真实的代码进展，而不是只有一句「进行中」。
 */
export function snapshot(dir) {
  const target = resolve(dir);
  if (!isRepo(target)) return { ok: false, reason: "no-repo", dir: target };
  try {
    const branch = git(["rev-parse", "--abbrev-ref", "HEAD"], { cwd: target, allowFail: true }).stdout.trim();
    const statusText = git(["status", "--porcelain"], { cwd: target, allowFail: true }).stdout.trim();
    const changedFiles = statusText ? statusText.split(/\r?\n/).filter(Boolean).length : 0;
    const head = git(["log", "-1", "--pretty=%h %s"], { cwd: target, allowFail: true }).stdout.trim();
    const commits = git(["rev-list", "--count", "HEAD"], { cwd: target, allowFail: true }).stdout.trim();
    return { ok: true, dir: target, branch, changedFiles, head, commits: Number(commits) || 0 };
  } catch (error) {
    return { ok: false, reason: "git-error", dir: target, message: redact(error.message) };
  }
}


/** prepare：初始化/复用检出目录，按基线分支创建（或重置）feature 分支。 */
function prepare(options) {
  const credential = resolveCredential();
  const repo = resolveRepoUrl(options.repo, { baseUrl: options["base-url"] || credential.baseUrl });
  const key = String(options.key || "").trim().toUpperCase();
  const feature = String(options.feature || "").trim() || (key ? `${FEATURE_PREFIX}${key}` : "");
  const base = String(options.base || "").trim();
  if (!feature) throw new GitFlowError("缺少 --key（用于生成 feature/<KEY> 分支名）或 --feature", "feature-missing");
  if (!base) throw new GitFlowError("缺少 --base 基线分支", "base-missing");
  if (base === feature) throw new GitFlowError("基线分支与 feature 分支同名，拒绝继续", "base-equals-feature");

  const dir = resolve(options.dir || "repo");
  const authUrl = withCredential(repo.url, credential);
  const secrets = credentialSecrets(credential);

  if (!isRepo(dir)) {
    mkdirSync(dir, { recursive: true });
    git(["-c", "init.defaultBranch=main", "init", "--quiet", dir]);
  }
  // origin 始终保存干净地址：后面所有网络操作都显式传 authUrl，不依赖 origin 里的凭据。
  const currentRemote = git(["remote", "get-url", "origin"], { cwd: dir, allowFail: true });
  if (currentRemote.status === 0) {
    if (currentRemote.stdout.trim() !== repo.url) git(["remote", "set-url", "origin", repo.url], { cwd: dir });
  } else {
    git(["remote", "add", "origin", repo.url], { cwd: dir });
  }

  try {
    fetchBranch(dir, authUrl, base, credential);
  } catch (error) {
    const branches = listRemoteBranches(authUrl, credential);
    const detail = redact(error.message, secrets);
    if (branches.length) {
      throw new GitFlowError(
        `拉取基线分支「${base}」失败（${error.reason}）：${detail}\n远端现有分支（最多 30 个）：${branches.slice(0, 30).join("、")}`,
        error.reason === "unknown" ? "base-branch-not-found" : error.reason,
      );
    }
    throw new GitFlowError(`拉取基线分支「${base}」失败（${error.reason}）：${detail}`, error.reason);
  }

  git(["checkout", "--quiet", "-B", feature, `refs/remotes/origin/${base}`], { cwd: dir });
  // 本地身份写进仓库配置，让 agent 之后直接在检出目录里 commit 也能成功。
  git(["config", "user.name", env("GIT_AUTHOR_NAME") || DEFAULT_AUTHOR_NAME], { cwd: dir });
  git(["config", "user.email", env("GIT_AUTHOR_EMAIL") || DEFAULT_AUTHOR_EMAIL], { cwd: dir });
  scrubFetchHead(dir, credential);
  // 记下这次检出：cleanup 靠它确认目录是本技能拉的，并在推送后把它删干净。
  const marker = writeCheckoutMarker(dir, { key, feature, base, repo: repo.url });

  const head = git(["rev-parse", "--short", "HEAD"], { cwd: dir, allowFail: true }).stdout.trim();
  return {
    ok: true,
    dir,
    marker,
    repo: repo.url,
    transport: repo.transport,
    credential: credential.mode,
    base,
    baseRef: `origin/${base}`,
    feature,
    head,
    snapshot: snapshot(dir),
  };
}


/** commit：只在确有改动时提交，避免产生空提交。 */
function commit(options) {
  const dir = resolve(options.dir || "repo");
  if (!isRepo(dir)) throw new GitFlowError(`检出目录不是 git 仓库：${dir}`, "no-repo");
  let message = String(options.message || "").trim();
  if (options["message-file"]) {
    message = readFileSync(resolve(String(options["message-file"])), "utf8").trim();
  }
  if (!message) throw new GitFlowError("缺少提交信息（--message 或 --message-file）", "message-missing");

  // -uall 让未跟踪目录展开成具体文件，便于在 Jira 评论里如实列出改动清单。
  const before = git(["status", "--porcelain", "-uall"], { cwd: dir }).stdout.trim();
  if (!before) {
    return { ok: true, committed: false, reason: "no-changes", dir, snapshot: snapshot(dir) };
  }
  git(["add", "-A"], { cwd: dir });
  const staged = git(["diff", "--cached", "--quiet"], { cwd: dir, allowFail: true });
  if (staged.status === 0) {
    return { ok: true, committed: false, reason: "no-staged-changes", dir, snapshot: snapshot(dir) };
  }
  git(["commit", "--quiet", "-m", message], { cwd: dir });
  const head = git(["rev-parse", "--short", "HEAD"], { cwd: dir }).stdout.trim();
  const files = before.split(/\r?\n/).filter(Boolean).map((line) => line.slice(3).trim());
  return { ok: true, committed: true, dir, head, files: files.slice(0, 40), fileCount: files.length, snapshot: snapshot(dir) };
}


/** push：把当前分支推到远端的同名分支（不做强推）。 */
function push(options) {
  const credential = resolveCredential();
  const dir = resolve(options.dir || "repo");
  if (!isRepo(dir)) throw new GitFlowError(`检出目录不是 git 仓库：${dir}`, "no-repo");
  const remoteUrl = git(["remote", "get-url", "origin"], { cwd: dir, allowFail: true }).stdout.trim();
  const origin = resolveRepoUrl(remoteUrl || options.repo || "", { baseUrl: credential.baseUrl });
  const branch = git(["rev-parse", "--abbrev-ref", "HEAD"], { cwd: dir }).stdout.trim();
  if (!branch || branch === "HEAD") throw new GitFlowError("当前处于游离 HEAD，无法推送", "detached-head");

  const args = ["-c", "credential.helper=", "push"];
  if (options["force-with-lease"]) args.push("--force-with-lease");
  args.push(withCredential(origin.url, credential), `HEAD:refs/heads/${branch}`);
  try {
    git(args, { cwd: dir, credential });
  } catch (error) {
    throw new GitFlowError(`推送分支「${branch}」失败（${error.reason}）：${error.message}`, error.reason);
  }
  // push 走的是显式 URL，不会自动更新 remote-tracking ref；这里补一条本地记录，
  // 让 cleanup 的「是否还有未推送提交」判断与后续 fetch 都能看到远端已有的 feature 分支。
  git(["update-ref", `refs/remotes/origin/${branch}`, "HEAD"], { cwd: dir, allowFail: true });
  return {
    ok: true,
    pushed: true,
    dir,
    repo: origin.url,
    branch,
    head: git(["rev-parse", "--short", "HEAD"], { cwd: dir, allowFail: true }).stdout.trim(),
  };
}


/** 本地有、远端没有的提交：非空说明还有代码没推上去。 */
function unpushedCommits(dir) {
  const result = git(["log", "--branches", "--not", "--remotes", "--oneline"], { cwd: dir, allowFail: true });
  return result.stdout.trim() ? result.stdout.trim().split(/\r?\n/).filter(Boolean) : [];
}


/** 未提交的改动（含未跟踪文件）：非空说明写好的代码还没进提交。 */
function uncommittedChanges(dir) {
  const result = git(["status", "--porcelain", "-uall"], { cwd: dir, allowFail: true });
  return result.stdout.trim() ? result.stdout.trim().split(/\r?\n/).filter(Boolean) : [];
}


/** 远端是否已存在该分支，用于确认代码真的推上去了。 */
function remoteHasBranch(authUrl, branch, credential) {
  try {
    const result = git(
      ["-c", "credential.helper=", "ls-remote", "--heads", authUrl, `refs/heads/${branch}`],
      { credential },
    );
    return result.stdout.includes(`refs/heads/${branch}`);
  } catch (error) {
    return false;
  }
}


/**
 * cleanup：删除本次拉下来的检出目录，不在工作区留代码副本。
 * 只删本技能 prepare 写过标记的目录；仍有未推送提交或未提交改动时拒绝删除，避免误删没进远端的代码。
 */
function cleanup(options) {
  if (!options.dir) throw new GitFlowError("缺少 --dir（要删除的检出目录）", "dir-missing");
  const dir = resolve(String(options.dir));
  const key = String(options.key || "").trim().toUpperCase();
  const markerPath = markerPathOf(dir);

  if (!existsSync(markerPath)) {
    throw new GitFlowError(
      `拒绝删除 ${dir}：没有找到本技能的检出标记 ${markerPath}，只允许删除 jira-code 自己拉的检出目录`,
      "not-managed-checkout",
    );
  }
  let marker;
  try {
    marker = JSON.parse(readFileSync(markerPath, "utf8"));
  } catch (error) {
    throw new GitFlowError(`检出标记无法解析：${markerPath}`, "bad-marker");
  }
  // 标记里记着当初创建的绝对路径，二者必须一致，避免路径被换成别处。
  if (resolve(String(marker.dir || "")) !== dir) {
    throw new GitFlowError(`检出标记与 --dir 不一致（标记：${marker.dir}），拒绝删除`, "dir-mismatch");
  }
  if (key && String(marker.key || "").toUpperCase() !== key) {
    throw new GitFlowError(`检出标记属于 ${marker.key}，与 --key ${key} 不一致，拒绝删除`, "key-mismatch");
  }
  // 兜底防护：绝不删除文件系统根目录或它下面的一级目录。
  const root = parsePath(dir).root;
  if (!dir || dir === root || dirname(dir) === root) {
    throw new GitFlowError(`拒绝删除可疑路径：${dir}`, "unsafe-path");
  }

  const exists = existsSync(dir);
  let unpushed = [];
  let dirty = [];
  if (exists && isRepo(dir)) {
    unpushed = unpushedCommits(dir);
    dirty = uncommittedChanges(dir);
    if (!options.force && unpushed.length) {
      throw new GitFlowError(
        `拒绝删除 ${dir}：还有 ${unpushed.length} 个提交没推到远端（例如 ${unpushed[0]}），先推送或确认后再加 --force`,
        "unpushed-commits",
      );
    }
    if (!options.force && dirty.length) {
      throw new GitFlowError(
        `拒绝删除 ${dir}：还有 ${dirty.length} 处未提交改动（例如 ${dirty[0]}），先提交推送或确认后再加 --force`,
        "uncommitted-changes",
      );
    }
    if (options["verify-remote"]) {
      const credential = resolveCredential();
      const remoteUrl = git(["remote", "get-url", "origin"], { cwd: dir, allowFail: true }).stdout.trim();
      const origin = resolveRepoUrl(remoteUrl || marker.repo || "", { baseUrl: credential.baseUrl });
      const branch = String(marker.feature || "").trim() || git(["rev-parse", "--abbrev-ref", "HEAD"], { cwd: dir, allowFail: true }).stdout.trim();
      if (!branch) throw new GitFlowError(`无法确定要核对的分支名：${dir}`, "branch-unknown");
      if (!remoteHasBranch(withCredential(origin.url, credential), branch, credential)) {
        throw new GitFlowError(
          `拒绝删除 ${dir}：远端还没有分支 ${branch}，说明代码没推上去，保留本地便于排查`,
          "remote-branch-missing",
        );
      }
    }
  }

  // 目录与标记一起删：先删目录，成功后再删标记，避免删一半留下孤儿标记。
  if (exists) rmSync(dir, { recursive: true, force: true, maxRetries: 3 });
  rmSync(markerPath, { force: true });
  return {
    ok: true,
    removed: true,
    dir,
    marker: markerPath,
    existed: exists,
    key: marker.key || null,
    feature: marker.feature || null,
    removedUnpushedCommits: options.force ? unpushed.length : 0,
    removedUncommittedChanges: options.force ? dirty.length : 0,
  };
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
  const { options } = parseArgs(rest);
  const usage = "用法：node scripts/git-flow.mjs <creds|prepare|status|commit|push|cleanup> [选项]";

  switch (command) {
    case "creds": {
      const credential = resolveCredential();
      // 只回显凭据来源与用户名，绝不回显令牌本身。
      process.stdout.write(JSON.stringify({
        ok: credential.mode !== "none",
        mode: credential.mode,
        username: credential.username || null,
        baseUrl: credential.baseUrl || null,
        hint: credential.mode === "none"
          ? "未配置 GITLAB_PRIVATE_TOKEN 或 GIT_USER/GIT_PASSWORD：只读拉取可能仍然成功，但推送大概率会失败"
          : "凭据已就绪（令牌不会打印，也不会写进 .git/config）",
      }, null, 2) + "\n");
      return;
    }
    case "prepare":
      process.stdout.write(JSON.stringify(prepare(options), null, 2) + "\n");
      return;
    case "status": {
      const info = snapshot(options.dir || "repo");
      process.stdout.write(JSON.stringify(info, null, 2) + "\n");
      if (!info.ok) process.exitCode = 1;
      return;
    }
    case "commit":
      process.stdout.write(JSON.stringify(commit(options), null, 2) + "\n");
      return;
    case "push":
      process.stdout.write(JSON.stringify(push(options), null, 2) + "\n");
      return;
    case "cleanup":
      process.stdout.write(JSON.stringify(cleanup(options), null, 2) + "\n");
      return;
    default:
      throw new GitFlowError(usage, "bad-usage");
  }
}


// 被 progress.mjs 作为库导入时不执行命令行逻辑。
const invokedDirectly = process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url));
if (invokedDirectly) {
  try {
    main();
  } catch (error) {
    const reason = error && error.reason ? `（${error.reason}）` : "";
    process.stderr.write(`[git 操作失败]${reason} ${redact(error && error.message)}\n`);
    process.exitCode = 1;
  }
}
