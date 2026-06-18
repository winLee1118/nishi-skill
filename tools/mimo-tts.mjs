#!/usr/bin/env node
/**
 * mimo-tts.mjs — mimo-v2.5-tts 配音注入工具（HyperFrames faceless-explainer 专用）
 *
 * 作用：绕过 HyperFrames 内置的 audio.mjs（只支持 HeyGen/ElevenLabs/Kokoro），
 * 用项目自有的 mimo 2.5 TTS（冰糖音色）生成每场景配音，再用 Whisper 本地
 * 对齐出词级时间戳，最后汇总成 audio_meta.json。之后从 faceless-explainer
 * Step 4 (visual-design) 正常续跑即可。
 *
 * 用法（在仓库根目录下）：
 *   node tools/mimo-tts.mjs --project ./videos/ni-distillation-explainer
 *
 * 环境变量（自动从 apps/desktop/.env.local 读取；也可手动 export）：
 *   MIMO_API_KEY=tp-...
 *   MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
 *   MIMO_AUTH_HEADER=authorization
 *
 * 产出（写入 --project 指定的视频工程目录）：
 *   <project>/assets/voice/scene_<N>.wav          （44.1kHz mono）
 *   <project>/assets/voice/scene_<N>_words.json   （词级时间戳；对齐失败则 []）
 *   <project>/audio_meta.json                      （HF resume 表的注入点）
 *
 * 退出码：
 *   0 = 全部场景合成成功（部分场景字幕对齐失败不阻断，仅在 stderr 警告）
 *   1 = narrator_scripts.json 读取失败，或任一场景 mimo 合成失败
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ---------- 参数解析 ----------
const argv = process.argv.slice(2);
function getFlag(name, fallback) {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback;
}
const PROJECT_DIR = getFlag("project", "./videos/ni-distillation-explainer");
const VOICE = getFlag("voice", "冰糖");
const FORMAT = getFlag("format", "wav");
const STYLE_PROMPT = getFlag(
  "style-prompt",
  "温和沉稳、像一位学识渊博的老师在课堂上讲解，语速适中，声音醇厚有磁性。"
);
const SKIP_TRANSCRIBE = argv.includes("--no-transcribe");
const ENV_FILE = getFlag("env-file", "");

// ---------- 加载环境变量 ----------
function loadEnvFile(p) {
  if (!p || !existsSync(p)) return false;
  for (const line of readFileSync(p, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)\s*$/);
    if (!m) continue;
    const [, k, vRaw] = m;
    if (process.env[k] === undefined) {
      process.env[k] = vRaw.replace(/^["']|["']$/g, "");
    }
  }
  return true;
}

const repoRoot = join(__dirname, "..");
const defaultEnv = join(repoRoot, "apps", "desktop", ".env.local");
if (!process.env.MIMO_API_KEY && existsSync(defaultEnv)) loadEnvFile(defaultEnv);
if (ENV_FILE) loadEnvFile(ENV_FILE);

const MIMO_API_KEY = process.env.MIMO_API_KEY;
const MIMO_BASE_URL = process.env.MIMO_BASE_URL || "https://token-plan-cn.xiaomimimo.com/v1";
const MIMO_AUTH_HEADER = process.env.MIMO_AUTH_HEADER || "authorization";

if (!MIMO_API_KEY) {
  console.error("FATAL: MIMO_API_KEY 未设置。");
  console.error("  请确保 apps/desktop/.env.local 存在，或手动 export，或用 --env-file 指定。");
  process.exit(1);
}

// ---------- 工具函数 ----------
function ffprobeDuration(absPath) {
  const r = spawnSync("ffprobe", [
    "-v", "error", "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", absPath,
  ], { encoding: "utf8" });
  if (r.status !== 0) return null;
  const d = parseFloat(String(r.stdout).trim());
  return Number.isFinite(d) && d > 0 ? d : null;
}

function ffmpegToWav44kMono(srcAbs, dstAbs) {
  const r = spawnSync("ffmpeg", [
    "-y", "-i", srcAbs, "-ar", "44100", "-ac", "1", dstAbs,
  ], { encoding: "utf8" });
  return r.status === 0;
}

function runWhisperTranscribe(wavAbs, wordsJsonAbs) {
  // npx hyperframes transcribe <wav> --language zh --format words --output <json>
  const cmd = process.platform === "win32" ? "npx.cmd" : "npx";
  const r = spawnSync(cmd, [
    "--yes", "hyperframes", "transcribe",
    wavAbs, "--language", "zh", "--format", "words", "--output", wordsJsonAbs,
  ], { encoding: "utf8", shell: process.platform === "win32" });
  if (r.status !== 0 || !existsSync(wordsJsonAbs)) {
    console.error(`  [warn] whisper 对齐失败 (exit ${r.status})，该场景字幕降级为整句。`);
    if (!existsSync(wordsJsonAbs)) writeFileSync(wordsJsonAbs, "[]");
    return false;
  }
  try {
    const parsed = JSON.parse(readFileSync(wordsJsonAbs, "utf8"));
    if (!Array.isArray(parsed)) throw new Error("not array");
    return true;
  } catch {
    writeFileSync(wordsJsonAbs, "[]");
    return false;
  }
}

// ---------- mimo TTS 调用 ----------
async function mimoTts(text, { retries = 2 } = {}) {
  const url = `${MIMO_BASE_URL.replace(/\/$/, "")}/chat/completions`;
  const authHeaderName = MIMO_AUTH_HEADER || "authorization";
  const authHeaderValue = MIMO_AUTH_HEADER === "authorization"
    ? `Bearer ${MIMO_API_KEY}`
    : MIMO_API_KEY;

  const body = {
    model: "mimo-v2.5-tts",
    messages: [
      { role: "user", content: STYLE_PROMPT },
      { role: "assistant", content: text },
    ],
    audio: { format: FORMAT, voice: VOICE },
  };

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 90000);
      const resp = await fetch(url, {
        method: "POST",
        headers: { [authHeaderName]: authHeaderValue, "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      if (!resp.ok) {
        const errText = await resp.text().catch(() => "");
        throw new Error(`HTTP ${resp.status}: ${errText.slice(0, 300)}`);
      }
      const data = await resp.json();
      const b64 = data?.choices?.[0]?.message?.audio?.data;
      if (!b64 || typeof b64 !== "string") {
        throw new Error(`响应里找不到 choices[0].message.audio.data，top keys=${Object.keys(data || {}).join(",")}`);
      }
      return b64;
    } catch (e) {
      const isLast = attempt === retries;
      console.error(`  [mimo attempt ${attempt + 1}/${retries + 1}] ${isLast ? "FAILED" : "retry"}: ${e.message}`);
      if (isLast) throw e;
      await new Promise((r) => setTimeout(r, 1500 * (attempt + 1)));
    }
  }
}

// ---------- 主流程 ----------
async function main() {
  const nsPath = join(PROJECT_DIR, "narrator_scripts.json");
  if (!existsSync(nsPath)) {
    console.error(`FATAL: 找不到 ${nsPath}。请先跑完 faceless-explainer Step 2 (scriptwriting)。`);
    process.exit(1);
  }
  const narrator = JSON.parse(readFileSync(nsPath, "utf8"));
  const scenes = Array.isArray(narrator.scenes) ? narrator.scenes : [];
  if (scenes.length === 0) {
    console.error("FATAL: narrator_scripts.json 里 scenes 为空。");
    process.exit(1);
  }

  const voiceDir = join(PROJECT_DIR, "assets", "voice");
  mkdirSync(voiceDir, { recursive: true });
  const tmpDir = join(PROJECT_DIR, ".mimo-tmp");
  mkdirSync(tmpDir, { recursive: true });

  const audioMeta = {
    tts_provider: "custom",
    voice_id: `mimo-v2.5-tts:${VOICE}`,
    bgm_provider: null,
    bgm_enabled: false,
    bgm_pending: false,
    bgm_path: null,
    bgm_log: null,
    bgm_pid: null,
    bgm_mode: null,
    bgm_target_duration_s: null,
    bgm_seed_duration_s: null,
    bgm_loop_count: null,
    total_duration_s: 0,
    scenes: {},
  };

  console.log(`\n=== mimo-tts 开始：${scenes.length} 个场景，音色「${VOICE}」 ===\n`);

  for (const scene of scenes) {
    const n = scene.sceneNumber;
    const text = String(scene.script || "").trim();
    if (!text) {
      console.error(`  [scene_${n}] 跳过：script 字段为空`);
      continue;
    }
    const cleanText = text.replace(/<\/?(em|brand|emph|cta)>/g, "");
    const preview = cleanText.length > 40 ? cleanText.slice(0, 40) + "…" : cleanText;
    console.log(`[scene_${n}] 合成（${cleanText.length}字）: ${preview}`);

    let b64;
    try {
      b64 = await mimoTts(cleanText);
    } catch (e) {
      console.error(`  [scene_${n}] mimo 合成失败，终止: ${e.message}`);
      process.exit(1);
    }

    const rawAbs = join(tmpDir, `scene_${n}_raw.${FORMAT}`);
    writeFileSync(rawAbs, Buffer.from(b64, "base64"));

    const wavRel = `assets/voice/scene_${n}.wav`;
    const wavAbs = join(PROJECT_DIR, wavRel);
    if (!ffmpegToWav44kMono(rawAbs, wavAbs)) {
      console.error(`  [scene_${n}] ffmpeg 转 wav 失败，终止`);
      process.exit(1);
    }
    const dur = ffprobeDuration(wavAbs);
    if (!dur) {
      console.error(`  [scene_${n}] ffprobe 读不到时长，终止`);
      process.exit(1);
    }
    console.log(`  ✓ wav: ${wavRel} (${dur.toFixed(2)}s)`);

    const wordsRel = `assets/voice/scene_${n}_words.json`;
    const wordsAbs = join(PROJECT_DIR, wordsRel);
    let wordsOk = false;
    if (SKIP_TRANSCRIBE) {
      writeFileSync(wordsAbs, "[]");
      console.error(`  [scene_${n}] --no-transcribe，跳过对齐（字幕将降级）`);
    } else {
      wordsOk = runWhisperTranscribe(wavAbs, wordsAbs);
    }

    audioMeta.scenes[`scene_${n}`] = {
      voicePath: wavRel,
      voiceDuration: Number(dur.toFixed(3)),
      wordsPath: wordsOk ? wordsRel : "",
    };
    audioMeta.total_duration_s += dur;
  }

  audioMeta.total_duration_s = Number(audioMeta.total_duration_s.toFixed(3));

  const metaPath = join(PROJECT_DIR, "audio_meta.json");
  writeFileSync(metaPath, JSON.stringify(audioMeta, null, 2));
  console.log(`\n=== 完成 ===`);
  console.log(`总时长: ${audioMeta.total_duration_s}s`);
  console.log(`场景数: ${Object.keys(audioMeta.scenes).length}`);
  console.log(`audio_meta.json: ${metaPath}`);
  console.log(`\n下一步：从 faceless-explainer Step 4 (visual-design) 续跑。`);
}

main().catch((e) => {
  console.error(`\nFATAL: ${e.stack || e.message}`);
  process.exit(1);
});
