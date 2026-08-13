#!/usr/bin/env node
// Single-skill CI gate: validates THIS repo's own SKILL.md against the g10dc
// canon. Exits non-zero on any P0/P1 issue so a regression fails the build.
// Self-contained (no deps) so it can be copied into any of the 36 skill repos.
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';

const DIR = resolve(process.argv[2] ?? '.');
const skillPath = join(DIR, 'SKILL.md');
if (!existsSync(skillPath)) {
  console.log('No SKILL.md in this repo -- nothing to validate.');
  process.exit(0);
}

const BOILERPLATE = [
  'Primary domain workflow execution as specified in frontmatter description',
  'Tasks outside declared skill scope or handled by specialized sibling skills',
];
const MANGLED = ['processing engine'];
const EXT = /\.(m?js|cjs|ts|tsx|py|json|md|ya?ml|sh|toml|txt)$/i;

function frontmatter(text) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
  if (!m) return null;
  const out = {};
  const lines = m[1].split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const kv = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(lines[i]);
    if (!kv) continue;
    let [, key, val] = kv;
    if (/^[>|]/.test(val)) {
      const buf = [];
      while (i + 1 < lines.length && /^\s+\S/.test(lines[i + 1])) buf.push(lines[++i].trim());
      val = buf.join(' ');
    }
    out[key] = val.replace(/^["'](.*)["']$/, '$1');
  }
  return out;
}

function fileRefs(text) {
  const refs = new Set();
  for (const m of text.matchAll(/`([^`\n]+)`/g)) {
    const t = m[1].trim();
    if (!EXT.test(t)) continue;
    if (/[\s*<>|$(){}]/.test(t)) continue;
    if (t.startsWith('-') || t.startsWith('http')) continue;
    if (!t.includes('/') && !t.includes('\\')) continue;
    if (t.startsWith('../') || t.startsWith('..\\')) continue; // ambiguous, skip
    refs.add(t.replace(/^\.\//, ''));
  }
  return [...refs];
}

const text = readFileSync(skillPath, 'utf8');
const fm = frontmatter(text);
const issues = [];

if (!fm) issues.push({ sev: 'P0', code: 'NO_FRONTMATTER', msg: 'no YAML frontmatter' });
if (fm && !fm.name) issues.push({ sev: 'P0', code: 'NO_NAME', msg: 'frontmatter missing `name`' });
if (fm && !fm.description) issues.push({ sev: 'P0', code: 'NO_DESC', msg: 'frontmatter missing `description`' });

for (const b of BOILERPLATE) {
  if (text.includes(b)) issues.push({ sev: 'P1', code: 'BOILERPLATE_SECTION', msg: `placeholder text present: "${b.slice(0, 40)}..."` });
}
for (const m of MANGLED) {
  if (text.includes(m)) issues.push({ sev: 'P1', code: 'MANGLED_TEXT', msg: `corrupted wording "${m}" -- should read "LLM"` });
}

const missingRefs = fileRefs(text).filter((r) => !existsSync(join(DIR, r)) && !existsSync(join(DIR, '..', r)));
for (const r of missingRefs) {
  issues.push({ sev: 'P1', code: 'BROKEN_REF', msg: `references \`${r}\` -- file does not exist` });
}

for (const m of text.matchAll(/\b(?:node|python3?)\s+([A-Za-z0-9_./-]+\.(?:m?js|cjs|py))/g)) {
  const p = m[1].replace(/^\.\//, '');
  if (!existsSync(join(DIR, p))) {
    issues.push({ sev: 'P0', code: 'BROKEN_ENTRYPOINT', msg: `documented command runs \`${p}\` -- file does not exist` });
  }
}

const p0 = issues.filter((i) => i.sev === 'P0').length;
const p1 = issues.filter((i) => i.sev === 'P1').length;
if (!issues.length) {
  console.log('validate-skill: OK, no issues.');
  process.exit(0);
}
console.log(`validate-skill: ${p0} P0, ${p1} P1 issue(s):`);
for (const i of issues) console.log(`  [${i.sev}] ${i.code}: ${i.msg}`);
process.exit(p0 + p1 > 0 ? 1 : 0);
