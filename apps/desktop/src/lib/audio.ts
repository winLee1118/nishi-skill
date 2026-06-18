export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      resolve(String(reader.result || ""));
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function encodeWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  const writeString = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) {
      view.setUint8(offset + i, text.charCodeAt(i));
    }
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }

  return buffer;
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

const STT_SAMPLE_RATE = 16000;

/**
 * MiMo STT 只接受 wav/mp3/mpeg，而 MediaRecorder 通常录出 webm/ogg，
 * 因此这里把录音解码后重采样为 16kHz 单声道 16-bit PCM WAV。
 */
export async function blobToWavBase64(blob: Blob): Promise<string> {
  const rawBuffer = await blob.arrayBuffer();
  const decodeContext = new AudioContext();
  let decoded: AudioBuffer;
  try {
    decoded = await decodeContext.decodeAudioData(rawBuffer);
  } finally {
    void decodeContext.close();
  }

  const length = Math.max(1, Math.ceil(decoded.duration * STT_SAMPLE_RATE));
  const offlineContext = new OfflineAudioContext(1, length, STT_SAMPLE_RATE);
  const source = offlineContext.createBufferSource();
  source.buffer = decoded;
  source.connect(offlineContext.destination);
  source.start();
  const rendered = await offlineContext.startRendering();

  const wavBuffer = encodeWav(rendered.getChannelData(0), STT_SAMPLE_RATE);
  return arrayBufferToBase64(wavBuffer);
}

export function playBase64Audio(audioData: string, format = "wav", onFinished?: () => void) {
  if (!audioData) return null;
  const audio = new Audio(`data:audio/${format};base64,${audioData}`);
  if (onFinished) {
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      onFinished();
    };
    audio.onended = finish;
    audio.onerror = finish;
    void audio.play().catch(finish);
  } else {
    void audio.play();
  }
  return audio;
}
