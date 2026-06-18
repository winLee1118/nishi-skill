const envBaseUrl = process.env.MIMO_BASE_URL || "https://api.xiaomimimo.com/v1";
const envChatModel = process.env.MIMO_CHAT_MODEL || "mimo-v2.5-pro";
const envAsrModel = process.env.MIMO_ASR_MODEL || "mimo-v2.5-asr";
const envTtsModel = process.env.MIMO_TTS_MODEL || "mimo-v2.5-tts";
const envTtsVoiceCloneModel = process.env.MIMO_TTS_VOICECLONE_MODEL || "mimo-v2.5-tts-voiceclone";

export interface MimoConfig {
  apiKey?: string;
  baseUrl?: string;
  chatModel?: string;
  asrModel?: string;
  ttsModel?: string;
  ttsVoiceCloneModel?: string;
  authHeader?: "api-key" | "authorization";
}

export interface MimoTtsOptions {
  stylePrompt?: string;
  voice?: string;
  cloneVoiceDataUrl?: string;
  cloneVoiceMimeType?: string;
  format?: string;
  config?: MimoConfig;
}

export interface ChatMessagePayload {
  role: string;
  content: string;
}

function apiKey(config?: MimoConfig) {
  return config?.apiKey || process.env.MIMO_API_KEY || "";
}

function baseUrl(config?: MimoConfig) {
  return (config?.baseUrl || envBaseUrl).replace(/\/$/, "");
}

function headers(config?: MimoConfig): Record<string, string> {
  const key = apiKey(config);
  if (!key) throw new Error("MIMO_API_KEY 未配置");
  const authHeader = config?.authHeader || process.env.MIMO_AUTH_HEADER || (key.startsWith("tp-") ? "authorization" : "api-key");

  if (authHeader.toLowerCase() === "authorization") {
    return {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json"
    };
  }

  return {
    "api-key": key,
    "Content-Type": "application/json"
  };
}

export function hasMimoKey() {
  return Boolean(apiKey());
}

export function hasMimoConfig(config?: MimoConfig) {
  return Boolean(apiKey(config));
}

// Prompt composition lives in the Python skill layer
// (nihaixia_mcp.orchestrator.compose_chat_messages). This module only carries
// ready-made messages to the MiMo API.

export async function mimoChat(messages: ChatMessagePayload[], config?: MimoConfig) {
  const response = await fetch(`${baseUrl(config)}/chat/completions`, {
    method: "POST",
    headers: headers(config),
    body: JSON.stringify({
      model: config?.chatModel || envChatModel,
      messages,
      temperature: 0.55
    })
  });

  if (!response.ok) {
    throw new Error(`MiMo chat HTTP ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  return String(data?.choices?.[0]?.message?.content || "");
}

export async function* mimoChatStream(messages: ChatMessagePayload[], config?: MimoConfig): AsyncGenerator<string> {
  const response = await fetch(`${baseUrl(config)}/chat/completions`, {
    method: "POST",
    headers: headers(config),
    body: JSON.stringify({
      model: config?.chatModel || envChatModel,
      messages,
      temperature: 0.55,
      stream: true
    })
  });

  if (!response.ok) {
    throw new Error(`MiMo chat stream HTTP ${response.status}: ${await response.text()}`);
  }

  if (!response.body) {
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const payload = trimmed.slice(5).trim();
      if (!payload || payload === "[DONE]") continue;

      try {
        const data = JSON.parse(payload);
        const delta = data?.choices?.[0]?.delta?.content ?? data?.choices?.[0]?.message?.content ?? "";
        if (typeof delta === "string" && delta) {
          yield delta;
        }
      } catch {
        if (payload) {
          yield payload;
        }
      }
    }
  }
}

function normalizeAudioDataUrl(audioData: string, mimeType = "audio/webm") {
  const trimmed = audioData.trim();
  if (trimmed.startsWith("data:")) {
    const commaIndex = trimmed.indexOf(",");
    if (commaIndex > 0) {
      const metadata = trimmed.slice(5, commaIndex);
      const payload = trimmed.slice(commaIndex + 1);
      const mime = metadata.split(";")[0] || mimeType.split(";")[0] || "audio/webm";
      return `data:${mime};base64,${payload}`;
    }
  }

  const cleanMimeType = mimeType.split(";")[0] || "audio/webm";
  return `data:${cleanMimeType};base64,${trimmed}`;
}

function normalizeVoiceCloneDataUrl(audioData: string, mimeType = "audio/wav") {
  const dataUrl = normalizeAudioDataUrl(audioData, mimeType);
  const mime = dataUrl.slice(5, dataUrl.indexOf(";")).toLowerCase();
  if (!["audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3"].includes(mime)) {
    throw new Error("克隆音色样本仅支持 mp3 或 wav");
  }
  return dataUrl;
}

export async function mimoStt(audioData: string, mimeType = "audio/webm", language = "auto", config?: MimoConfig) {
  const dataUrl = normalizeAudioDataUrl(audioData, mimeType);
  const response = await fetch(`${baseUrl(config)}/chat/completions`, {
    method: "POST",
    headers: headers(config),
    body: JSON.stringify({
      model: config?.asrModel || envAsrModel,
      messages: [
        {
          role: "user",
          content: [
            {
              type: "input_audio",
              input_audio: {
                data: dataUrl
              }
            }
          ]
        }
      ],
      asr_options: { language }
    })
  });

  if (!response.ok) {
    throw new Error(`MiMo STT HTTP ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  return String(data?.choices?.[0]?.message?.content || "");
}

export async function mimoTts(text: string, options: MimoTtsOptions = {}) {
  const {
    stylePrompt = "",
    voice = "冰糖",
    cloneVoiceDataUrl = "",
    cloneVoiceMimeType = "audio/wav",
    format = "wav",
    config
  } = options;
  const clonedVoice = cloneVoiceDataUrl ? normalizeVoiceCloneDataUrl(cloneVoiceDataUrl, cloneVoiceMimeType) : "";
  const model = clonedVoice ? config?.ttsVoiceCloneModel || envTtsVoiceCloneModel : config?.ttsModel || envTtsModel;

  const response = await fetch(`${baseUrl(config)}/chat/completions`, {
    method: "POST",
    headers: headers(config),
    body: JSON.stringify({
      model,
      messages: [
        {
          role: "user",
          content:
            stylePrompt ||
            "温和沉稳、像一位学识渊博的老师在课堂上讲解，语速适中，声音醇厚有磁性。"
        },
        { role: "assistant", content: text }
      ],
      audio: { format, voice: clonedVoice || voice }
    })
  });

  if (!response.ok) {
    throw new Error(`MiMo TTS HTTP ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  return String(data?.choices?.[0]?.message?.audio?.data || "");
}
