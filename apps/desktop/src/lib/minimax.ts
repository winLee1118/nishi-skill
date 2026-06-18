export interface MinimaxConfig {
  apiKey?: string;
  groupId?: string;
  baseUrl?: string;
  ttsModel?: string;
  cloneModel?: string;
  voiceId?: string;
  cloneVoiceId?: string;
  emotion?: string;
}

export interface MinimaxTtsOptions {
  format?: string;
  voiceCloneDataUrl?: string;
  voiceCloneMimeType?: string;
  stylePrompt?: string;
}

function requireConfig(config: MinimaxConfig) {
  if (!config.apiKey) throw new Error("MINIMAX_API_KEY 未配置");
}

function endpoint(config: MinimaxConfig, path: string) {
  const baseUrl = (config.baseUrl || "https://api.minimaxi.com").replace(/\/$/, "");
  return `${baseUrl}${path}`;
}

function jsonHeaders(config: MinimaxConfig) {
  requireConfig(config);
  return {
    Authorization: `Bearer ${config.apiKey}`,
    "Content-Type": "application/json"
  };
}

function splitDataUrl(value: string, fallbackMimeType: string) {
  const trimmed = value.trim();
  if (!trimmed.startsWith("data:")) {
    return { mimeType: fallbackMimeType, base64: trimmed };
  }
  const commaIndex = trimmed.indexOf(",");
  const metadata = trimmed.slice(5, commaIndex);
  return {
    mimeType: metadata.split(";")[0] || fallbackMimeType,
    base64: trimmed.slice(commaIndex + 1)
  };
}

function audioToBase64(value: string) {
  const trimmed = value.trim();
  if (/^[0-9a-fA-F]+$/.test(trimmed) && trimmed.length % 2 === 0) {
    return Buffer.from(trimmed, "hex").toString("base64");
  }
  return trimmed.replace(/^data:[^,]+,/, "");
}

function firstString(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function minimaxErrorMessage(data: unknown) {
  if (!data || typeof data !== "object") return "";
  const response = data as { base_resp?: { status_code?: number; status_msg?: string } };
  const statusCode = response.base_resp?.status_code;
  if (typeof statusCode === "number" && statusCode !== 0) {
    return response.base_resp?.status_msg || `status_code=${statusCode}`;
  }
  return "";
}

async function uploadCloneAudio(config: MinimaxConfig, dataUrl: string, mimeType: string) {
  const audio = splitDataUrl(dataUrl, mimeType);
  const bytes = Buffer.from(audio.base64, "base64");
  const form = new FormData();
  form.append("purpose", "voice_clone");
  form.append("file", new Blob([bytes], { type: audio.mimeType }), `voice-sample.${audio.mimeType.includes("mpeg") ? "mp3" : "wav"}`);

  const response = await fetch(endpoint(config, "/v1/files/upload"), {
    method: "POST",
    headers: { Authorization: `Bearer ${config.apiKey}` },
    body: form
  });

  if (!response.ok) {
    throw new Error(`Minimax upload HTTP ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  const fileId = firstString(data?.file?.file_id, data?.file_id, data?.data?.file_id);
  if (!fileId) throw new Error("Minimax upload response missing file_id");
  return fileId;
}

async function cloneVoice(config: MinimaxConfig, fileId: string) {
  const voiceId = config.cloneVoiceId || `nishi_clone_${Date.now()}`;
  const response = await fetch(endpoint(config, "/v1/voice_clone"), {
    method: "POST",
    headers: jsonHeaders(config),
    body: JSON.stringify({
      file_id: fileId,
      voice_id: voiceId,
      need_noise_reduction: true,
      text: "你好，我是倪师数字人。今天我们先把问题讲清楚，再一步一步往下看。",
      model: config.cloneModel || config.ttsModel || "speech-2.8-hd"
    })
  });

  if (!response.ok) {
    throw new Error(`Minimax voice clone HTTP ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  const baseRespError = minimaxErrorMessage(data);
  if (baseRespError) throw new Error(`Minimax voice clone error: ${baseRespError}`);
  return firstString(data?.voice_id, data?.data?.voice_id, voiceId);
}

export async function minimaxTts(text: string, config: MinimaxConfig, options: MinimaxTtsOptions = {}) {
  requireConfig(config);
  const format = options.format || "mp3";
  let voiceId = config.voiceId || "female-shaonv";

  if (options.voiceCloneDataUrl) {
    const fileId = await uploadCloneAudio(config, options.voiceCloneDataUrl, options.voiceCloneMimeType || "audio/wav");
    voiceId = await cloneVoice(config, fileId);
  }

  const voiceSetting: Record<string, string | number> = {
    voice_id: voiceId,
    speed: 1,
    vol: 1,
    pitch: 0
  };
  if (config.emotion && config.emotion !== "neutral") {
    voiceSetting.emotion = config.emotion;
  }

  const response = await fetch(endpoint(config, "/v1/t2a_v2"), {
    method: "POST",
    headers: jsonHeaders(config),
    body: JSON.stringify({
      model: config.ttsModel || "speech-2.8-hd",
      text,
      stream: false,
      voice_setting: voiceSetting,
      audio_setting: {
        sample_rate: 32000,
        bitrate: 128000,
        format,
        channel: 1
      },
      subtitle_enable: false,
      language_boost: "Chinese"
    })
  });

  if (!response.ok) {
    throw new Error(`Minimax TTS HTTP ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  const baseRespError = minimaxErrorMessage(data);
  if (baseRespError) throw new Error(`Minimax TTS error: ${baseRespError}`);
  const audio = firstString(data?.data?.audio, data?.audio, data?.audio_data);
  if (!audio) throw new Error("Minimax TTS response missing audio data");
  return { audioData: audioToBase64(audio), format, voiceId };
}

export interface MinimaxVoiceItem {
  voice_id: string;
  voice_name?: string;
  created_time?: string;
  description?: string[];
}

export interface MinimaxVoices {
  system_voice: MinimaxVoiceItem[];
  voice_cloning: MinimaxVoiceItem[];
  voice_generation: MinimaxVoiceItem[];
}

function voiceList(value: unknown): MinimaxVoiceItem[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map((item) => ({
      voice_id: firstString(item.voice_id),
      voice_name: firstString(item.voice_name),
      created_time: firstString(item.created_time),
      description: Array.isArray(item.description) ? item.description.filter((entry): entry is string => typeof entry === "string") : []
    }))
    .filter((item) => item.voice_id);
}

export async function minimaxVoices(config: MinimaxConfig, voiceType = "all"): Promise<MinimaxVoices> {
  requireConfig(config);
  const response = await fetch(endpoint(config, "/v1/get_voice"), {
    method: "POST",
    headers: jsonHeaders(config),
    body: JSON.stringify({ voice_type: voiceType })
  });

  if (!response.ok) {
    throw new Error(`Minimax get voice HTTP ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  return {
    system_voice: voiceList(data?.system_voice),
    voice_cloning: voiceList(data?.voice_cloning),
    voice_generation: voiceList(data?.voice_generation)
  };
}
