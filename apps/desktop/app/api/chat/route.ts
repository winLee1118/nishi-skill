import { NextResponse } from "next/server";
import { activeRuntimeAiSettings } from "@/src/lib/aiSettings";
import { sanitizeChatText } from "@/src/lib/chatText";
import { hasMimoConfig, hasMimoKey, mimoChatStream } from "@/src/lib/mimo";
import { openAiCompatibleChatStream } from "@/src/lib/openaiCompatible";
import { runPythonModuleJson } from "@/src/lib/pythonBridge";
import type { Citation, RetrievalHit } from "@/src/types";

export const runtime = "nodejs";

// Standard skill contract returned by `python -m nihaixia_mcp.orchestrator`.
// See docs/specs/0006-chat-orchestration-spec.md.
interface OrchestratorResult {
  route: "bazi" | "answer" | "error";
  answer_draft: string;
  draft_is_final: boolean;
  messages: { role: string; content: string }[];
  citations: Citation[];
  retrieval_hits?: RetrievalHit[];
  meta: Record<string, unknown> & {
    error?: string;
    domain?: string;
    safety_notes?: string[];
    medical_intent?: string;
  };
}

interface HistoryMessage {
  role?: string;
  content?: string;
}

const HISTORY_LIMIT = 24;

const OFFLINE_FALLBACK =
  "我这边的本地检索链路这会儿没接通，先不勉强答。你可以稍后再问一次；要是问题急，先把症状、时间或场景描述完整，我们再按体系来看。";
const LLM_FAILURE_FALLBACK =
  "模型调用失败了，这次没有生成回答。请检查前端配置里的 MiMo API Key、鉴权头和模型名。";

function normalizedHistory(value: unknown): HistoryMessage[] {
  if (!Array.isArray(value)) return [];
  const history: HistoryMessage[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const entry = item as Record<string, unknown>;
    const role = typeof entry.role === "string" ? entry.role : "";
    const content = typeof entry.content === "string" ? entry.content : "";
    if (role && content) {
      history.push({ role, content });
    }
  }
  return history.slice(-HISTORY_LIMIT);
}

function sseEvent(event: string, data: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function streamTextChunks(controller: ReadableStreamDefaultController<Uint8Array>, encoder: TextEncoder, text: string) {
  const chars = Array.from(text);
  for (let index = 0; index < chars.length; index += 18) {
    const chunk = chars.slice(index, index + 18).join("");
    if (chunk) {
      controller.enqueue(encoder.encode(sseEvent("delta", { text: chunk })));
    }
  }
}

function streamResponse(run: (controller: ReadableStreamDefaultController<Uint8Array>, encoder: TextEncoder) => Promise<void>) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        await run(controller, encoder);
      } catch (error) {
        controller.enqueue(encoder.encode(sseEvent("error", { error: String(error) })));
      } finally {
        controller.close();
      }
    }
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no"
    }
  });
}

export async function POST(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  const question = String(body.question || "").trim();
  const history = normalizedHistory(body.history);
  const aiSettings = activeRuntimeAiSettings(body.provider_config || body.ai_settings);

  if (!question) {
    return NextResponse.json({ error: "question is empty" }, { status: 400 });
  }

  return streamResponse(async (controller, encoder) => {
    let result: OrchestratorResult;
    try {
      result = await runPythonModuleJson<OrchestratorResult>("nihaixia_mcp.orchestrator", {
        question,
        history,
        timezone: body.timezone || "Asia/Shanghai",
        domain: body.domain || "auto",
        top_k: body.top_k || 5,
        mode: body.mode || "auto",
        style_intensity: body.style_intensity || "medium"
      });
    } catch (error) {
      const meta = {
        error: String(error),
        domain: body.domain || "auto",
        citations: [],
        safety_notes: ["本地 Python 检索链路暂时不可用，已返回离线提示。"],
        retrieval_info: {},
        used_model: "local-draft"
      };
      controller.enqueue(encoder.encode(sseEvent("meta", meta)));
      streamTextChunks(controller, encoder, OFFLINE_FALLBACK);
      controller.enqueue(encoder.encode(sseEvent("done", { ...meta, answer: OFFLINE_FALLBACK })));
      return;
    }

    if (result.route === "error") {
      const meta = {
        error: String(result.meta?.error || "orchestrator error"),
        domain: body.domain || "auto",
        citations: [],
        safety_notes: [],
        retrieval_info: {},
        used_model: "local-draft"
      };
      controller.enqueue(encoder.encode(sseEvent("meta", meta)));
      streamTextChunks(controller, encoder, OFFLINE_FALLBACK);
      controller.enqueue(encoder.encode(sseEvent("done", { ...meta, answer: OFFLINE_FALLBACK })));
      return;
    }

    const baseMeta = {
      route: result.route,
      citations: result.citations,
      ...result.meta
    };
    controller.enqueue(encoder.encode(sseEvent("meta", baseMeta)));

    // Tool routes (calendar/bazi) come back as final conversational answers.
    if (result.draft_is_final) {
      const answer = sanitizeChatText(result.answer_draft);
      streamTextChunks(controller, encoder, answer);
      controller.enqueue(
        encoder.encode(sseEvent("done", { ...baseMeta, answer, used_model: "local-skill-tool", generation_error: "" }))
      );
      return;
    }

    // Answer route: feed the skill-composed messages to the LLM as-is.
    let answer = "";
    let usedModel = "local-draft";
    let generationError = "";

    const selectedRemoteProvider = aiSettings?.llmProvider === "openai" || aiSettings?.llmProvider === "mimo";

    if (result.messages.length) {
      try {
        if (aiSettings?.llmProvider === "openai" && aiSettings.openai?.apiKey) {
          for await (const chunk of openAiCompatibleChatStream(result.messages, aiSettings.openai)) {
            answer += chunk;
            controller.enqueue(encoder.encode(sseEvent("delta", { text: chunk })));
          }
          if (answer) usedModel = aiSettings.openai.model || "openai-compatible";
        } else if (aiSettings?.llmProvider === "openai") {
          generationError = "OpenAI-compatible API key 未配置";
        } else if (aiSettings?.llmProvider === "mimo" && hasMimoConfig(aiSettings.mimo)) {
          for await (const chunk of mimoChatStream(result.messages, aiSettings.mimo)) {
            answer += chunk;
            controller.enqueue(encoder.encode(sseEvent("delta", { text: chunk })));
          }
          if (answer) usedModel = aiSettings.mimo?.chatModel || "mimo-v2.5-pro";
        } else if (aiSettings?.llmProvider === "mimo") {
          generationError = "MiMo API Key 未配置";
        } else if (!aiSettings && hasMimoKey()) {
          for await (const chunk of mimoChatStream(result.messages)) {
            answer += chunk;
            controller.enqueue(encoder.encode(sseEvent("delta", { text: chunk })));
          }
          if (answer) usedModel = process.env.MIMO_CHAT_MODEL || "mimo-v2.5-pro";
        }
      } catch (error) {
        generationError = String(error);
      }
    }

    if (!answer) {
      if (selectedRemoteProvider && !generationError) {
        generationError = "模型没有返回内容";
      }
      answer = generationError ? LLM_FAILURE_FALLBACK : sanitizeChatText(result.answer_draft) || OFFLINE_FALLBACK;
      streamTextChunks(controller, encoder, answer);
    }

    controller.enqueue(
      encoder.encode(
        sseEvent("done", {
          ...baseMeta,
          answer: sanitizeChatText(answer),
          used_model: usedModel,
          generation_error: generationError
        })
      )
    );
  });
}
