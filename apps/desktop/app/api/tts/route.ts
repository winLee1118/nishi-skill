import { NextResponse } from "next/server";
import { activeRuntimeAiSettings } from "@/src/lib/aiSettings";
import { sanitizeChatText } from "@/src/lib/chatText";
import { minimaxTts } from "@/src/lib/minimax";
import { hasMimoConfig, hasMimoKey, mimoTts } from "@/src/lib/mimo";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const body = await request.json();
  const text = sanitizeChatText(String(body.text || "").trim());
  const aiSettings = activeRuntimeAiSettings(body.provider_config || body.ai_settings);

  if (!text) {
    return NextResponse.json({ error: "text is empty", audio_data: "" }, { status: 400 });
  }

  if (aiSettings?.ttsProvider === "none") {
    return NextResponse.json({ error: "语音合成未启用", audio_data: "" }, { status: 200 });
  }

  if (aiSettings?.ttsProvider === "mimo" && !hasMimoConfig(aiSettings.mimo)) {
    return NextResponse.json({ error: "MiMo TTS API Key 未配置", audio_data: "" }, { status: 200 });
  }

  if (!aiSettings && !hasMimoKey()) {
    return NextResponse.json({ error: "MIMO_API_KEY 未配置", audio_data: "" }, { status: 200 });
  }

  try {
    const format = String(body.format || (aiSettings?.ttsProvider === "minimax" ? "mp3" : "wav"));
    const voiceClone = typeof body.voice_clone === "object" && body.voice_clone ? body.voice_clone : {};
    const cloneVoiceDataUrl = String(
      voiceClone.data_url || voiceClone.audio_data || body.clone_voice_data_url || body.clone_voice_audio || ""
    );
    const cloneVoiceMimeType = String(voiceClone.mime_type || body.clone_voice_mime_type || "audio/wav");

    if (aiSettings?.ttsProvider === "minimax") {
      const useExistingCloneVoice =
        aiSettings.cloneProvider === "minimax" && Boolean(aiSettings.minimax?.cloneVoiceId);
      const shouldCloneFromSample =
        !useExistingCloneVoice &&
        Boolean(cloneVoiceDataUrl) &&
        (aiSettings.cloneProvider === "minimax" || aiSettings.cloneProvider === "env");
      const minimaxConfig = {
        ...(aiSettings.minimax || {}),
        voiceId:
          useExistingCloneVoice
            ? aiSettings.minimax?.cloneVoiceId || aiSettings.minimax?.voiceId
            : aiSettings.minimax?.voiceId
      };
      const result = await minimaxTts(text, minimaxConfig, {
        format,
        stylePrompt: String(body.style_prompt || ""),
        voiceCloneDataUrl: shouldCloneFromSample ? cloneVoiceDataUrl : "",
        voiceCloneMimeType: cloneVoiceMimeType
      });
      return NextResponse.json({
        audio_data: result.audioData,
        format,
        voice_mode: useExistingCloneVoice || shouldCloneFromSample ? "voiceclone" : "preset",
        provider: "minimax",
        voice_id: result.voiceId
      });
    }

    const audio = await mimoTts(text, {
      stylePrompt: String(body.style_prompt || ""),
      voice: String(body.voice || aiSettings?.mimo?.voice || "冰糖"),
      cloneVoiceDataUrl:
        aiSettings && aiSettings.cloneProvider !== "mimo" && aiSettings.cloneProvider !== "env" ? "" : cloneVoiceDataUrl,
      cloneVoiceMimeType,
      format,
      config: aiSettings?.ttsProvider === "mimo" ? aiSettings.mimo : undefined
    });
    return NextResponse.json({
      audio_data: audio,
      format,
      voice_mode: cloneVoiceDataUrl ? "voiceclone" : "preset",
      provider: aiSettings?.ttsProvider === "mimo" ? "mimo" : "env"
    });
  } catch (error) {
    return NextResponse.json({ error: String(error), audio_data: "" }, { status: 200 });
  }
}
