import type { MimoConfig } from "./mimo";

export type LlmProvider = "env" | "mimo" | "openai" | "local";
export type SpeechProvider = "env" | "mimo" | "minimax" | "none";

export interface RuntimeAiSettings {
  active?: boolean;
  llmProvider?: LlmProvider;
  sttProvider?: SpeechProvider;
  ttsProvider?: SpeechProvider;
  cloneProvider?: SpeechProvider;
  openai?: {
    apiKey?: string;
    baseUrl?: string;
    model?: string;
  };
  mimo?: MimoConfig & {
    voice?: string;
  };
  minimax?: {
    apiKey?: string;
    groupId?: string;
    baseUrl?: string;
    ttsModel?: string;
    cloneModel?: string;
    voiceId?: string;
    cloneVoiceId?: string;
    emotion?: string;
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function cleanString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function pick<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

export function runtimeAiSettings(value: unknown): RuntimeAiSettings {
  const raw = asRecord(value);
  const openai = asRecord(raw.openai);
  const mimo = asRecord(raw.mimo);
  const minimax = asRecord(raw.minimax);
  const mimoApiKey = cleanString(mimo.apiKey);
  const mimoAuthHeader = mimoApiKey.startsWith("tp-")
    ? "authorization"
    : pick(mimo.authHeader, ["api-key", "authorization"] as const, "api-key");
  return {
    active: Boolean(raw.active),
    llmProvider: pick(raw.llmProvider, ["env", "mimo", "openai", "local"] as const, "env"),
    sttProvider: pick(raw.sttProvider, ["env", "mimo", "minimax", "none"] as const, "env"),
    ttsProvider: pick(raw.ttsProvider, ["env", "mimo", "minimax", "none"] as const, "env"),
    cloneProvider: pick(raw.cloneProvider, ["env", "mimo", "minimax", "none"] as const, "env"),
    openai: {
      apiKey: cleanString(openai.apiKey),
      baseUrl: cleanString(openai.baseUrl) || "https://api.openai.com/v1",
      model: cleanString(openai.model) || "gpt-4o-mini"
    },
    mimo: {
      apiKey: mimoApiKey,
      baseUrl: cleanString(mimo.baseUrl) || "https://api.xiaomimimo.com/v1",
      chatModel: cleanString(mimo.chatModel) || "mimo-v2.5-pro",
      asrModel: cleanString(mimo.asrModel) || "mimo-v2.5-asr",
      ttsModel: cleanString(mimo.ttsModel) || "mimo-v2.5-tts",
      ttsVoiceCloneModel: cleanString(mimo.ttsVoiceCloneModel) || "mimo-v2.5-tts-voiceclone",
      authHeader: mimoAuthHeader,
      voice: cleanString(mimo.voice) || "冰糖"
    },
    minimax: {
      apiKey: cleanString(minimax.apiKey),
      groupId: cleanString(minimax.groupId),
      baseUrl: cleanString(minimax.baseUrl) || "https://api.minimaxi.com",
      ttsModel: cleanString(minimax.ttsModel) || "speech-2.8-hd",
      cloneModel: cleanString(minimax.cloneModel) || "speech-2.8-hd",
      voiceId: cleanString(minimax.voiceId) || "female-shaonv",
      cloneVoiceId: cleanString(minimax.cloneVoiceId),
      emotion: cleanString(minimax.emotion) || "neutral"
    }
  };
}

export function activeRuntimeAiSettings(value: unknown): RuntimeAiSettings | null {
  const settings = runtimeAiSettings(value);
  return settings.active ? settings : null;
}
