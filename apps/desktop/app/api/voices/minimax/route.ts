import { NextResponse } from "next/server";
import { runtimeAiSettings } from "@/src/lib/aiSettings";
import { minimaxVoices } from "@/src/lib/minimax";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const body = await request.json();
  const settings = runtimeAiSettings(body.provider_config || body.ai_settings || {});

  try {
    const voices = await minimaxVoices(settings.minimax || {}, String(body.voice_type || "all"));
    return NextResponse.json({
      ...voices,
      counts: {
        system_voice: voices.system_voice.length,
        voice_cloning: voices.voice_cloning.length,
        voice_generation: voices.voice_generation.length
      }
    });
  } catch (error) {
    return NextResponse.json({ error: String(error), system_voice: [], voice_cloning: [], voice_generation: [] }, { status: 200 });
  }
}
