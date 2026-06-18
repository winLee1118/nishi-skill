import type { ChatMessagePayload } from "./mimo";

export interface OpenAiCompatibleConfig {
  apiKey?: string;
  baseUrl?: string;
  model?: string;
}

function headers(config: OpenAiCompatibleConfig) {
  if (!config.apiKey) throw new Error("OpenAI-compatible API key 未配置");
  return {
    Authorization: `Bearer ${config.apiKey}`,
    "Content-Type": "application/json"
  };
}

export async function* openAiCompatibleChatStream(
  messages: ChatMessagePayload[],
  config: OpenAiCompatibleConfig
): AsyncGenerator<string> {
  const baseUrl = (config.baseUrl || "https://api.openai.com/v1").replace(/\/$/, "");
  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: headers(config),
    body: JSON.stringify({
      model: config.model || "gpt-4o-mini",
      messages,
      temperature: 0.55,
      stream: true
    })
  });

  if (!response.ok) {
    throw new Error(`OpenAI-compatible chat HTTP ${response.status}: ${await response.text()}`);
  }

  if (!response.body) return;

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
      const data = JSON.parse(payload);
      const delta = data?.choices?.[0]?.delta?.content ?? data?.choices?.[0]?.message?.content ?? "";
      if (typeof delta === "string" && delta) yield delta;
    }
  }
}
