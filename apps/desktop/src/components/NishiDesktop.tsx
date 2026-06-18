"use client";

import { Database, Mic, RefreshCw, Send, Settings, Square, Upload, UserRound, Volume2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { blobToBase64, blobToWavBase64, playBase64Audio } from "@/src/lib/audio";
import type { AssistantStatus, ChatMessage, RetrievalHit } from "@/src/types";

const initialMessages: ChatMessage[] = [
  {
    id: "hello",
    role: "assistant",
    time: "10:26",
    content: "你好，我是倪师数字人。可以直接问我，也可以点击麦克风开始实时通话。"
  }
];

interface Particle {
  x: number;
  y: number;
  tx: number;
  ty: number;
  vx: number;
  vy: number;
  size: number;
  phase: number;
  alpha: number;
  tone: number;
}

interface VoiceCloneSample {
  name: string;
  dataUrl: string;
  mimeType: string;
  size: number;
}

interface MinimaxVoiceItem {
  voice_id: string;
  voice_name?: string;
  created_time?: string;
  description?: string[];
}

interface MinimaxVoiceCatalog {
  system_voice: MinimaxVoiceItem[];
  voice_cloning: MinimaxVoiceItem[];
  voice_generation: MinimaxVoiceItem[];
}

type SettingsTab = "general" | "llm" | "speech" | "clone";
type LlmProvider = "env" | "mimo" | "openai" | "local";
type SpeechProvider = "env" | "mimo" | "minimax" | "none";

interface AiSettings {
  active: boolean;
  autoSpeak: boolean;
  retrievalMode: "auto" | "fts" | "hybrid";
  llmProvider: LlmProvider;
  sttProvider: SpeechProvider;
  ttsProvider: SpeechProvider;
  cloneProvider: SpeechProvider;
  openai: {
    apiKey: string;
    baseUrl: string;
    model: string;
  };
  mimo: {
    apiKey: string;
    baseUrl: string;
    chatModel: string;
    asrModel: string;
    ttsModel: string;
    ttsVoiceCloneModel: string;
    authHeader: "api-key" | "authorization";
    voice: string;
  };
  minimax: {
    apiKey: string;
    groupId: string;
    baseUrl: string;
    ttsModel: string;
    cloneModel: string;
    voiceId: string;
    cloneVoiceId: string;
    emotion: string;
  };
}

const SETTINGS_STORAGE_KEY = "nishi-desktop-ai-settings-v1";
const VOICE_SAMPLE_STORAGE_KEY = "nishi-desktop-voice-clone-sample-v1";
const VOICE_CATALOG_STORAGE_KEY = "nishi-desktop-minimax-voice-catalog-v1";
const CHAT_STORAGE_KEY = "nishi-desktop-chat-session-v1";
const CHAT_HISTORY_LIMIT = 24;
const CHAT_CACHE_LIMIT = 80;

function isReloadNavigation() {
  if (typeof window === "undefined") return false;
  const navigation = window.performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
  return navigation?.type === "reload";
}

function loadCachedMessages() {
  if (typeof window === "undefined") return initialMessages;
  try {
    if (isReloadNavigation()) {
      window.localStorage.removeItem(CHAT_STORAGE_KEY);
      return initialMessages;
    }
    const saved = window.localStorage.getItem(CHAT_STORAGE_KEY);
    if (!saved) return initialMessages;
    const parsed = JSON.parse(saved);
    if (!Array.isArray(parsed)) return initialMessages;
    const messages = parsed.filter((item): item is ChatMessage => {
      if (!item || typeof item !== "object") return false;
      const entry = item as Partial<ChatMessage>;
      return (
        typeof entry.id === "string" &&
        (entry.role === "user" || entry.role === "assistant" || entry.role === "system") &&
        typeof entry.content === "string" &&
        typeof entry.time === "string"
      );
    });
    return messages.length ? messages.slice(-CHAT_CACHE_LIMIT) : initialMessages;
  } catch {
    return initialMessages;
  }
}

function normalizedRetrievalHits(value: unknown): RetrievalHit[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (item && typeof item === "object" ? (item as Record<string, unknown>) : null))
    .filter((item): item is Record<string, unknown> => Boolean(item))
    .map((item) => ({
      source_id: typeof item.source_id === "string" ? item.source_id : "",
      chunk_id: typeof item.chunk_id === "string" ? item.chunk_id : "",
      title: typeof item.title === "string" && item.title ? item.title : "未命名资料",
      course: typeof item.course === "string" ? item.course : "",
      chapter: typeof item.chapter === "string" ? item.chapter : "",
      timestamp: typeof item.timestamp === "string" ? item.timestamp : "",
      page: typeof item.page === "string" ? item.page : "",
      source_url: typeof item.source_url === "string" ? item.source_url : "",
      rights_status: typeof item.rights_status === "string" ? item.rights_status : "",
      snippet: typeof item.snippet === "string" ? item.snippet : "",
      score: typeof item.score === "number" ? item.score : undefined,
      match_source: typeof item.match_source === "string" ? item.match_source : "fts"
    }))
    .filter((item) => item.chunk_id || item.title || item.snippet);
}

function retrievalSourceLabel(source?: string) {
  if (source === "vector") return "向量命中";
  if (source === "hybrid") return "向量 + FTS";
  return "FTS 命中";
}

function retrievalSourceCounts(hits: RetrievalHit[]) {
  return hits.reduce(
    (counts, hit) => {
      if (hit.match_source === "vector") counts.vector += 1;
      else if (hit.match_source === "hybrid") counts.hybrid += 1;
      else counts.fts += 1;
      return counts;
    },
    { fts: 0, vector: 0, hybrid: 0 }
  );
}

const defaultAiSettings: AiSettings = {
  active: false,
  autoSpeak: false,
  retrievalMode: "hybrid",
  llmProvider: "env",
  sttProvider: "env",
  ttsProvider: "env",
  cloneProvider: "env",
  openai: {
    apiKey: "",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini"
  },
  mimo: {
    apiKey: "",
    baseUrl: "https://api.xiaomimimo.com/v1",
    chatModel: "mimo-v2.5-pro",
    asrModel: "mimo-v2.5-asr",
    ttsModel: "mimo-v2.5-tts",
    ttsVoiceCloneModel: "mimo-v2.5-tts-voiceclone",
    authHeader: "api-key",
    voice: "冰糖"
  },
  minimax: {
    apiKey: "",
    groupId: "",
    baseUrl: "https://api.minimaxi.com",
    ttsModel: "speech-2.8-hd",
    cloneModel: "speech-2.8-hd",
    voiceId: "female-shaonv",
    cloneVoiceId: "",
    emotion: "neutral"
  }
};

function mergeAiSettings(value: unknown): AiSettings {
  if (!value || typeof value !== "object") return defaultAiSettings;
  const raw = value as Partial<AiSettings>;
  const minimax = { ...defaultAiSettings.minimax, ...(raw.minimax || {}) };
  if (minimax.cloneVoiceId === "nishi_clone_voice") {
    minimax.cloneVoiceId = "";
  }
  return {
    ...defaultAiSettings,
    ...raw,
    openai: { ...defaultAiSettings.openai, ...(raw.openai || {}) },
    mimo: { ...defaultAiSettings.mimo, ...(raw.mimo || {}) },
    minimax
  };
}

function providerConfig(settings: AiSettings) {
  if (!settings.active) return undefined;
  const mimoAuthHeader = settings.mimo.apiKey.trim().startsWith("tp-") ? "authorization" : settings.mimo.authHeader;
  return {
    ...settings,
    openai: {
      ...settings.openai,
      apiKey: settings.openai.apiKey.trim(),
      baseUrl: settings.openai.baseUrl.trim()
    },
    mimo: {
      ...settings.mimo,
      apiKey: settings.mimo.apiKey.trim(),
      baseUrl: settings.mimo.baseUrl.trim(),
      authHeader: mimoAuthHeader
    },
    minimax: {
      ...settings.minimax,
      apiKey: settings.minimax.apiKey.trim(),
      baseUrl: settings.minimax.baseUrl.trim(),
      cloneVoiceId: settings.minimax.cloneVoiceId.trim(),
      voiceId: settings.minimax.voiceId.trim()
    }
  };
}

const fallbackMinimaxSystemVoices: MinimaxVoiceItem[] = [
  { voice_id: "female-shaonv", voice_name: "少女音色" },
  { voice_id: "female-yujie", voice_name: "御姐音色" },
  { voice_id: "female-chengshu", voice_name: "成熟女性音色" },
  { voice_id: "female-tianmei", voice_name: "甜美女性音色" },
  { voice_id: "male-qn-qingse", voice_name: "青涩青年音色" },
  { voice_id: "male-qn-jingying", voice_name: "精英青年音色" },
  { voice_id: "Chinese (Mandarin)_Gentleman", voice_name: "温润男声" },
  { voice_id: "Chinese (Mandarin)_Reliable_Executive", voice_name: "沉稳高管" },
  { voice_id: "Chinese (Mandarin)_Male_Announcer", voice_name: "播报男声" },
  { voice_id: "Chinese (Mandarin)_Radio_Host", voice_name: "电台男主播" }
];

function voiceLabel(item: MinimaxVoiceItem) {
  return item.voice_name ? `${item.voice_name} (${item.voice_id})` : item.voice_id;
}

function uniqueVoices(items: MinimaxVoiceItem[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (!item.voice_id || seen.has(item.voice_id)) return false;
    seen.add(item.voice_id);
    return true;
  });
}

function nowTime() {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date());
}

function parseSseBlock(block: string) {
  const lines = block.split(/\r?\n/);
  let event = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (!dataLines.length) return null;

  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return { event, data: dataLines.join("\n") };
  }
}

function statusText(status: AssistantStatus, recording: boolean, voiceCallActive = false) {
  if (recording || status === "listening") return "正在聆听";
  if (status === "transcribing") return "正在识别";
  if (status === "thinking") return "正在回应";
  if (status === "speaking") return "正在朗读";
  if (voiceCallActive) return "实时通话中";
  return "可以提问";
}

function makeParticles(width: number, height: number) {
  const particles: Particle[] = [];
  const cx = width * 0.5;
  const headCy = height * 0.32;
  const headRx = width * 0.13;
  const headRy = height * 0.16;
  const robeTopY = height * 0.49;
  const robeBottomY = height * 0.76;
  const shoulderRx = width * 0.32;

  const add = (tx: number, ty: number, alpha = 0.9) => {
    particles.push({
      x: tx + (Math.random() - 0.5) * width * 0.55,
      y: ty + (Math.random() - 0.5) * height * 0.45,
      tx,
      ty,
      vx: 0,
      vy: 0,
      size: Math.random() * 1.55 + 0.55,
      phase: Math.random() * Math.PI * 2,
      alpha,
      tone: 0.5 + Math.random() * 0.4
    });
  };

  for (let i = 0; i < 1700; i += 1) {
    const theta = Math.random() * Math.PI * 2;
    const radius = Math.sqrt(Math.random());
    add(cx + Math.cos(theta) * headRx * radius, headCy + Math.sin(theta) * headRy * radius, 0.96);
  }

  for (let i = 0; i < 320; i += 1) {
    add(cx + (Math.random() - 0.5) * width * 0.07, height * (0.45 + Math.random() * 0.08), 0.88);
  }

  for (let i = 0; i < 2600; i += 1) {
    const t = Math.random();
    const y = robeTopY + t * (robeBottomY - robeTopY);
    const span = shoulderRx * (1 - t * 0.35);
    const x = cx + (Math.random() - 0.5) * span * 2;
    const curve = Math.sin(t * Math.PI) * height * 0.045;
    add(x, y + curve, 0.72);
  }

  for (let i = 0; i < 840; i += 1) {
    const side = i % 2 === 0 ? -1 : 1;
    const t = Math.random();
    const x = cx + side * (width * 0.04 + t * width * 0.17 - Math.sin(t * Math.PI) * width * 0.035);
    const y = height * 0.47 + t * height * 0.25;
    add(x, y, 0.8);
  }

  for (let ring = 0; ring < 5; ring += 1) {
    const count = 150 - ring * 16;
    for (let i = 0; i < count; i += 1) {
      const theta = (Math.PI * 2 * i) / count;
      add(
        cx + Math.cos(theta) * width * (0.2 + ring * 0.07),
        height * 0.62 + Math.sin(theta) * height * (0.055 + ring * 0.026),
        0.25
      );
    }
  }

  return particles;
}

const SILHOUETTE_SRC = "/nishi-silhouette.png";
const CALLIGRAPHY_COLUMNS = [
  "太阳之为病脉浮",
  "头项强痛而恶寒",
  "观天之道执天之行",
  "阴阳者天地之道也",
  "万物之纲纪变化之父母",
  "生杀之本始神明之府也",
  "治病必求于本",
  "望闻问切辨证论治"
];

interface SilhouetteSample {
  aspect: number;
  points: Array<{ nx: number; ny: number; alpha: number; tone: number }>;
}

let silhouetteSamplePromise: Promise<SilhouetteSample | null> | null = null;

// 直接从设计稿位图按亮度采样粒子目标点，保证剪影形态与设计稿一致。
function loadSilhouetteSample(): Promise<SilhouetteSample | null> {
  if (!silhouetteSamplePromise) {
    silhouetteSamplePromise = new Promise((resolve) => {
      const image = new Image();
      image.onload = () => {
        try {
          const sampleWidth = 380;
          const aspect = image.naturalHeight / image.naturalWidth;
          const sampleHeight = Math.max(1, Math.round(sampleWidth * aspect));
          const offscreen = document.createElement("canvas");
          offscreen.width = sampleWidth;
          offscreen.height = sampleHeight;
          const offContext = offscreen.getContext("2d", { willReadFrequently: true });
          if (!offContext) {
            resolve(null);
            return;
          }
          offContext.drawImage(image, 0, 0, sampleWidth, sampleHeight);
          const { data } = offContext.getImageData(0, 0, sampleWidth, sampleHeight);
          const points: SilhouetteSample["points"] = [];
          for (let y = 0; y < sampleHeight; y += 1) {
            for (let x = 0; x < sampleWidth; x += 1) {
              const index = (y * sampleWidth + x) * 4;
              const luminance =
                data[index] * 0.299 + data[index + 1] * 0.587 + data[index + 2] * 0.114;
              if (luminance < 9) continue;
              const tone = Math.min(1, Math.pow(luminance / 235, 0.74));
              points.push({
                nx: x / sampleWidth,
                ny: y / sampleHeight,
                alpha: Math.min(1, 0.2 + tone * 0.85),
                tone
              });
            }
          }
          resolve(points.length > 500 ? { aspect, points } : null);
        } catch {
          resolve(null);
        }
      };
      image.onerror = () => resolve(null);
      image.src = SILHOUETTE_SRC;
    });
  }
  return silhouetteSamplePromise;
}

function particlesFromSample(sample: SilhouetteSample, width: number, height: number): Particle[] {
  // 设计稿是横版、人物居中约占画面一半宽。这里对宽高分别设上限再取较小值：
  // 竖长舞台受宽度上限约束（人物不会被放大裁切到只剩局部），
  // 扁宽舞台受高度上限约束（人物不会溢出上下边）。
  const widthBound = width * 1.42;
  const heightBound = (height * 1.12) / sample.aspect;
  const drawWidth = Math.min(widthBound, heightBound);
  const drawHeight = drawWidth * sample.aspect;
  const offsetX = (width - drawWidth) / 2;
  const offsetY = (height - drawHeight) / 2;

  const budget = Math.max(10000, Math.min(30000, Math.floor((width * height) / 10)));
  const keepRatio = Math.min(1, budget / sample.points.length);
  // 采样格映射到画布的单元尺寸，用于亚像素抖动，避免出现网格纹理。
  const jitterX = drawWidth / 380;
  const jitterY = jitterX;
  const particles: Particle[] = [];

  for (const point of sample.points) {
    // 亮的轮廓点全部保留，暗的填充点按比例丢弃，整体仍受 budget 控制。
    const keep = point.tone >= 0.58 ? 1 : keepRatio * (0.5 + point.tone * 1.2);
    if (Math.random() > keep) continue;
    const tx = offsetX + point.nx * drawWidth + (Math.random() - 0.5) * jitterX * 1.6;
    const ty = offsetY + point.ny * drawHeight + (Math.random() - 0.5) * jitterY * 1.6;
    if (tx < -12 || tx > width + 12 || ty < -12 || ty > height + 12) continue;
    particles.push({
      x: tx + (Math.random() - 0.5) * width * 0.6,
      y: ty + (Math.random() - 0.5) * height * 0.5,
      tx,
      ty,
      vx: 0,
      vy: 0,
      size: 0.45 + point.tone * 1.15 + Math.random() * 0.4,
      phase: Math.random() * Math.PI * 2,
      alpha: point.alpha,
      tone: point.tone
    });
  }

  return particles;
}

function buildCalligraphyBackdrop(width: number, height: number): HTMLCanvasElement {
  const backdrop = document.createElement("canvas");
  backdrop.width = Math.max(1, Math.floor(width));
  backdrop.height = Math.max(1, Math.floor(height));
  const ctx = backdrop.getContext("2d");
  if (!ctx) return backdrop;

  const fontSize = Math.max(16, Math.min(26, width * 0.052));
  ctx.font = `${fontSize}px STKaiti, KaiTi, "Noto Serif SC", serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  const sideColumns = [
    { x: width * 0.07, columns: CALLIGRAPHY_COLUMNS.slice(0, 4) },
    { x: width * 0.93, columns: CALLIGRAPHY_COLUMNS.slice(4) }
  ];

  sideColumns.forEach((side, sideIndex) => {
    side.columns.forEach((column, columnIndex) => {
      const columnX = side.x + (sideIndex === 0 ? 1 : -1) * columnIndex * fontSize * 1.55;
      const startY = height * (0.1 + columnIndex * 0.045);
      for (let i = 0; i < column.length; i += 1) {
        const charY = startY + i * fontSize * 1.18;
        if (charY > height * 0.95) break;
        ctx.fillStyle = `rgba(214, 178, 112, ${0.028 + (columnIndex % 2) * 0.014})`;
        ctx.fillText(column[i], columnX, charY);
      }
    });
  });

  return backdrop;
}

function ParticleSilhouette({ status }: { status: AssistantStatus }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const statusRef = useRef(status);

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    let frame = 0;
    let animationId = 0;
    let disposed = false;
    let particles: Particle[] = [];
    let backdrop: HTMLCanvasElement | null = null;
    let sample: SilhouetteSample | null = null;

    const rebuild = () => {
      const rect = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.floor(rect.width * ratio);
      canvas.height = Math.floor(rect.height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      particles = sample
        ? particlesFromSample(sample, rect.width, rect.height)
        : makeParticles(rect.width, rect.height);
      backdrop = buildCalligraphyBackdrop(rect.width, rect.height);
    };

    const observer = new ResizeObserver(rebuild);
    observer.observe(canvas);
    rebuild();

    void loadSilhouetteSample().then((loaded) => {
      if (disposed || !loaded) return;
      sample = loaded;
      rebuild();
    });

    const draw = () => {
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      frame += 1;

      const state = statusRef.current;
      const amplitude = state === "speaking" ? 11 : state === "thinking" ? 7 : state === "listening" ? 9 : 2.6;
      const speed = state === "speaking" ? 0.1 : state === "thinking" ? 0.065 : state === "listening" ? 0.085 : 0.03;
      const centerX = width * 0.5;
      const centerY = height * 0.56;

      context.clearRect(0, 0, width, height);
      context.fillStyle = "#050604";
      context.fillRect(0, 0, width, height);

      if (backdrop) {
        context.drawImage(backdrop, 0, 0, width, height);
      }

      // 人物身后的暖色辉光
      const glow = context.createRadialGradient(
        centerX,
        centerY,
        0,
        centerX,
        centerY,
        Math.max(width, height) * 0.5
      );
      glow.addColorStop(0, "rgba(150, 112, 52, 0.13)");
      glow.addColorStop(0.55, "rgba(110, 84, 40, 0.05)");
      glow.addColorStop(1, "rgba(0, 0, 0, 0)");
      context.fillStyle = glow;
      context.fillRect(0, 0, width, height);

      context.save();
      context.lineWidth = 1;
      for (let i = 0; i < 7; i += 1) {
        const ringPhase = frame * speed * 0.55 + i * 0.9;
        const pulse = Math.sin(ringPhase) * (state === "speaking" ? 9 : 3);
        const ringAlpha = 0.1 - i * 0.011 + (state === "idle" ? 0 : Math.sin(ringPhase) * 0.02);
        context.strokeStyle = `rgba(198, 160, 88, ${Math.max(0.018, ringAlpha)})`;
        context.beginPath();
        context.ellipse(
          centerX,
          height * 0.6,
          width * (0.18 + i * 0.075) + pulse,
          height * (0.05 + i * 0.028),
          0,
          0,
          Math.PI * 2
        );
        context.stroke();
      }
      context.restore();

      for (const p of particles) {
        const dx = p.tx - centerX;
        const dy = p.ty - centerY;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const wave = Math.sin(frame * speed + p.phase + dist * 0.016);
        const targetX = p.tx + (dx / dist) * wave * amplitude;
        const targetY = p.ty + (dy / dist) * wave * amplitude * 0.5;

        p.vx += (targetX - p.x) * 0.048;
        p.vy += (targetY - p.y) * 0.048;
        p.vx *= 0.8;
        p.vy *= 0.8;
        p.x += p.vx;
        p.y += p.vy;

        const flicker = 0.78 + 0.22 * Math.sin(frame * 0.024 + p.phase * 3.1);
        const r = Math.round(176 + p.tone * 72);
        const g = Math.round(128 + p.tone * 64);
        const b = Math.round(70 + p.tone * 38);
        // fillRect 比 arc 快一个量级，粒子很小肉眼看不出方圆差别。
        const extent = p.size * 1.6;
        if (p.tone > 0.78) {
          // 亮粒子加一层柔和光晕，贴近设计稿的轮廓光效果。
          context.fillStyle = `rgba(${r}, ${g}, ${b}, ${0.1 * flicker})`;
          const halo = extent * 3.2;
          context.fillRect(p.x - halo / 2, p.y - halo / 2, halo, halo);
        }
        context.fillStyle = `rgba(${r}, ${g}, ${b}, ${p.alpha * flicker})`;
        context.fillRect(p.x - extent / 2, p.y - extent / 2, extent, extent);
      }

      animationId = requestAnimationFrame(draw);
    };

    draw();
    return () => {
      disposed = true;
      observer.disconnect();
      cancelAnimationFrame(animationId);
    };
  }, []);

  return <canvas ref={canvasRef} className="particle-canvas" aria-label="粒子构成的倪师数字人剪影" />;
}

function ChatBubble({ message, onOpenRetrieval }: { message: ChatMessage; onOpenRetrieval: (message: ChatMessage) => void }) {
  const isUser = message.role === "user";
  const isPendingAssistant = !isUser && !message.content;
  const isTranscribingUser = isUser && message.status === "transcribing";
  const canInspectRetrieval = !isUser && !isPendingAssistant && !isTranscribingUser;
  return (
    <article className={`message ${isUser ? "user" : "assistant"}`}>
      {!isUser && <div className="assistant-mark">倪</div>}
      <div className="message-body">
        <div className="message-meta">
          <time>{message.time}</time>
        </div>
        <div className={`bubble ${isPendingAssistant || isTranscribingUser ? "stream-loading" : ""}`}>
          {isTranscribingUser ? (
            <div className="thinking-inline" aria-live="polite">
              <span>正在识别语音</span>
              <i />
              <i />
              <i />
            </div>
          ) : isPendingAssistant ? (
            <div className="thinking-inline" aria-live="polite">
              <span>正在思考</span>
              <i />
              <i />
              <i />
            </div>
          ) : (
            message.content.split("\n").map((line, index) => (
              <p key={`${message.id}-${index}`}>{line}</p>
            ))
          )}
        </div>
        {canInspectRetrieval && (
          <button
            type="button"
            className="retrieval-open-button"
            onClick={() => onOpenRetrieval(message)}
            aria-label="检查命中"
            title="检查命中"
          >
            检查命中
          </button>
        )}
      </div>
      {isUser && (
        <div className="user-mark">
          <UserRound size={17} />
        </div>
      )}
    </article>
  );
}

function RetrievalDialog({ message, onClose }: { message: ChatMessage; onClose: () => void }) {
  const hits = message.retrievalHits || [];
  const counts = retrievalSourceCounts(hits);
  const info = message.retrievalInfo || {};
  const mode = typeof info.retrieval_mode === "string" ? info.retrieval_mode : "unknown";
  const requestedMode = typeof info.requested_mode === "string" ? info.requested_mode : "";
  const fallback = Boolean(info.fallback);

  return (
    <div className="settings-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="retrieval-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="retrieval-modal-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="settings-modal-header">
          <div>
            <p>本地缓存 · 刷新后清除</p>
            <h2 id="retrieval-modal-title">检查命中</h2>
          </div>
          <button type="button" className="modal-close-button" onClick={onClose} aria-label="关闭命中详情">
            <X size={18} />
          </button>
        </header>

        <div className="retrieval-summary" aria-label="检索摘要">
          <span>
            <Database size={15} />
            {mode}
            {requestedMode && requestedMode !== mode ? ` / 请求 ${requestedMode}` : ""}
          </span>
          <span>FTS {counts.fts}</span>
          <span>向量 {counts.vector}</span>
          <span>混合 {counts.hybrid}</span>
          {fallback && <span className="warning">已回退</span>}
        </div>

        <div className="retrieval-hit-list">
          {hits.length ? (
            hits.map((hit, index) => (
              <article className="retrieval-hit" key={`${hit.chunk_id || hit.title}-${index}`}>
                <header>
                  <span className={`retrieval-source ${hit.match_source || "fts"}`}>
                    {retrievalSourceLabel(hit.match_source)}
                  </span>
                  {typeof hit.score === "number" && <span className="retrieval-score">{hit.score.toFixed(3)}</span>}
                </header>
                <strong>{hit.title || "未命名资料"}</strong>
                <p className="retrieval-path">
                  {[hit.course, hit.chapter, hit.timestamp || hit.page].filter(Boolean).join(" / ") || "未标注章节"}
                </p>
                <p className="retrieval-snippet">{hit.snippet || "这条命中没有返回片段内容。"}</p>
              </article>
            ))
          ) : (
            <div className="retrieval-empty">
              <Database size={20} />
              <p>这条回复没有可展示的检索命中。</p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function VoiceWave({
  status,
  recording,
  voiceCallActive
}: {
  status: AssistantStatus;
  recording: boolean;
  voiceCallActive: boolean;
}) {
  const active =
    voiceCallActive ||
    recording ||
    status === "listening" ||
    status === "transcribing" ||
    status === "speaking" ||
    status === "thinking";

  return (
    <div className={`voice-wave ${active ? "active" : ""} ${status}`} aria-label="语音波纹">
      <Volume2 size={15} />
      <div className="wave-bars" aria-hidden="true">
        {Array.from({ length: 38 }).map((_, index) => (
          <i key={index} style={{ animationDelay: `${index * 0.035}s` }} />
        ))}
      </div>
      <span>
        {recording
          ? "正在听你说话"
          : status === "transcribing"
            ? "正在识别语音"
            : status === "speaking"
              ? "正在朗读回答"
              : voiceCallActive
                ? "实时通话已开启"
              : "语音聊天已就绪"}
      </span>
    </div>
  );
}

const VOICE_SPEECH_THRESHOLD = 0.035;
const VOICE_SILENCE_MS = 1200;
const VOICE_MAX_SEGMENT_MS = 30000;

export default function NishiDesktop() {
  const [status, setStatus] = useState<AssistantStatus>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadCachedMessages());
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [recording, setRecording] = useState(false);
  const [voiceCallActive, setVoiceCallActive] = useState(false);
  const [aiSettings, setAiSettings] = useState<AiSettings>(defaultAiSettings);
  const [settingsHydrated, setSettingsHydrated] = useState(false);
  const [activeSettingsTab, setActiveSettingsTab] = useState<SettingsTab>("general");
  const [minimaxVoiceCatalog, setMinimaxVoiceCatalog] = useState<MinimaxVoiceCatalog>({
    system_voice: fallbackMinimaxSystemVoices,
    voice_cloning: [],
    voice_generation: []
  });
  const [minimaxVoiceLoading, setMinimaxVoiceLoading] = useState(false);
  const [minimaxVoiceError, setMinimaxVoiceError] = useState("");
  const [voiceCloneSample, setVoiceCloneSample] = useState<VoiceCloneSample | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [retrievalMessageId, setRetrievalMessageId] = useState<string | null>(null);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const statusRef = useRef<AssistantStatus>("idle");
  const voiceCallActiveRef = useRef(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const transcribingMessageIdRef = useRef<string | null>(null);
  const activeStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const voiceMonitorFrameRef = useRef<number | null>(null);
  const voiceRestartTimerRef = useRef<number | null>(null);
  const voiceSegmentStartedAtRef = useRef(0);
  const speechDetectedRef = useRef(false);
  const silenceStartedAtRef = useRef<number | null>(null);
  const recorderStopModeRef = useRef<"transcribe" | "cancel">("cancel");
  const startVoiceListeningRef = useRef<() => Promise<void>>(async () => {});
  const cloneFileInputRef = useRef<HTMLInputElement | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, status]);

  useEffect(() => {
    const clearChatCache = () => {
      try {
        window.localStorage.removeItem(CHAT_STORAGE_KEY);
      } catch {
        // Best effort: chat cache should never block page unload.
      }
    };
    window.addEventListener("beforeunload", clearChatCache);
    return () => window.removeEventListener("beforeunload", clearChatCache);
  }, []);

  useEffect(() => {
    try {
      if (messages.length <= 1 && messages[0]?.id === "hello") {
        window.localStorage.removeItem(CHAT_STORAGE_KEY);
        return;
      }
      window.localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages.slice(-CHAT_CACHE_LIMIT)));
    } catch {
      // In-memory chat remains available even if local cache is blocked.
    }
  }, [messages]);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
      if (saved) {
        setAiSettings(mergeAiSettings(JSON.parse(saved)));
      }
      const savedCatalog = window.localStorage.getItem(VOICE_CATALOG_STORAGE_KEY);
      if (savedCatalog) {
        const catalog = JSON.parse(savedCatalog) as MinimaxVoiceCatalog;
        setMinimaxVoiceCatalog({
          system_voice: Array.isArray(catalog.system_voice) && catalog.system_voice.length ? catalog.system_voice : fallbackMinimaxSystemVoices,
          voice_cloning: Array.isArray(catalog.voice_cloning) ? catalog.voice_cloning : [],
          voice_generation: Array.isArray(catalog.voice_generation) ? catalog.voice_generation : []
        });
      }
      const savedSample = window.localStorage.getItem(VOICE_SAMPLE_STORAGE_KEY);
      if (savedSample) {
        setVoiceCloneSample(JSON.parse(savedSample) as VoiceCloneSample);
      }
    } catch {
      setAiSettings(defaultAiSettings);
    } finally {
      setSettingsHydrated(true);
    }
  }, []);

  useEffect(() => {
    if (!settingsHydrated) return;
    try {
      window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(aiSettings));
    } catch {
      // Local settings remain usable for the current session even when storage is full or blocked.
    }
  }, [aiSettings, settingsHydrated]);

  useEffect(() => {
    if (!settingsHydrated) return;
    try {
      if (voiceCloneSample) {
        window.localStorage.setItem(VOICE_SAMPLE_STORAGE_KEY, JSON.stringify(voiceCloneSample));
      } else {
        window.localStorage.removeItem(VOICE_SAMPLE_STORAGE_KEY);
      }
    } catch {
      setError("克隆音频样本较大，浏览器缓存空间不足；模型与音色选择仍会保存。");
    }
  }, [voiceCloneSample, settingsHydrated]);

  useEffect(() => {
    if (!settingsHydrated) return;
    try {
      window.localStorage.setItem(VOICE_CATALOG_STORAGE_KEY, JSON.stringify(minimaxVoiceCatalog));
    } catch {
      // The catalog is only a convenience cache; settings themselves are stored separately.
    }
  }, [minimaxVoiceCatalog, settingsHydrated]);

  useEffect(() => {
    if (!settingsOpen && !retrievalMessageId) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSettingsOpen(false);
        setRetrievalMessageId(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [settingsOpen, retrievalMessageId]);

  const updateAiSettings = useCallback((patch: Partial<AiSettings>) => {
    setAiSettings((current) => ({ ...current, ...patch }));
  }, []);

  const activateAiSettings = useCallback((patch: Partial<AiSettings>) => {
    setAiSettings((current) => ({ ...current, active: true, ...patch }));
  }, []);

  const updateProviderSettings = useCallback(
    <Key extends "openai" | "mimo" | "minimax">(key: Key, patch: Partial<AiSettings[Key]>) => {
      setAiSettings((current) => ({
        ...current,
        [key]: {
          ...current[key],
          ...patch
        }
      }));
    },
    []
  );

  const minimaxSystemVoiceOptions = uniqueVoices([
    ...minimaxVoiceCatalog.system_voice,
    ...fallbackMinimaxSystemVoices,
    aiSettings.minimax.voiceId ? { voice_id: aiSettings.minimax.voiceId, voice_name: "当前选择" } : { voice_id: "" }
  ]);
  const minimaxCloneVoiceOptions = uniqueVoices([
    ...minimaxVoiceCatalog.voice_cloning,
    aiSettings.minimax.cloneVoiceId ? { voice_id: aiSettings.minimax.cloneVoiceId, voice_name: "当前复刻音色" } : { voice_id: "" }
  ]);
  const speechNeedsMimoSettings = aiSettings.sttProvider === "mimo" || aiSettings.ttsProvider === "mimo";
  const speechNeedsMinimaxSettings = aiSettings.ttsProvider === "minimax";
  const cloneNeedsMimoSettings = aiSettings.cloneProvider === "mimo";
  const cloneNeedsMinimaxSettings = aiSettings.cloneProvider === "minimax";
  const cloneActive =
    voiceCloneSample ||
    (aiSettings.active &&
      aiSettings.cloneProvider !== "none" &&
      ((aiSettings.cloneProvider === "minimax" && Boolean(aiSettings.minimax.cloneVoiceId)) ||
        (aiSettings.cloneProvider === "mimo" && Boolean(aiSettings.mimo.ttsVoiceCloneModel))));

  const refreshMinimaxVoices = useCallback(async () => {
    setMinimaxVoiceLoading(true);
    setMinimaxVoiceError("");
    try {
      const response = await fetch("/api/voices/minimax", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          voice_type: "all",
          provider_config: {
            minimax: aiSettings.minimax
          }
        })
      });
      const data = await response.json();
      if (data.error) {
        throw new Error(String(data.error));
      }
      setMinimaxVoiceCatalog({
        system_voice: Array.isArray(data.system_voice) && data.system_voice.length ? data.system_voice : fallbackMinimaxSystemVoices,
        voice_cloning: Array.isArray(data.voice_cloning) ? data.voice_cloning : [],
        voice_generation: Array.isArray(data.voice_generation) ? data.voice_generation : []
      });
    } catch (voiceError) {
      setMinimaxVoiceError(String(voiceError));
    } finally {
      setMinimaxVoiceLoading(false);
    }
  }, [aiSettings.minimax]);

  const clearVoiceRestartTimer = useCallback(() => {
    if (voiceRestartTimerRef.current !== null) {
      window.clearTimeout(voiceRestartTimerRef.current);
      voiceRestartTimerRef.current = null;
    }
  }, []);

  const applyStatus = useCallback((nextStatus: AssistantStatus) => {
    statusRef.current = nextStatus;
    setStatus(nextStatus);
  }, []);

  const stopVoiceMonitor = useCallback(() => {
    if (voiceMonitorFrameRef.current !== null) {
      window.cancelAnimationFrame(voiceMonitorFrameRef.current);
      voiceMonitorFrameRef.current = null;
    }
    const context = audioContextRef.current;
    audioContextRef.current = null;
    if (context && context.state !== "closed") {
      void context.close().catch(() => undefined);
    }
  }, []);

  const stopActiveStream = useCallback(() => {
    activeStreamRef.current?.getTracks().forEach((track) => track.stop());
    activeStreamRef.current = null;
  }, []);

  const queueVoiceListeningRestart = useCallback(() => {
    clearVoiceRestartTimer();
    if (!voiceCallActiveRef.current) return;
    voiceRestartTimerRef.current = window.setTimeout(() => {
      voiceRestartTimerRef.current = null;
      if (!voiceCallActiveRef.current) return;
      if (statusRef.current !== "idle") {
        queueVoiceListeningRestart();
        return;
      }
      void startVoiceListeningRef.current();
    }, 500);
  }, [clearVoiceRestartTimer]);

  const createTranscribingMessage = useCallback(() => {
    const transcribingMessageId = `user-stt-${Date.now()}`;
    transcribingMessageIdRef.current = transcribingMessageId;
    setMessages((items) => [
      ...items,
      {
        id: transcribingMessageId,
        role: "user",
        time: nowTime(),
        content: "",
        status: "transcribing"
      }
    ]);
    return transcribingMessageId;
  }, []);

  const stopRecordingForTranscription = useCallback(() => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    recorderStopModeRef.current = "transcribe";
    createTranscribingMessage();
    stopVoiceMonitor();
    recorder.stop();
    setRecording(false);
    applyStatus("transcribing");
  }, [applyStatus, createTranscribingMessage, stopVoiceMonitor]);

  const speakAnswer = useCallback(async (answer: string, stylePrompt = "") => {
    applyStatus("speaking");
    try {
      const ttsProvider = aiSettings.active ? aiSettings.ttsProvider : "env";
      const useSelectedMinimaxClone =
        ttsProvider === "minimax" &&
        aiSettings.cloneProvider === "minimax" &&
        Boolean(aiSettings.minimax.cloneVoiceId.trim());
      const clonePayload =
        voiceCloneSample && !useSelectedMinimaxClone
          ? {
              data_url: voiceCloneSample.dataUrl,
              mime_type: voiceCloneSample.mimeType,
              file_name: voiceCloneSample.name
            }
          : undefined;
      const response = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: answer,
          style_prompt: stylePrompt,
          provider_config: providerConfig(aiSettings),
          voice: aiSettings.mimo.voice || "冰糖",
          format: ttsProvider === "minimax" ? "mp3" : "wav",
          voice_clone: clonePayload
        })
      });
      const data = await response.json();
      if (data.error) {
        throw new Error(String(data.error));
      }
      const audioData = String(data.audio_data || "");
      if (audioData) {
        await new Promise<void>((resolve) => {
          let finished = false;
          let fallbackTimer = 0;
          const finish = () => {
            if (finished) return;
            finished = true;
            window.clearTimeout(fallbackTimer);
            applyStatus("idle");
            resolve();
          };
          fallbackTimer = window.setTimeout(finish, 60000);
          const audio = playBase64Audio(audioData, String(data.format || "wav"), finish);
          if (!audio) finish();
        });
        return;
      }
    } catch {
      // Keep the chat usable even when TTS is not configured.
    }
    await new Promise<void>((resolve) => {
      window.setTimeout(() => {
        applyStatus("idle");
        resolve();
      }, 900);
    });
  }, [aiSettings, applyStatus, voiceCloneSample]);

  const selectVoiceCloneSample = async (file?: File) => {
    setError("");
    if (!file) return;
    const allowedTypes = new Set(["audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3"]);
    if (!allowedTypes.has(file.type)) {
      setError("克隆音色样本仅支持 mp3 或 wav 文件。");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError("克隆音色样本不能超过 10MB。");
      return;
    }
    const dataUrl = await blobToBase64(file);
    setVoiceCloneSample({
      name: file.name,
      dataUrl,
      mimeType: file.type || "audio/wav",
      size: file.size
    });
  };

  const sendQuestion = useCallback(
    async (override?: string, existingUserMessageId?: string, continueVoiceCall = false) => {
      const question = (override ?? input).trim();
      if (!question || status === "thinking") return;

      setError("");
      setInput("");
      applyStatus("thinking");
      const assistantId = `assistant-${Date.now()}`;
      const questionTime = nowTime();
      const requestHistory = messages
        .slice(-CHAT_HISTORY_LIMIT)
        .filter((message) => message.content.trim())
        .map((message) => ({
          role: message.role,
          content: message.content
        }));
      setStreamingMessageId(assistantId);
      setMessages((items) => {
        let matchedExistingUser = false;
        const nextItems = existingUserMessageId
          ? items.map((message) => {
              if (message.id !== existingUserMessageId) return message;
              matchedExistingUser = true;
              const nextMessage = {
                ...message,
                content: question
              };
              delete nextMessage.status;
              return nextMessage;
            })
          : [
              ...items,
              {
                id: `user-${Date.now()}`,
                role: "user" as const,
                time: questionTime,
                content: question
              }
            ];

        if (existingUserMessageId && !matchedExistingUser) {
          nextItems.push({
            id: existingUserMessageId,
            role: "user",
            time: questionTime,
            content: question
          });
        }

        return [
          ...nextItems,
          {
            id: assistantId,
            role: "assistant",
            time: questionTime,
            content: ""
          }
        ];
      });

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question,
            history: requestHistory,
            domain: "auto",
            top_k: 5,
            mode: aiSettings.retrievalMode,
            style_intensity: "medium",
            timezone: "Asia/Shanghai",
            provider_config: providerConfig(aiSettings)
          })
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${await response.text()}`);
        }

        if (!response.body) {
          throw new Error("响应没有可读取的流。");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let answer = "";
        let doneData: Record<string, unknown> = {};

        const applyMeta = (data: Record<string, unknown>) => {
          setMessages((items) =>
            items.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    domain: typeof data.domain === "string" ? data.domain : message.domain,
                    citations: Array.isArray(data.citations) ? data.citations : message.citations,
                    retrievalHits: Array.isArray(data.retrieval_hits)
                      ? normalizedRetrievalHits(data.retrieval_hits)
                      : message.retrievalHits,
                    retrievalInfo:
                      data.retrieval_info && typeof data.retrieval_info === "object" && !Array.isArray(data.retrieval_info)
                        ? (data.retrieval_info as Record<string, unknown>)
                        : message.retrievalInfo,
                    safetyNotes: Array.isArray(data.safety_notes) ? data.safety_notes : message.safetyNotes
                  }
                : message
            )
          );
        };

        const applyDelta = (text: string) => {
          answer += text;
          setMessages((items) =>
            items.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    content: answer
                  }
                : message
            )
          );
        };

        const handleEvent = (parsed: { event: string; data: unknown } | null) => {
          if (!parsed) return;
          const data = typeof parsed.data === "object" && parsed.data ? (parsed.data as Record<string, unknown>) : {};

          if (parsed.event === "meta") {
            applyMeta(data);
          } else if (parsed.event === "delta") {
            applyDelta(String(data.text || ""));
          } else if (parsed.event === "done") {
            doneData = data;
            if (typeof data.generation_error === "string" && data.generation_error.trim()) {
              setError(data.generation_error.trim());
            }
            answer = String(data.answer || answer || "我没有生成回答，请再问一次。");
            setMessages((items) =>
              items.map((message) =>
                message.id === assistantId
                  ? {
                      ...message,
                      content: answer,
                      domain: typeof data.domain === "string" ? data.domain : message.domain,
                      citations: Array.isArray(data.citations) ? data.citations : message.citations,
                      retrievalHits: Array.isArray(data.retrieval_hits)
                        ? normalizedRetrievalHits(data.retrieval_hits)
                        : message.retrievalHits,
                      retrievalInfo:
                        data.retrieval_info && typeof data.retrieval_info === "object" && !Array.isArray(data.retrieval_info)
                          ? (data.retrieval_info as Record<string, unknown>)
                          : message.retrievalInfo,
                      safetyNotes: Array.isArray(data.safety_notes) ? data.safety_notes : message.safetyNotes
                    }
                  : message
              )
            );
          } else if (parsed.event === "error") {
            throw new Error(String(data.error || "流式输出失败。"));
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split(/\r?\n\r?\n/);
          buffer = blocks.pop() || "";
          blocks.forEach((block) => handleEvent(parseSseBlock(block)));
        }

        if (buffer.trim()) {
          handleEvent(parseSseBlock(buffer));
        }

        if (aiSettings.autoSpeak) {
          const persona =
            typeof doneData.persona === "object" && doneData.persona
              ? (doneData.persona as Record<string, unknown>)
              : {};
          setStreamingMessageId(null);
          await speakAnswer(answer, String(persona.style_prompt || ""));
          if (continueVoiceCall) queueVoiceListeningRestart();
        } else {
          setStreamingMessageId(null);
          applyStatus("idle");
          if (continueVoiceCall) queueVoiceListeningRestart();
        }
      } catch (requestError) {
        setError(String(requestError));
        setStreamingMessageId(null);
        setMessages((items) =>
          items.map((message) =>
            message.id === assistantId && !message.content
              ? {
                  ...message,
                  content: "这次流式输出没有完成，请再试一次。"
                }
              : message
          )
        );
        applyStatus("idle");
        if (continueVoiceCall) queueVoiceListeningRestart();
      }
    },
    [aiSettings, applyStatus, input, messages, queueVoiceListeningRestart, speakAnswer, status]
  );

  const startVoiceListening = useCallback(async () => {
    if (!voiceCallActiveRef.current) return;
    if (recorderRef.current && recorderRef.current.state !== "inactive") return;
    if (statusRef.current !== "idle") {
      queueVoiceListeningRestart();
      return;
    }

    clearVoiceRestartTimer();
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      activeStreamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorderRef.current = recorder;
      recorderStopModeRef.current = "cancel";
      speechDetectedRef.current = false;
      silenceStartedAtRef.current = null;
      voiceSegmentStartedAtRef.current = performance.now();
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        stopVoiceMonitor();
        stopActiveStream();
        recorderRef.current = null;
        setRecording(false);
        const shouldTranscribe = recorderStopModeRef.current === "transcribe";
        const transcribingMessageId = transcribingMessageIdRef.current || undefined;
        const updateTranscribingMessage = (content: string) => {
          if (!transcribingMessageId) return;
          setMessages((items) =>
            items.map((message) => {
              if (message.id !== transcribingMessageId) return message;
              const nextMessage = {
                ...message,
                content
              };
              delete nextMessage.status;
              return nextMessage;
            })
          );
        };
        if (!shouldTranscribe) {
          transcribingMessageIdRef.current = null;
          if (!voiceCallActiveRef.current || statusRef.current === "listening") applyStatus("idle");
          return;
        }

        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        try {
          const audioData = await blobToWavBase64(blob);
          const response = await fetch("/api/stt", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              audio_data: audioData,
              mime_type: "audio/wav",
              language: "auto",
              provider_config: providerConfig(aiSettings)
            })
          });
          const data = await response.json();
          const transcript = String(data.text || "").trim();
          if (transcript) {
            await sendQuestion(transcript, transcribingMessageId, voiceCallActiveRef.current);
          } else {
            updateTranscribingMessage("没有识别到语音内容。");
            applyStatus("idle");
            setError(data.error || "没有识别到语音内容。");
            queueVoiceListeningRestart();
          }
        } catch (sttError) {
          updateTranscribingMessage("语音识别失败，请检查 STT 配置。");
          applyStatus("idle");
          setError(String(sttError));
          queueVoiceListeningRestart();
        } finally {
          transcribingMessageIdRef.current = null;
        }
      };
      transcribingMessageIdRef.current = null;
      recorder.start();
      setRecording(true);
      applyStatus("listening");

      const AudioContextConstructor =
        window.AudioContext ||
        (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioContextConstructor) return;

      const audioContext = new AudioContextConstructor();
      audioContextRef.current = audioContext;
      if (audioContext.state === "suspended") {
        await audioContext.resume().catch(() => undefined);
      }
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);
      const samples = new Uint8Array(analyser.fftSize);

      const monitorVoice = () => {
        if (recorderRef.current !== recorder || recorder.state === "inactive") return;
        analyser.getByteTimeDomainData(samples);
        let sum = 0;
        for (const sample of samples) {
          const normalized = (sample - 128) / 128;
          sum += normalized * normalized;
        }
        const volume = Math.sqrt(sum / samples.length);
        const now = performance.now();
        if (volume > VOICE_SPEECH_THRESHOLD) {
          speechDetectedRef.current = true;
          silenceStartedAtRef.current = null;
        } else if (speechDetectedRef.current) {
          if (silenceStartedAtRef.current === null) {
            silenceStartedAtRef.current = now;
          } else if (now - silenceStartedAtRef.current >= VOICE_SILENCE_MS) {
            stopRecordingForTranscription();
            return;
          }
        }

        if (speechDetectedRef.current && now - voiceSegmentStartedAtRef.current >= VOICE_MAX_SEGMENT_MS) {
          stopRecordingForTranscription();
          return;
        }

        voiceMonitorFrameRef.current = window.requestAnimationFrame(monitorVoice);
      };
      voiceMonitorFrameRef.current = window.requestAnimationFrame(monitorVoice);
    } catch (recordError) {
      voiceCallActiveRef.current = false;
      setVoiceCallActive(false);
      setError(`无法打开麦克风：${String(recordError)}`);
      applyStatus("idle");
    }
  }, [
    applyStatus,
    clearVoiceRestartTimer,
    queueVoiceListeningRestart,
    sendQuestion,
    stopActiveStream,
    stopRecordingForTranscription,
    stopVoiceMonitor
  ]);

  useEffect(() => {
    startVoiceListeningRef.current = startVoiceListening;
  }, [startVoiceListening]);

  useEffect(
    () => () => {
      voiceCallActiveRef.current = false;
      clearVoiceRestartTimer();
      stopVoiceMonitor();
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        recorderStopModeRef.current = "cancel";
        recorderRef.current.stop();
      }
      stopActiveStream();
    },
    [clearVoiceRestartTimer, stopActiveStream, stopVoiceMonitor]
  );

  const stopVoiceCall = useCallback(() => {
    voiceCallActiveRef.current = false;
    setVoiceCallActive(false);
    clearVoiceRestartTimer();
    stopVoiceMonitor();
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorderStopModeRef.current = "cancel";
      recorder.stop();
    } else {
      stopActiveStream();
      if (statusRef.current === "listening") applyStatus("idle");
    }
  }, [applyStatus, clearVoiceRestartTimer, stopActiveStream, stopVoiceMonitor]);

  const toggleRecording = async () => {
    setError("");
    if (voiceCallActiveRef.current) {
      stopVoiceCall();
      return;
    }

    voiceCallActiveRef.current = true;
    setVoiceCallActive(true);
    await startVoiceListening();
  };

  const selectedRetrievalMessage = retrievalMessageId
    ? messages.find((message) => message.id === retrievalMessageId) || null
    : null;

  return (
    <main className="simple-shell">
      <section className="avatar-panel">
        <div className="avatar-heading">
          <div className="brand">
            <span className="brand-seal" aria-hidden="true">倪</span>
            <div>
              <h1>倪师数字人</h1>
              <p>{statusText(status, recording, voiceCallActive)}</p>
            </div>
          </div>
          <span className={`live-dot ${status}`} />
        </div>
        <div className="avatar-stage">
          <ParticleSilhouette status={status} />
        </div>
        <VoiceWave status={status} recording={recording} voiceCallActive={voiceCallActive} />
      </section>

      <section className="chat-panel">
        <div className="chat-toolbar">
          <div>
            <span>会话</span>
            <strong>{cloneActive ? "复刻音色已启用" : "默认音色"}</strong>
          </div>
          <button
            type="button"
            className="settings-button"
            onClick={() => setSettingsOpen(true)}
            aria-label="打开语音设置"
            title="语音设置"
          >
            <Settings size={18} />
          </button>
        </div>

        <div className="messages" ref={scrollerRef}>
          {messages.map((message) => (
            <ChatBubble key={message.id} message={message} onOpenRetrieval={(item) => setRetrievalMessageId(item.id)} />
          ))}
          {status === "thinking" && !streamingMessageId && (
            <article className="message assistant">
              <div className="assistant-mark">倪</div>
              <div className="message-body">
                <time>{nowTime()}</time>
                <div className="bubble typing">正在整理回答...</div>
              </div>
            </article>
          )}
        </div>

        {error && <div className="error-line">{error}</div>}

        <footer className="chat-composer">
          <button
            type="button"
            className={`voice-button ${voiceCallActive ? "recording" : ""}`}
            onClick={toggleRecording}
            title={voiceCallActive ? "结束实时通话" : "开始实时通话"}
          >
            {voiceCallActive ? <Square size={22} /> : <Mic size={24} />}
          </button>
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void sendQuestion();
              }
            }}
            placeholder="输入问题，Enter 发送"
          />
          <button type="button" className="send-button" onClick={() => void sendQuestion()} title="发送">
            <Send size={22} />
          </button>
        </footer>

        <div className="voice-hint">
          <span>{voiceCallActive ? "停顿后自动识别并发送" : "点击麦克风开始实时通话"}</span>
          <label className="auto-speak-toggle">
            <input
              type="checkbox"
              checked={aiSettings.autoSpeak}
              onChange={(event) => updateAiSettings({ autoSpeak: event.currentTarget.checked })}
            />
            <span className="toggle-track" aria-hidden="true">
              <span />
            </span>
            <span>回答后自动朗读</span>
          </label>
        </div>
      </section>

      {selectedRetrievalMessage && (
        <RetrievalDialog message={selectedRetrievalMessage} onClose={() => setRetrievalMessageId(null)} />
      )}

      {settingsOpen && (
        <div className="settings-backdrop" role="presentation" onMouseDown={() => setSettingsOpen(false)}>
          <section
            className="settings-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="ai-settings-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="settings-modal-header">
              <div>
                <p>本地持久化设置</p>
                <h2 id="ai-settings-title">模型与语音配置</h2>
              </div>
              <button type="button" className="modal-close-button" onClick={() => setSettingsOpen(false)} aria-label="关闭设置">
                <X size={18} />
              </button>
            </header>

            <nav className="settings-tabs" aria-label="设置分类">
              {([
                ["general", "总开关"],
                ["llm", "LLM"],
                ["speech", "语音"],
                ["clone", "克隆"]
              ] as Array<[SettingsTab, string]>).map(([tab, label]) => (
                <button
                  key={tab}
                  type="button"
                  className={activeSettingsTab === tab ? "active" : ""}
                  onClick={() => setActiveSettingsTab(tab)}
                >
                  {label}
                </button>
              ))}
            </nav>

            {activeSettingsTab === "general" && (
              <div className="settings-tab-panel">
                <label className="settings-switch-row flush">
                  <div>
                    <strong>启用本地配置</strong>
                    <span>勾选后，本页保存的 API Key、模型和语音服务会覆盖环境变量。</span>
                  </div>
                  <span className="auto-speak-toggle compact">
                    <input
                      type="checkbox"
                      checked={aiSettings.active}
                      onChange={(event) => updateAiSettings({ active: event.currentTarget.checked })}
                    />
                    <span className="toggle-track" aria-hidden="true">
                      <span />
                    </span>
                  </span>
                </label>
                <label className="settings-switch-row">
                  <div>
                    <strong>回答后自动朗读</strong>
                    <span>开启后，每次回答都会按当前 TTS 服务播放。</span>
                  </div>
                  <span className="auto-speak-toggle compact">
                    <input
                      type="checkbox"
                      checked={aiSettings.autoSpeak}
                      onChange={(event) => updateAiSettings({ autoSpeak: event.currentTarget.checked })}
                    />
                    <span className="toggle-track" aria-hidden="true">
                      <span />
                    </span>
                  </span>
                </label>
                <label className="settings-field">
                  <span>检索模式</span>
                  <select
                    value={aiSettings.retrievalMode}
                    onChange={(event) => updateAiSettings({ retrievalMode: event.currentTarget.value as AiSettings["retrievalMode"] })}
                  >
                    <option value="hybrid">混合检索</option>
                    <option value="fts">FTS5</option>
                    <option value="auto">自动</option>
                  </select>
                </label>
              </div>
            )}

            {activeSettingsTab === "llm" && (
              <div className="settings-tab-panel">
                <label className="settings-field">
                  <span>LLM 服务</span>
                  <select
                    value={aiSettings.llmProvider}
                    onChange={(event) => activateAiSettings({ llmProvider: event.currentTarget.value as LlmProvider })}
                  >
                    <option value="env">环境变量 MiMo</option>
                    <option value="mimo">MiMo</option>
                    <option value="openai">OpenAI-compatible</option>
                    <option value="local">仅本地草稿</option>
                  </select>
                </label>
                {aiSettings.llmProvider === "openai" && (
                  <div className="settings-grid">
                    <label className="settings-field span-2">
                      <span>Base URL</span>
                      <input
                        value={aiSettings.openai.baseUrl}
                        onChange={(event) => updateProviderSettings("openai", { baseUrl: event.currentTarget.value })}
                      />
                    </label>
                    <label className="settings-field">
                      <span>模型</span>
                      <input
                        value={aiSettings.openai.model}
                        onChange={(event) => updateProviderSettings("openai", { model: event.currentTarget.value })}
                      />
                    </label>
                    <label className="settings-field">
                      <span>API Key</span>
                      <input
                        type="password"
                        value={aiSettings.openai.apiKey}
                        onChange={(event) => updateProviderSettings("openai", { apiKey: event.currentTarget.value })}
                      />
                    </label>
                  </div>
                )}
                {aiSettings.llmProvider === "mimo" && (
                  <div className="settings-grid">
                    <label className="settings-field span-2">
                      <span>MiMo Base URL</span>
                      <input
                        value={aiSettings.mimo.baseUrl}
                        onChange={(event) => updateProviderSettings("mimo", { baseUrl: event.currentTarget.value })}
                      />
                    </label>
                    <label className="settings-field">
                      <span>聊天模型</span>
                      <input
                        value={aiSettings.mimo.chatModel}
                        onChange={(event) => updateProviderSettings("mimo", { chatModel: event.currentTarget.value })}
                      />
                    </label>
                    <label className="settings-field">
                      <span>API Key</span>
                      <input
                        type="password"
                        value={aiSettings.mimo.apiKey}
                        onChange={(event) => updateProviderSettings("mimo", { apiKey: event.currentTarget.value })}
                      />
                    </label>
                  </div>
                )}
              </div>
            )}

            {activeSettingsTab === "speech" && (
              <div className="settings-tab-panel">
                <div className="settings-grid">
                  <label className="settings-field">
                    <span>STT 服务</span>
                    <select
                      value={aiSettings.sttProvider}
                      onChange={(event) => activateAiSettings({ sttProvider: event.currentTarget.value as SpeechProvider })}
                    >
                      <option value="env">环境变量 MiMo</option>
                      <option value="mimo">MiMo</option>
                      <option value="none">关闭</option>
                    </select>
                  </label>
                  <label className="settings-field">
                    <span>TTS 服务</span>
                    <select
                      value={aiSettings.ttsProvider}
                      onChange={(event) => {
                        const ttsProvider = event.currentTarget.value as SpeechProvider;
                        activateAiSettings({
                          ttsProvider,
                          cloneProvider: ttsProvider === "minimax" && aiSettings.cloneProvider === "env" ? "minimax" : aiSettings.cloneProvider
                        });
                      }}
                    >
                      <option value="env">环境变量 MiMo</option>
                      <option value="mimo">MiMo</option>
                      <option value="minimax">MiniMax</option>
                      <option value="none">关闭</option>
                    </select>
                  </label>
                </div>
                {speechNeedsMimoSettings && (
                  <div className="provider-settings-panel">
                    <div className="provider-settings-heading">
                      <strong>MiMo 语音设置</strong>
                      <span>当前 STT 或 TTS 选择 MiMo 时生效。</span>
                    </div>
                    <div className="settings-grid">
                      <label className="settings-field span-2">
                        <span>MiMo Base URL</span>
                        <input
                          value={aiSettings.mimo.baseUrl}
                          onChange={(event) => updateProviderSettings("mimo", { baseUrl: event.currentTarget.value })}
                        />
                      </label>
                      <label className="settings-field">
                        <span>MiMo API Key</span>
                        <input
                          type="password"
                          value={aiSettings.mimo.apiKey}
                          onChange={(event) => updateProviderSettings("mimo", { apiKey: event.currentTarget.value })}
                        />
                      </label>
                      <label className="settings-field">
                        <span>鉴权 Header</span>
                        <select
                          value={aiSettings.mimo.authHeader}
                          onChange={(event) =>
                            updateProviderSettings("mimo", { authHeader: event.currentTarget.value as AiSettings["mimo"]["authHeader"] })
                          }
                        >
                          <option value="api-key">api-key</option>
                          <option value="authorization">Authorization Bearer</option>
                        </select>
                      </label>
                      {aiSettings.sttProvider === "mimo" && (
                        <label className="settings-field">
                          <span>MiMo ASR 模型</span>
                          <input
                            value={aiSettings.mimo.asrModel}
                            onChange={(event) => updateProviderSettings("mimo", { asrModel: event.currentTarget.value })}
                          />
                        </label>
                      )}
                      {aiSettings.ttsProvider === "mimo" && (
                        <>
                          <label className="settings-field">
                            <span>MiMo TTS 模型</span>
                            <input
                              value={aiSettings.mimo.ttsModel}
                              onChange={(event) => updateProviderSettings("mimo", { ttsModel: event.currentTarget.value })}
                            />
                          </label>
                          <label className="settings-field">
                            <span>MiMo 音色</span>
                            <input
                              value={aiSettings.mimo.voice}
                              onChange={(event) => updateProviderSettings("mimo", { voice: event.currentTarget.value })}
                            />
                          </label>
                        </>
                      )}
                    </div>
                  </div>
                )}
                {speechNeedsMinimaxSettings && (
                  <div className="provider-settings-panel">
                    <div className="provider-settings-heading">
                      <strong>MiniMax 语音设置</strong>
                      <span>仅在 TTS 选择 MiniMax 时生效。</span>
                    </div>
                    <div className="settings-grid">
                      <label className="settings-field span-2">
                        <span>MiniMax Base URL</span>
                        <input
                          value={aiSettings.minimax.baseUrl}
                          onChange={(event) => updateProviderSettings("minimax", { baseUrl: event.currentTarget.value })}
                        />
                      </label>
                      <label className="settings-field">
                        <span>MiniMax API Key</span>
                        <input
                          type="password"
                          value={aiSettings.minimax.apiKey}
                          onChange={(event) => updateProviderSettings("minimax", { apiKey: event.currentTarget.value })}
                        />
                      </label>
                      <label className="settings-field">
                        <span>MiniMax TTS 模型</span>
                        <input
                          value={aiSettings.minimax.ttsModel}
                          onChange={(event) => updateProviderSettings("minimax", { ttsModel: event.currentTarget.value })}
                        />
                      </label>
                      <label className="settings-field">
                        <span>MiniMax 音色 ID</span>
                        <select
                          value={aiSettings.minimax.voiceId}
                          onChange={(event) => {
                            activateAiSettings({ ttsProvider: "minimax" });
                            updateProviderSettings("minimax", { voiceId: event.currentTarget.value });
                          }}
                        >
                          {minimaxSystemVoiceOptions.map((voice) => (
                            <option key={voice.voice_id} value={voice.voice_id}>
                              {voiceLabel(voice)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="settings-field voice-refresh-field">
                        <span>MiniMax 音色列表</span>
                        <button
                          type="button"
                          className="modal-secondary-button refresh-voice-button"
                          onClick={() => void refreshMinimaxVoices()}
                          disabled={minimaxVoiceLoading}
                        >
                          <RefreshCw size={15} />
                          <span>{minimaxVoiceLoading ? "刷新中" : "刷新音色"}</span>
                        </button>
                      </div>
                      <label className="settings-field">
                        <span>MiniMax 情绪</span>
                        <input
                          value={aiSettings.minimax.emotion}
                          onChange={(event) => updateProviderSettings("minimax", { emotion: event.currentTarget.value })}
                        />
                      </label>
                    </div>
                    {minimaxVoiceError && <div className="settings-error-line">{minimaxVoiceError}</div>}
                  </div>
                )}
              </div>
            )}

            {activeSettingsTab === "clone" && (
              <div className="settings-tab-panel">
                <label className="settings-field">
                  <span>克隆服务</span>
                  <select
                    value={aiSettings.cloneProvider}
                    onChange={(event) => {
                      const cloneProvider = event.currentTarget.value as SpeechProvider;
                      activateAiSettings({
                        cloneProvider,
                        ttsProvider:
                          cloneProvider === "minimax" ? "minimax" : cloneProvider === "mimo" ? "mimo" : aiSettings.ttsProvider
                      });
                    }}
                  >
                    <option value="env">跟随 TTS</option>
                    <option value="mimo">MiMo</option>
                    <option value="minimax">MiniMax</option>
                    <option value="none">关闭</option>
                  </select>
                </label>
                <div className={`voice-clone-panel ${voiceCloneSample ? "ready" : ""}`}>
                  <div className="voice-clone-copy">
                    <span className="voice-clone-kicker">{voiceCloneSample ? "当前样本" : "样本要求"}</span>
                    <strong>{voiceCloneSample ? voiceCloneSample.name : "上传一段 mp3 或 wav 音频"}</strong>
                    <p>
                      {voiceCloneSample
                        ? `${(voiceCloneSample.size / 1024 / 1024).toFixed(2)} MB，朗读时会按克隆服务发送给本地 API。`
                        : "样本只保存在当前会话内；API Key 和模型设置会写入本机浏览器缓存。"}
                    </p>
                  </div>
                  <div className="voice-clone-actions">
                    <input
                      ref={cloneFileInputRef}
                      type="file"
                      accept="audio/wav,audio/x-wav,audio/mpeg,audio/mp3,.wav,.mp3"
                      onChange={(event) => {
                        void selectVoiceCloneSample(event.currentTarget.files?.[0]);
                        event.currentTarget.value = "";
                      }}
                    />
                    <button type="button" className="modal-primary-button" onClick={() => cloneFileInputRef.current?.click()}>
                      <Upload size={16} />
                      <span>{voiceCloneSample ? "更换样本" : "选择音频"}</span>
                    </button>
                    {voiceCloneSample && (
                      <button type="button" className="modal-secondary-button" onClick={() => setVoiceCloneSample(null)}>
                        移除
                      </button>
                    )}
                  </div>
                </div>
                {cloneNeedsMimoSettings && (
                  <div className="provider-settings-panel">
                    <div className="provider-settings-heading">
                      <strong>MiMo 克隆设置</strong>
                      <span>仅在克隆服务选择 MiMo 时生效。</span>
                    </div>
                    <div className="settings-grid">
                      <label className="settings-field span-2">
                        <span>MiMo Base URL</span>
                        <input
                          value={aiSettings.mimo.baseUrl}
                          onChange={(event) => updateProviderSettings("mimo", { baseUrl: event.currentTarget.value })}
                        />
                      </label>
                      <label className="settings-field">
                        <span>MiMo API Key</span>
                        <input
                          type="password"
                          value={aiSettings.mimo.apiKey}
                          onChange={(event) => updateProviderSettings("mimo", { apiKey: event.currentTarget.value })}
                        />
                      </label>
                      <label className="settings-field">
                        <span>MiMo 克隆模型</span>
                        <input
                          value={aiSettings.mimo.ttsVoiceCloneModel}
                          onChange={(event) => updateProviderSettings("mimo", { ttsVoiceCloneModel: event.currentTarget.value })}
                        />
                      </label>
                    </div>
                  </div>
                )}
                {cloneNeedsMinimaxSettings && (
                  <div className="provider-settings-panel">
                    <div className="provider-settings-heading">
                      <strong>MiniMax 克隆设置</strong>
                      <span>仅在克隆服务选择 MiniMax 时生效。</span>
                    </div>
                    <div className="settings-grid">
                      <label className="settings-field span-2">
                        <span>MiniMax Base URL</span>
                        <input
                          value={aiSettings.minimax.baseUrl}
                          onChange={(event) => updateProviderSettings("minimax", { baseUrl: event.currentTarget.value })}
                        />
                      </label>
                      <label className="settings-field">
                        <span>MiniMax API Key</span>
                        <input
                          type="password"
                          value={aiSettings.minimax.apiKey}
                          onChange={(event) => updateProviderSettings("minimax", { apiKey: event.currentTarget.value })}
                        />
                      </label>
                      <label className="settings-field">
                        <span>MiniMax 克隆音色 ID</span>
                        <select
                          value={aiSettings.minimax.cloneVoiceId}
                          onChange={(event) => {
                            activateAiSettings({ ttsProvider: "minimax", cloneProvider: "minimax" });
                            updateProviderSettings("minimax", { cloneVoiceId: event.currentTarget.value });
                          }}
                        >
                          {minimaxCloneVoiceOptions.length ? (
                            minimaxCloneVoiceOptions.map((voice) => (
                              <option key={voice.voice_id} value={voice.voice_id}>
                                {voiceLabel(voice)}
                              </option>
                            ))
                          ) : (
                            <option value={aiSettings.minimax.cloneVoiceId}>
                              暂无已激活复刻音色
                            </option>
                          )}
                        </select>
                      </label>
                      <label className="settings-field">
                        <span>MiniMax 克隆模型</span>
                        <input
                          value={aiSettings.minimax.cloneModel}
                          onChange={(event) => updateProviderSettings("minimax", { cloneModel: event.currentTarget.value })}
                        />
                      </label>
                      <div className="settings-field voice-refresh-field">
                        <span>复刻音色列表</span>
                        <button
                          type="button"
                          className="modal-secondary-button refresh-voice-button"
                          onClick={() => void refreshMinimaxVoices()}
                          disabled={minimaxVoiceLoading}
                        >
                          <RefreshCw size={15} />
                          <span>{minimaxVoiceLoading ? "刷新中" : "刷新复刻音色"}</span>
                        </button>
                      </div>
                      <label className="settings-field">
                        <span>MiniMax Group ID</span>
                        <input
                          value={aiSettings.minimax.groupId}
                          onChange={(event) => updateProviderSettings("minimax", { groupId: event.currentTarget.value })}
                        />
                      </label>
                    </div>
                    {minimaxVoiceError && <div className="settings-error-line">{minimaxVoiceError}</div>}
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
