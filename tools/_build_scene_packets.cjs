// 一次性脚本：构造 scene dispatch packets（shared + 5 workers）
const fs = require("fs");
const path = require("path");

const PROJECT_DIR = "D:/cto9012/WXAPPS/倪师数字人/videos/ni-distillation-explainer";
const SKILL_DIR = "C:/Users/cto90/.hyperframes/skills/faceless-explainer";

const groupSpec = JSON.parse(fs.readFileSync(path.join(PROJECT_DIR, "group_spec.json"), "utf8"));
const sectionPlan = fs.readFileSync(path.join(PROJECT_DIR, "section_plan.md"), "utf8");

function cat(p) {
  try { return fs.readFileSync(p, "utf8"); } catch { return ""; }
}

// 解析 section_plan.md 里每个 ## Scene N: 块的正文
function parseSceneBlocks(md) {
  const blocks = {};
  const parts = md.split(/^## Scene (\d+):/m);
  // parts[0] = preface, parts[1]=N, parts[2]=body, parts[3]=N, ...
  for (let i = 1; i < parts.length; i += 2) {
    const n = parseInt(parts[i], 10);
    blocks[n] = parts[i + 1].trim();
  }
  return blocks;
}
const sceneBlocks = parseSceneBlocks(sectionPlan);

// 解析 ## Film Direction 块
let filmDirection = "";
const fdMatch = sectionPlan.match(/^## Film Direction\s*\n([\s\S]*?)(?=\n## (?:Scene|Film Direction))/m);
if (fdMatch) filmDirection = fdMatch[1].trim();
if (!filmDirection) {
  // 备用：第一个 ## Scene 之前、## Film Direction 之后
  const m2 = sectionPlan.match(/## Film Direction\s*\n([\s\S]*?)\n## Scene /);
  if (m2) filmDirection = m2[1].trim();
}
// 如果 group_spec 里有 film_direction 字段，优先用它（prep 已经提取）
if (groupSpec.film_direction) filmDirection = JSON.stringify(groupSpec.film_direction, null, 2);

// ---------- scene-shared.txt ----------
const dispatchDir = path.join(PROJECT_DIR, ".dispatch", "scene-dispatch");
fs.mkdirSync(dispatchDir, { recursive: true });

const shared = [
  "## Film direction",
  filmDirection,
  "",
  "## Tokens/easings/voice",
  cat(path.join(PROJECT_DIR, "design-system/chunks/tokens.css")),
  cat(path.join(PROJECT_DIR, "design-system/chunks/easings.js")),
  cat(path.join(PROJECT_DIR, "design-system/chunks/voice.md")),
].join("\n");
const sharedPath = path.join(dispatchDir, "scene-shared.txt");
fs.writeFileSync(sharedPath, shared, "utf8");

// guard: brand token 必须在
if (!/--brand-primary/.test(shared)) {
  console.error("FATAL: scene-shared.txt 缺少 --brand-primary");
  process.exit(1);
}

// ---------- 每个 worker 的 packet ----------
const groups = groupSpec.groups || [];
console.log("groups count:", groups.length);

for (const g of groups) {
  const wid = g.worker_id;
  // 收集这个 worker 拥有的所有逻辑场景的 section_plan 块
  const sceneIds = g.scene_ids || [];
  const sceneSections = sceneIds.map((sid) => {
    // sid 形如 "scene_3"，提取数字
    const n = parseInt(String(sid).replace(/\D/g, ""), 10);
    const body = sceneBlocks[n] || `(missing scene ${n} block in section_plan.md)`;
    return `### ${sid} (from section_plan.md)\n${body}`;
  }).join("\n\n");

  const workerPacket = [
    shared,
    "",
    `## Worker ${wid}`,
    `composition_id: ${g.composition_id}`,
    `composition_file: ${g.composition_file}`,
    `duration_s: ${g.duration_s}`,
    `canvas: ${groupSpec.width}x${groupSpec.height}`,
    `captions: disabled (full-canvas scenes, no caption band)`,
    `scenes: ${sceneIds.join(", ")}`,
    "",
    "## Scenes detail",
    sceneSections,
  ].join("\n");

  const p = path.join(dispatchDir, `${wid}.txt`);
  fs.writeFileSync(p, workerPacket, "utf8");
  console.log(`✓ ${wid}: ${p} (${Buffer.byteLength(workerPacket)} bytes, scenes: ${sceneIds.join(",")})`);
}

console.log("\nall worker packets written to", dispatchDir);
