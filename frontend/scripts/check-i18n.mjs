import { fileURLToPath } from "node:url";
// i18n check: (1) en and zh-TW have exactly the same keys, no empty values, same {{placeholders}};
// (2) every static t("key") used in src exists; (3) every dynamic key family has all its known members.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const root = fileURLToPath(new URL("..", import.meta.url));
const flat = (o, p = "") => Object.entries(o).flatMap(([k, v]) => (typeof v === "object" ? flat(v, `${p}${k}.`) : [[`${p}${k}`, v]]));
const en = Object.fromEntries(flat(JSON.parse(readFileSync(join(root, "src/locales/en.json"), "utf8"))));
const zh = Object.fromEntries(flat(JSON.parse(readFileSync(join(root, "src/locales/zh-TW.json"), "utf8"))));
const errors = [];
const ph = (s) => [...String(s).matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort().join(",");

for (const k of Object.keys(en)) if (!(k in zh)) errors.push(`zh-TW missing: ${k}`);
for (const k of Object.keys(zh)) if (!(k in en)) errors.push(`en missing: ${k}`);
for (const k of Object.keys(en)) {
  if (!String(en[k]).trim()) errors.push(`en empty: ${k}`);
  if (k in zh && !String(zh[k]).trim()) errors.push(`zh-TW empty: ${k}`);
  if (k in zh && ph(en[k]) !== ph(zh[k])) errors.push(`placeholder mismatch: ${k} (${ph(en[k])} vs ${ph(zh[k])})`);
}

const files = [];
const walk = (d) => { for (const f of readdirSync(d)) { const p = join(d, f); if (statSync(p).isDirectory()) walk(p); else if (/\.tsx?$/.test(f) && !/\.test\./.test(f)) files.push(p); } };
walk(join(root, "src"));
let used = 0;
for (const f of files) {
  const src = readFileSync(f, "utf8");
  for (const m of src.matchAll(/\bt\("([a-zA-Z0-9_.-]+)"/g)) { used++; if (!(m[1] in en)) errors.push(`${f.replace(root, "")}: unknown key ${m[1]}`); }
}

// Dynamic families: t(`prefix.${x}`) — list the values the backend/data can produce.
const families = {
  "provenance.*.label": ["LIVE_MEASURED", "IMPORTED", "DEMO_SAMPLE", "NOT_RUN", "FAILED"],
  "provenance.*.help": ["LIVE_MEASURED", "IMPORTED", "DEMO_SAMPLE", "NOT_RUN", "FAILED"],
  "status.*": ["pending", "running", "succeeded", "failed", "blocked", "not_run", "verified", "check_failed", "not_started"],
  "approval.*": ["model_download_uses_network_and_disk", "vllm_uses_gpu_and_pulls_container_image", "large_benchmark"],
  "areas.*.name": ["lab", "garage", "missions", "code", "research", "arena", "journal"],
  "areas.*.desc": ["lab", "garage", "missions", "code", "research", "arena", "journal"],
  "modes.*.label": ["observe", "guided", "expert"], "modes.*.help": ["observe", "guided", "expert"],
  "caps.*": ["cpu_inference", "nvidia_gpu", "cuda_torch", "docker", "vllm_docker", "vllm_python", "hub_access"],
  "missionState.*": ["locked", "available", "in_progress", "complete", "not_available"],
  "mastery.*": ["none", "started", "practiced", "independent"],
  "stepStatus.*": ["verified", "pending", "not_available"],
  "claim.*": ["established", "implementation", "heuristic", "assumption", "engineering_heuristic"],
  "tutor.source.*": ["curated", "derived", "source", "ai", "none"],
  "garage.path.*": ["gpu_transformers", "gpu_vllm", "cpu_transformers"],
  "garage.verdict.*": ["fits_gpu", "cpu_only", "too_large", "unknown"],
  "garage.size.*": ["tiny", "small"], "garage.source.*": ["huggingface_hub_api", "local_files"],
  "kinds.*": ["hardware", "inference", "benchmark"],
  "skills.*": ["m01-meet-your-machine", "m02-find-your-model", "m03-wake-it-up", "m04-build-your-server", "m05-put-it-to-the-test", "m06-hunt-the-bottleneck", "m07-defend-your-decision"],
  "research.kind.*": ["paper", "documentation", "book_chapter"], "research.verification.*": ["fetched", "not_fetched"],
  "research.section.*": ["beginner", "engineering", "contributions", "practical", "limitations"],
  "arena.p.*": ["concurrency", "max_tokens", "num_requests", "warmup_requests", "trials", "hypothesis"],
  "arena.sf.*": ["evidence", "cause", "change", "impact", "drawbacks", "validation"],
  "arena.sugg.*": ["queueing_serial", "queueing_saturated", "batching_helps", "decode_bound", "errors_present", "confounded"],
  "arena.warn.*": ["non_measured_provenance", "more_than_one_variable_changed", "no_variable_changed"],
  "journal.note.*": ["hypothesis", "observation", "decision", "lesson"],
  "viz.kv.*": ["contiguous", "paged"],
};
for (const [fam, vals] of Object.entries(families)) for (const v of vals) { const k = fam.replace("*", v); if (!(k in en)) errors.push(`family ${fam}: missing ${k}`); }

if (errors.length) { console.error(errors.join("\n")); console.error(`\n✗ ${errors.length} i18n problem(s)`); process.exit(1); }
console.log(`✓ i18n OK: ${Object.keys(en).length} keys in en and zh-TW, ${used} static usages, ${Object.keys(families).length} dynamic families`);
