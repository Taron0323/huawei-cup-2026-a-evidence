import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const workspace = path.dirname(path.dirname(root));
const readJSON = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const manifest = readJSON(path.join(root, 'evidence/source_manifest.json'));
const groups = [
  ['evidence/冠亚季军_features.json', ['connected_questions', 'actual_comparison', 'actionable_output']],
  ['evidence/analyses/AB_features.json', ['cross_question_io_link', 'actual_alternative_comparison', 'concrete_final_answer']],
  ['evidence/analyses/CD_features.json', ['cross_question_link', 'actual_comparison', 'final_answer']],
  ['evidence/analyses/EF_features.json', ['connected_questions', 'actual_comparison', 'actionable_output']],
];
const keys = ['connected_questions', 'actual_comparison', 'actionable_output'];
const indexed = new Map();
for (const [rel, aliases] of groups) {
  for (const paper of readJSON(path.join(root, rel)).papers) {
    const id = paper.id ?? paper.paper_id;
    if (indexed.has(id)) throw new Error(`Duplicate paper ${id}`);
    const features = paper.structural_features ?? paper.conservative_structure;
    indexed.set(id, {
      analysis_source: rel,
      structural_features: Object.fromEntries(keys.map((key, i) => [key, features[aliases[i]]])),
      appendix_code: paper.appendix_code ?? paper.features.appendix_code,
    });
  }
}
const papers = manifest.map(source => {
  const analysis = indexed.get(source.id);
  if (!analysis) throw new Error(`Missing analysis ${source.id}`);
  const bytes = fs.readFileSync(path.join(workspace, source.source_path));
  const hash = crypto.createHash('sha256').update(bytes).digest('hex');
  if (hash !== source.sha256) throw new Error(`Source hash changed: ${source.id}`);
  const corpus = readJSON(path.join(root, `evidence/corpus/${source.id}.json`));
  if (corpus.length !== source.pdf_pages) throw new Error(`Page count mismatch ${source.id}`);
  corpus.forEach((page, i) => {
    if (page.pdf_page !== i + 1 || typeof page.text !== 'string') throw new Error(`Invalid corpus ${source.id}`);
  });
  for (const feature of [...Object.values(analysis.structural_features), analysis.appendix_code]) {
    if (!feature || !['present', 'not_found', 'unclear'].includes(feature.status)) throw new Error(`Invalid feature ${source.id}`);
    if (!feature.pages.length || feature.pages.some(p => !Number.isInteger(p) || p < 1 || p > source.pdf_pages)) throw new Error(`Invalid page ${source.id}`);
  }
  return { ...source, ...analysis, source_hash_verified: true };
});
if (papers.length !== 13 || indexed.size !== 13) throw new Error('Corpus must contain exactly 13 unique papers');
const counts = Object.fromEntries(keys.map(k => [k, papers.filter(p => p.structural_features[k].status === 'present').length]));
counts.appendix_code = papers.filter(p => p.appendix_code.status === 'present').length;
const result = {
  study_date: '2026-09-23',
  page_basis: 'PDF physical page; cover=1',
  interpretation: 'Presence describes observable structure only, not scientific validity, fair comparison, reproducibility or award causation.',
  definitions: {
    connected_questions: 'At least two questions have an explicit input/output connection.',
    actual_comparison: 'At least one numerical or plotted comparison of candidate methods, alternatives or before/after designs; fairness is assessed separately.',
    actionable_output: 'At least one concrete numerical answer, configuration or executable proposal responding to the problem.',
    appendix_code: 'Code text is embedded in the inspected PDF; file listings alone do not count. Execution was not performed.',
  },
  counts: { papers: papers.length, pdf_pages: papers.reduce((n, p) => n + p.pdf_pages, 0), ...counts },
  papers,
};
fs.writeFileSync(path.join(root, 'evidence/共性核对表.json'), JSON.stringify(result, null, 2) + '\n');
const table = ['# 13篇论文共性逐项核对', '', '页码均为PDF物理页码。存在不等于验证充分。正文分析与限制见各证据卡。', '', '| 论文ID | 奖项/高校 | 跨问衔接页码 | 实际对照页码 | 具体输出页码 | PDF内代码 |', '| --- | --- | --- | --- | --- | --- |'];
for (const p of papers) {
  const cols = keys.map(k => `${p.structural_features[k].status}: ${p.structural_features[k].pages.join(', ')}`);
  table.push(`| ${p.id} | ${p.award}/${p.university} | ${cols.join(' | ')} | ${p.appendix_code.status} |`);
}
table.push('', `统计：${counts.connected_questions}/13有跨问衔接；${counts.actual_comparison}/13有实际对照；${counts.actionable_output}/13有具体输出；${counts.appendix_code}/13的PDF内有代码片段。`, '', '以上特征不用于推算官方分数或获奖概率。');
fs.writeFileSync(path.join(root, 'evidence/共性核对表.md'), table.join('\n') + '\n');
console.log(JSON.stringify(result.counts));
