#!/usr/bin/env node
/**
 * mock-jira.mjs —— 本地 mock JIRA Server/DC 服务，供 jira-code 技能离线自测与端到端演练使用。
 *
 * 用法：
 *   node scripts/mock-jira.mjs [--port 0] [--json] [--log]
 *
 * 与真实 JIRA 的约定对齐：
 *   - 认证：`Authorization: Bearer <token>`，缺失或不符返回 401
 *   - 单条：GET /rest/api/2/issue/<KEY>（description 为 wiki markup 字符串）
 *   - 评论：GET/POST /rest/api/2/issue/<KEY>/comment、PUT .../comment/<ID>
 *   - 附件：GET /rest/api/2/attachment/content/<ID>
 *   - 旁路：GET /__mock/state 返回当前评论与附件状态，便于自动化断言
 *
 * 数据集覆盖三条典型路径：方案里仓库+分支齐全（SHOP-201）、方案缺仓库/分支（SHOP-202）、
 * 单子上根本没有开发方案附件（SHOP-203）。本脚本只用于本地验证，线上流程不会调用它。
 */

import { createServer } from "node:http";


export const MOCK_TOKEN = "mock-jira-code-token";

// SHOP-201：方案里写清了仓库与目标分支 —— 正常流程。
const PLAN_READY = [
  "# 开发方案：购物车支持批量删除选中商品",
  "",
  "## 一、涉及仓库",
  "",
  "- 仓库：shop/cart-service",
  "- 目标分支：release/2.4",
  "",
  "## 二、实现要点",
  "",
  "1. 购物车列表页新增批量删除入口，选中项一次性删除",
  "2. 删除前弹出确认框，提示将删除的商品数量",
  "3. 删除后刷新购物车总价与商品数",
  "",
].join("\n");

// SHOP-202：只写了要做什么，没写仓库也没写分支 —— 应当评论说明并中断。
const PLAN_INCOMPLETE = [
  "# 开发方案：订单导出",
  "",
  "## 一、背景",
  "",
  "运营希望把订单导出成表格，方便对账。",
  "",
  "## 二、实现要点",
  "",
  "1. 新增导出按钮",
  "2. 导出速度要快",
  "",
  "## 三、待定",
  "",
  "具体放在哪个服务里还没有定，等确认后再补。",
  "",
].join("\n");


/** mock 数据集：key → 单子字段与附件正文。 */
export const ISSUES = {
  "SHOP-201": {
    summary: "购物车支持批量删除选中商品",
    status: "评审中",
    assignee: { name: "li.si", displayName: "李四" },
    attachments: [{ id: "20001", filename: "开发方案.md", body: PLAN_READY }],
  },
  "SHOP-202": {
    summary: "订单导出",
    status: "评审中",
    assignee: { name: "wang.wu", displayName: "王五" },
    attachments: [{ id: "20002", filename: "开发方案.md", body: PLAN_INCOMPLETE }],
  },
  "SHOP-203": {
    summary: "商品详情页图片懒加载",
    status: "评审中",
    assignee: { name: "zhao.liu", displayName: "赵六" },
    attachments: [],
  },
};


/** 启动 mock 服务，返回访问地址、令牌与运行期状态（评论等），供测试断言。 */
export async function startMockJira({ token = MOCK_TOKEN, port = 0, log = false } = {}) {
  // 运行期可变状态：评论按单号分组，附件内容按 ID 索引。
  const state = {
    comments: {},
    nextCommentId: 90000,
    requests: [],
  };

  const server = createServer((req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    const auth = req.headers.authorization || "";
    state.requests.push({ method: req.method, pathname: url.pathname, query: Object.fromEntries(url.searchParams) });
    if (log) process.stderr.write(`[mock-jira] ${req.method} ${req.url}\n`);

    const sendJson = (status, body) => {
      res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
      res.end(JSON.stringify(body));
    };
    const unauthorized = () => sendJson(401, { errorMessages: ["Client must be authenticated to access this resource."] });

    const readBody = () => new Promise((resolveBody) => {
      let raw = "";
      req.on("data", (chunk) => { raw += chunk; });
      req.on("end", () => {
        try {
          resolveBody(raw ? JSON.parse(raw) : {});
        } catch (error) {
          resolveBody({});
        }
      });
    });

    const finish = async () => {
      // 旁路接口：给本地验证用，不需要鉴权。
      if (url.pathname === "/__mock/state") {
        sendJson(200, { comments: state.comments, issues: Object.keys(ISSUES), requestCount: state.requests.length });
        return;
      }
      if (url.pathname === "/rest/api/2/serverInfo") {
        sendJson(200, { baseUrl: `http://127.0.0.1:${server.address().port}`, version: "10.3.0-mock" });
        return;
      }
      if (auth !== `Bearer ${token}`) {
        unauthorized();
        return;
      }
      if (url.pathname === "/rest/api/2/myself") {
        sendJson(200, { name: "jira-code-mock", displayName: "技能自测账号" });
        return;
      }

      const issueMatch = url.pathname.match(/^\/rest\/api\/2\/issue\/([^/]+)$/);
      if (issueMatch && req.method === "GET") {
        const key = decodeURIComponent(issueMatch[1]);
        const issue = ISSUES[key];
        if (!issue) {
          sendJson(404, { errorMessages: [`Issue ${key} does not exist.`] });
          return;
        }
        const comments = state.comments[key] || [];
        sendJson(200, {
          key,
          id: String(10000 + Object.keys(ISSUES).indexOf(key)),
          self: `http://127.0.0.1:${server.address().port}/rest/api/2/issue/${key}`,
          fields: {
            summary: issue.summary,
            description: "见附件《开发方案.md》。",
            status: { name: issue.status },
            issuetype: { name: "需求" },
            assignee: issue.assignee,
            reporter: issue.assignee,
            labels: [],
            attachment: issue.attachments.map((item) => ({
              id: item.id,
              filename: item.filename,
              size: Buffer.byteLength(item.body, "utf8"),
              mimeType: "text/markdown",
              created: "2026-09-20T10:00:00.000+0800",
              author: { displayName: "产品经理" },
              content: `http://127.0.0.1:${server.address().port}/rest/api/2/attachment/content/${item.id}`,
            })),
            subtasks: [],
            comment: {
              total: comments.length,
              comments: comments.map((item) => ({
                id: item.id,
                author: { name: "jira-code", displayName: "jira-code" },
                created: item.created,
                updated: item.updated,
                body: item.body,
              })),
            },
          },
        });
        return;
      }

      const commentListMatch = url.pathname.match(/^\/rest\/api\/2\/issue\/([^/]+)\/comment$/);
      if (commentListMatch) {
        const key = decodeURIComponent(commentListMatch[1]);
        if (!ISSUES[key]) {
          sendJson(404, { errorMessages: [`Issue ${key} does not exist.`] });
          return;
        }
        if (req.method === "GET") {
          sendJson(200, { comments: (state.comments[key] || []).map((item) => ({
            id: item.id,
            author: { name: "jira-code", displayName: "jira-code" },
            created: item.created,
            updated: item.updated,
            body: item.body,
          })) });
          return;
        }
        if (req.method === "POST") {
          const payload = await readBody();
          const id = String(state.nextCommentId++);
          const record = { id, body: String(payload.body || ""), created: "2026-09-22T10:00:00.000+0800", updated: "2026-09-22T10:00:00.000+0800", updates: 0 };
          state.comments[key] = (state.comments[key] || []).concat(record);
          sendJson(201, { id, body: record.body });
          return;
        }
        sendJson(405, { errorMessages: ["method not allowed"] });
        return;
      }

      const commentMatch = url.pathname.match(/^\/rest\/api\/2\/issue\/([^/]+)\/comment\/(\d+)$/);
      if (commentMatch && req.method === "PUT") {
        const key = decodeURIComponent(commentMatch[1]);
        const id = commentMatch[2];
        const payload = await readBody();
        const list = state.comments[key] || [];
        const target = list.find((item) => item.id === id);
        if (!target) {
          sendJson(404, { errorMessages: [`Comment ${id} does not exist.`] });
          return;
        }
        target.body = String(payload.body || "");
        target.updated = "2026-09-22T10:05:00.000+0800";
        target.updates += 1;
        sendJson(200, { id, body: target.body });
        return;
      }

      const attachmentMatch = url.pathname.match(/^\/rest\/api\/2\/attachment\/content\/(\d+)$/);
      if (attachmentMatch && req.method === "GET") {
        const id = attachmentMatch[1];
        const hit = Object.values(ISSUES).flatMap((issue) => issue.attachments).find((item) => item.id === id);
        if (!hit) {
          sendJson(404, { errorMessages: [`Attachment ${id} does not exist.`] });
          return;
        }
        res.writeHead(200, { "content-type": "text/markdown; charset=utf-8" });
        res.end(hit.body);
        return;
      }

      if (url.pathname === "/rest/api/2/search") {
        sendJson(200, { total: 0, startAt: 0, maxResults: 50, issues: [] });
        return;
      }
      sendJson(404, { errorMessages: [`mock 未实现的路径：${url.pathname}`] });
    };

    finish().catch((error) => {
      sendJson(500, { errorMessages: [String((error && error.message) || error)] });
    });
  });

  await new Promise((resolveListen) => server.listen(port, "127.0.0.1", resolveListen));
  const actualPort = server.address().port;
  return {
    baseUrl: `http://127.0.0.1:${actualPort}`,
    port: actualPort,
    token,
    state,
    close: () => new Promise((resolveClose) => server.close(resolveClose)),
  };
}


// 独立运行：起服务并保持，方便手工试用。
if (process.argv[1] && process.argv[1].endsWith("mock-jira.mjs")) {
  const portIndex = process.argv.indexOf("--port");
  const port = portIndex === -1 ? 0 : Number(process.argv[portIndex + 1]);
  const mock = await startMockJira({ port, log: process.argv.includes("--log") });
  if (process.argv.includes("--json")) {
    // 只输出一行 JSON，便于外部脚本直接抓取端口与令牌。
    process.stdout.write(JSON.stringify({ baseUrl: mock.baseUrl, port: mock.port, token: mock.token }) + "\n");
  } else {
    process.stdout.write([
      `mock JIRA 已启动：${mock.baseUrl}`,
      `  单号：${Object.keys(ISSUES).join(", ")}`,
      `  令牌：${mock.token}`,
      "",
      "按 Ctrl+C 结束。",
      "",
    ].join("\n"));
  }
}
