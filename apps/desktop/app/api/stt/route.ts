import { NextResponse } from "next/server";
import { activeRuntimeAiSettings } from "@/src/lib/aiSettings";
import { hasMimoConfig, hasMimoKey, mimoStt } from "@/src/lib/mimo";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const body = await request.json();
  const aiSettings = activeRuntimeAiSettings(body.provider_config || body.ai_settings);

  if (aiSettings?.sttProvider === "none") {
    return NextResponse.json({ error: "语音识别未启用", text: "" }, { status: 200 });
  }

  if (aiSettings?.sttProvider === "mimo" && !hasMimoConfig(aiSettings.mimo)) {
    return NextResponse.json({ error: "MiMo STT API Key 未配置", text: "" }, { status: 200 });
  }

  if (!aiSettings && !hasMimoKey()) {
    return NextResponse.json({ error: "MIMO_API_KEY 未配置", text: "" }, { status: 200 });
  }

  try {
    const text = await mimoStt(
      String(body.audio_data || ""),
      String(body.mime_type || "audio/webm"),
      String(body.language || "auto"),
      aiSettings?.sttProvider === "mimo" ? aiSettings.mimo : undefined
    );
    return NextResponse.json({ text });
  } catch (error) {
    return NextResponse.json({ error: String(error), text: "" }, { status: 200 });
  }
}
