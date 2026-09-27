import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const checkout = path.join(root, '../github/huawei-cup-champion');
const repo = 'Taron0323/Huawei-Cup-Mathematical-Modeling-Skill';
const run = (cmd, args, options = {}) => execFileSync(cmd, args, { cwd: checkout, encoding: 'utf8', ...options }).trim();
const api = endpoint => JSON.parse(run('gh', ['api', endpoint]));
const info = api(`repos/${repo}`);
if (info.private || info.full_name !== repo) throw new Error('Wrong repository or visibility');
const head = run('git', ['rev-parse', 'HEAD']);
const ref = api(`repos/${repo}/git/ref/heads/main`).object.sha;
if (head !== ref) throw new Error('Local/remote commit mismatch');
const tree = api(`repos/${repo}/git/trees/${head}?recursive=1`);
if (tree.truncated) throw new Error('Incomplete remote tree');
const expected = ['README.md', 'SKILL.md', 'agents/openai.yaml', 'references/2024-patterns.md', 'references/execution.md', 'references/paper-and-defense.md'];
const blobs = tree.tree.filter(e => e.type === 'blob');
if (JSON.stringify(blobs.map(e => e.path).sort()) !== JSON.stringify(expected.sort())) throw new Error('Unexpected published files');
const entries = blobs.map(item => {
  const data = fs.readFileSync(path.join(checkout, item.path));
  const sha = crypto.createHash('sha1').update(`blob ${data.length}\0`).update(data).digest('hex');
  if (sha !== item.sha) throw new Error(`Remote bytes differ: ${item.path}`);
  if (item.path !== 'README.md') {
    const source = fs.readFileSync(path.join(root, 'huawei-cup-champion', item.path));
    const installed = fs.readFileSync(path.join(process.env.HOME, '.codex/skills/huawei-cup-champion', item.path));
    if (!data.equals(source) || !data.equals(installed)) throw new Error(`Skill copies differ: ${item.path}`);
  }
  return { path: item.path, bytes: data.length, git_blob_sha: item.sha };
});
const anonymous = execFileSync('curl', ['--fail', '--location', '--max-time', '30', '--silent', `https://raw.githubusercontent.com/${repo}/${head}/SKILL.md`]);
if (!anonymous.equals(fs.readFileSync(path.join(checkout, 'SKILL.md')))) throw new Error('Anonymous download differs');
const clean = run('git', ['status', '--porcelain']) === '';
if (!clean) throw new Error('Publication checkout not clean');
const result = { status: 'PASS', repository: info.html_url, visibility: 'PUBLIC', branch: 'main', commit: head, remote_commit_matches: true, exact_remote_files_verified: true, anonymous_download_verified: true, installed_skill_matches: true, checkout_clean: clean, new_session_discovery: 'NOT_TESTED', ci: 'NOT_CONFIGURED', entries };
fs.writeFileSync(path.join(root, 'evidence/github_publication.json'), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result));
