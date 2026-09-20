#!/usr/bin/env node
/**
 * 从 JIRA Server/DC 拉取需求，原始 JSON 落盘，供后续归一化使用。
 *
 * 用法：
 *   node scripts/jira-fetch.mjs --key PROJ-123 [--run-id <id>] [--out <dir>]
 *   node scripts/jira-fetch.mjs --jql "project = PROJ AND status = Open" [--limit 20]
 *
 * 只读约束（specs → 凭据与数据安全）：本脚本只发起 GET 请求，
 * 不创建、不修改、不删除 issue，不写评论。
 */

import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { loadCredentials, createLogger, makeRunId, CredentialsError } from './lib/shared.mjs';
import { cleanWikiMarkup } from './lib/wikimarkup.mjs';

const FIELDS = ['summary', 'description', 'issuetype', 'status', 'labels', 'assignee'];

export const DEFAULT_LIMIT = 20;
export const PAGE_SIZE = 50;

/**
 * 默认输出目录基于 cwd，而不是脚本自身位置。
 * 这样脚本被复制进 skill（~/.claude/skills/.../bin/）后，产物仍落在使用者的项目里，
 * 而不是写进 skill 安装目录。
 */
const DEFAULT_OUT_DIR = path.join(process.cwd(), 'reports', '.work');

/** 拉取失败时抛出的错误，携带可判断类别。 */
export class FetchError extends Error {
  constructor(message, { kind, status, key } = {}) {
    super(message);
    this.name = 'FetchError';
    this.kind = kind;
    this.status = status;
    this.key = key;
  }
}

/** 把 JIRA 返回的 issue 对象裁剪成本工具关心的形状。 */
export function normalizeIssue(raw) {
  const fields = raw?.fields ?? {};
  const descriptionRaw = fields.description ?? '';
  return {
    key: raw?.key ?? '(未知)',
    summary: fields.summary ?? '',
    descriptionRaw: typeof descriptionRaw === 'string' ? descriptionRaw : JSON.stringify(descriptionRaw),
    descriptionClean: cleanWikiMarkup(descriptionRaw),
    issueType: fields.issuetype?.name ?? '',
    status: fields.status?.name ?? '',
    labels: Array.isArray(fields.labels) ? fields.labels : [],
    assignee: fields.assignee?.displayName ?? fields.assignee?.name ?? '',
    self: raw?.self ?? '',
  };
}

/** 构造只读请求。集中在此，便于审计"没有写请求"。 */
function buildGetUrl(baseUrl, pathname, params = {}) {
  const url = new URL(`${baseUrl}/rest/api/2${pathname}`);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }
  return url;
}

/** 发一个 GET 并把常见失败翻译成 FetchError。 */
async function jiraGet({ baseUrl, pat, pathname, params, fetchImpl = fetch }) {
  const url = buildGetUrl(baseUrl, pathname, params);

  let response;
  try {
    response = await fetchImpl(url, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${pat}`,
        Accept: 'application/json',
      },
    });
  } catch (cause) {
    throw new FetchError(`无法连接 JIRA（${url.origin}）：${cause.message}`, { kind: 'network' });
  }

  if (response.status === 401 || response.status === 403) {
    throw new FetchError(
      `JIRA 认证失败（HTTP ${response.status}）。请检查环境变量 JIRA_PAT 是否为有效且未过期的 Personal Access Token。`,
      { kind: 'auth', status: response.status },
    );
  }

  if (response.status === 404) {
    throw new FetchError('JIRA 返回 404：资源不存在或当前账号无权访问。', {
      kind: 'not-found',
      status: 404,
    });
  }

  if (!response.ok) {
    throw new FetchError(`JIRA 返回非预期状态 HTTP ${response.status}。`, {
      kind: 'http',
      status: response.status,
    });
  }

  try {
    return await response.json();
  } catch (cause) {
    throw new FetchError(`JIRA 响应不是合法 JSON：${cause.message}`, { kind: 'decode' });
  }
}

/** 单 issue 模式。 */
export async function fetchIssue({ baseUrl, pat, key, fetchImpl }) {
  const data = await jiraGet({
    baseUrl,
    pat,
    pathname: `/issue/${encodeURIComponent(key)}`,
    params: { fields: FIELDS.join(',') },
    fetchImpl,
  });

  if (!data || typeof data !== 'object' || !data.key) {
    throw new FetchError(`JIRA 未返回 ${key} 的 issue 数据。`, { kind: 'shape', key });
  }

  return normalizeIssue(data);
}

/**
 * JQL 批量模式：按 startAt 翻页，直到达到 limit 或结果耗尽。
 * 返回 { issues, total, truncated }。
 */
export async function fetchByJql({ baseUrl, pat, jql, limit = DEFAULT_LIMIT, fetchImpl }) {
  const issues = [];
  let startAt = 0;
  let total = 0;

  while (issues.length < limit) {
    const want = Math.min(PAGE_SIZE, limit - issues.length);
    const page = await jiraGet({
      baseUrl,
      pat,
      pathname: '/search',
      params: { jql, startAt, maxResults: want, fields: FIELDS.join(',') },
      fetchImpl,
    });

    total = Number.isFinite(page?.total) ? page.total : issues.length;
    const batch = Array.isArray(page?.issues) ? page.issues : [];
    if (batch.length === 0) break;

    for (const raw of batch) {
      if (issues.length >= limit) break;
      issues.push(normalizeIssue(raw));
    }

    startAt += batch.length;
    if (startAt >= total) break;
  }

  return { issues, total, truncated: total > issues.length, failures: [] };
}

/**
 * 指定 Key 列表的批量模式：逐个拉取，单条失败不中断整体。
 *
 * 与 fetchByJql 的区别：JQL 搜索会静默略过当前账号无权查看的 issue，
 * 因此拿不到"某一条不可访问"的信号；逐条拉取才能给出真实的 404/无权限隔离。
 *
 * 例外：认证失败（401/403）代表凭据对所有人都无效，直接向上抛出终止整轮运行。
 */
export async function fetchByKeys({ baseUrl, pat, keys, limit = DEFAULT_LIMIT, fetchImpl, logger }) {
  const targets = keys.slice(0, limit);
  const truncated = keys.length > targets.length;
  const issues = [];
  const failures = [];

  for (const key of targets) {
    try {
      issues.push(await fetchIssue({ baseUrl, pat, key, fetchImpl }));
    } catch (error) {
      if (error instanceof FetchError && error.kind === 'auth') throw error;
      const failure = {
        key,
        kind: error instanceof FetchError ? error.kind : 'unknown',
        message: error instanceof Error ? error.message : String(error),
      };
      failures.push(failure);
      logger?.warn(`跳过 ${key}：${failure.message}`);
    }
  }

  return { issues, total: keys.length, truncated, failures };
}

async function persist({ issues, runId, outDir, logger }) {
  const runDir = path.join(outDir, runId);
  const rawDir = path.join(runDir, 'raw');
  await mkdir(rawDir, { recursive: true });

  const written = [];
  for (const issue of issues) {
    const file = path.join(rawDir, `${sanitizeKey(issue.key)}.json`);
    await writeFile(file, `${JSON.stringify(issue, null, 2)}\n`, 'utf8');
    written.push(file);
  }

  logger.info(`已落盘 ${written.length} 份原始 issue 到 ${rawDir}`);
  return { runDir, rawDir, written };
}

function sanitizeKey(key) {
  return String(key).replace(/[^A-Za-z0-9._-]/g, '_');
}

export function parseArgs(argv) {
  const args = { key: null, keys: null, jql: null, limit: DEFAULT_LIMIT, runId: null, outDir: null };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    const next = argv[i + 1];
    if (token === '--key') {
      args.key = next;
      i += 1;
    } else if (token === '--keys') {
      args.keys = String(next ?? '')
        .split(',')
        .map((item) => item.trim())
        .filter((item) => item !== '');
      i += 1;
    } else if (token === '--jql') {
      args.jql = next;
      i += 1;
    } else if (token === '--limit') {
      const parsed = Number.parseInt(next, 10);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        throw new FetchError(`--limit 需要正整数，收到 "${next}"。`, { kind: 'usage' });
      }
      args.limit = parsed;
      i += 1;
    } else if (token === '--run-id') {
      args.runId = next;
      i += 1;
    } else if (token === '--out') {
      args.outDir = next;
      i += 1;
    } else if (token === '--pat' || token.startsWith('--pat=')) {
      throw new FetchError(
        '不接受通过命令行传递 PAT。请改用环境变量 JIRA_PAT。',
        { kind: 'usage' },
      );
    } else {
      throw new FetchError(`无法识别的参数 "${token}"。`, { kind: 'usage' });
    }
  }

  const modes = [
    args.key ? '--key' : null,
    args.keys && args.keys.length > 0 ? '--keys' : null,
    args.jql ? '--jql' : null,
  ].filter(Boolean);

  if (modes.length === 0) {
    throw new FetchError('需要 --key <ISSUE-KEY>、--keys A,B,C 或 --jql "<JQL>" 之一。', {
      kind: 'usage',
    });
  }
  if (modes.length > 1) {
    throw new FetchError(`${modes.join(' 与 ')} 只能选一种。`, { kind: 'usage' });
  }

  return args;
}

export async function runFetch({
  argv = process.argv.slice(2),
  env = process.env,
  fetchImpl = fetch,
  outDir = DEFAULT_OUT_DIR,
  now = new Date(),
} = {}) {
  const args = parseArgs(argv);

  // 凭据校验前置：缺失时在任何网络请求之前终止。
  const { baseUrl, pat } = loadCredentials(env);
  const logger = createLogger({ secrets: [pat] });

  const runId = args.runId ?? makeRunId(now);
  const resolvedOutDir = args.outDir ?? outDir;

  let issues;
  let total;
  let truncated = false;
  let jql = null;
  let failures = [];

  if (args.key) {
    logger.info(`拉取单个 issue：${args.key}`);
    issues = [await fetchIssue({ baseUrl, pat, key: args.key, fetchImpl })];
    total = 1;
  } else if (args.keys) {
    logger.info(`按 Key 列表拉取 ${args.keys.length} 条（上限 ${args.limit} 条）`);
    const result = await fetchByKeys({
      baseUrl,
      pat,
      keys: args.keys,
      limit: args.limit,
      fetchImpl,
      logger,
    });
    issues = result.issues;
    total = result.total;
    truncated = result.truncated;
    failures = result.failures;
  } else {
    jql = args.jql;
    logger.info(`按 JQL 拉取：${jql}（上限 ${args.limit} 条）`);
    const result = await fetchByJql({ baseUrl, pat, jql, limit: args.limit, fetchImpl });
    issues = result.issues;
    total = result.total;
    truncated = result.truncated;
    failures = result.failures;
  }

  const { runDir, rawDir, written } = await persist({ issues, runId, outDir: resolvedOutDir, logger });

  const meta = {
    runId,
    fetchedAt: now.toISOString(),
    baseUrl,
    mode: args.key ? 'key' : args.keys ? 'keys' : 'jql',
    jql,
    requestedKey: args.key,
    requestedKeys: args.keys ?? null,
    limit: args.key ? 1 : args.limit,
    total,
    fetched: issues.length,
    truncated,
    truncatedCount: truncated ? total - issues.length : 0,
    failures,
    keys: issues.map((issue) => issue.key),
  };
  await writeFile(path.join(runDir, 'meta.json'), `${JSON.stringify(meta, null, 2)}\n`, 'utf8');

  return { runId, runDir, rawDir, issues, failures, meta, writtenFiles: written, logger, secrets: [pat] };
}

async function main() {
  try {
    const { issues, failures, meta, runDir, secrets } = await runFetch();
    const logger = createLogger({ secrets });
    logger.info(`运行 id：${meta.runId}`);
    logger.info(`原始数据目录：${runDir}`);
    if (meta.truncated) {
      const source = meta.jql ? `所用 JQL：${meta.jql}` : `请求的 Key 数：${meta.total}`;
      logger.warn(
        `共命中 ${meta.total} 条，本次仅评审上限内的 ${meta.fetched} 条，` +
          `被截断 ${meta.truncatedCount} 条。${source}`,
      );
    }
    for (const failure of failures) {
      logger.warn(`${failure.key} 无法访问（${failure.kind}）：${failure.message}`);
    }
    logger.out(
      `拉取完成：${issues.length} 条（${issues.map((i) => i.key).join(', ') || '无'}）` +
        (failures.length > 0 ? `，${failures.length} 条无法访问` : ''),
    );
  } catch (error) {
    const secrets = [process.env.JIRA_PAT].filter(Boolean);
    const logger = createLogger({ secrets });
    if (error instanceof CredentialsError) {
      logger.error(error.message);
      process.exitCode = 2;
      return;
    }
    if (error instanceof FetchError) {
      if (error.kind === 'auth') {
        logger.error(`${error.message}\n（认证失败，未产出任何评审结论。）`);
        process.exitCode = 3;
        return;
      }
      if (error.kind === 'usage') {
        logger.error(
          `${error.message}\n用法：node scripts/jira-fetch.mjs ` +
            '（--key PROJ-123 | --keys PROJ-1,PROJ-2 | --jql "<JQL>"）[--limit N]',
        );
        process.exitCode = 4;
        return;
      }
      logger.error(error.message);
      process.exitCode = 5;
      return;
    }
    logger.error(`未预期的错误：${error.stack ?? error.message}`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && process.argv[1].endsWith('jira-fetch.mjs')) {
  await main();
}
