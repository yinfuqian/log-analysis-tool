import { readFileSync } from 'node:fs';

import { validateSemantic } from './lib/semantic-schema.mjs';

// 用法：
//   node verify-semantic-quotes.mjs <run-id> <KEY> [KEY...]
//       —— 引用必须逐字来自 raw/<KEY>.json 的 descriptionClean（默认）
//   node verify-semantic-quotes.mjs <run-id> <KEY> --draft
//       —— 引用改验 normalized/<KEY>.spec.md（评审对象是改写草稿而非 JIRA 原文时用）
//
// 结构校验直接复用报告端的契约（lib/semantic-schema.mjs），
// 避免出现"自检通过、报告却静默跳过"这种两边规则不一致的情况。
const args = process.argv.slice(2);
const byDraft = args.includes('--draft');
const [runId, ...keys] = args.filter((a) => a !== '--draft');

let bad = 0;
let total = 0;

for (const k of keys) {
  const sourcePath = byDraft ? `reports/.work/${runId}/normalized/${k}.spec.md` : `reports/.work/${runId}/raw/${k}.json`;
  const source = byDraft
    ? readFileSync(sourcePath, 'utf8')
    : JSON.parse(readFileSync(sourcePath, 'utf8')).descriptionClean;
  const sem = JSON.parse(readFileSync(`reports/.work/${runId}/semantic/${k}.json`, 'utf8'));

  for (const issue of validateSemantic(sem)) {
    bad += 1;
    console.log(`结构不合规 ${k}: ${issue}`);
  }

  for (const d of sem.dimensions ?? []) {
    for (const e of d.evidence ?? []) {
      total += 1;
      if (source.indexOf(e.quote) < 0) {
        bad += 1;
        console.log(`引用非逐字 [${d.id}] ${k}: ${e.quote}`);
      }
    }
  }

  const q = (sem.dimensions ?? []).flatMap((d) => d.evidence ?? []).length;
  console.log(`${k}: 引用 ${q} | 建议场景 ${(sem.suggestedScenarios ?? []).length} | 非原子 ${sem.nonAtomic?.detected}`);
  console.log(`    ${(sem.dimensions ?? []).map((d) => `${d.id}=${d.conclusion}`).join(' ')}`);
}

console.log(`\n校验（引用来源：${byDraft ? '改写草稿' : 'JIRA descriptionClean'}）：引用逐字 ${total} 条，问题 ${bad} 个`);
process.exit(bad === 0 ? 0 : 1);
