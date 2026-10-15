export async function waveform(blob: Blob) {
  const ctx = new AudioContext();
  try {
    const data = await ctx.decodeAudioData(await blob.arrayBuffer());
    const samples = data.getChannelData(0);
    const values = Array.from({ length: 40 }, (_, i) => {
      const a = Math.floor((i * samples.length) / 40),
        b = Math.floor(((i + 1) * samples.length) / 40);
      let peak = 0;
      for (let k = a; k < b; k += 8)
        peak = Math.max(peak, Math.abs(samples[k]));
      return peak;
    });
    return { waveform: values, duration: data.duration };
  } finally {
    await ctx.close();
  }
}
export class Recorder {
  media: MediaRecorder | null = null;
  tracks: MediaStream | null = null;
  chunks: Blob[] = [];
  started = 0;
  timeout: ReturnType<typeof setTimeout> | null = null;
  async start(onLimit?: () => void) {
    this.tracks = await navigator.mediaDevices.getUserMedia({ audio: true });
    try {
      const mime = [
        "audio/webm;codecs=opus",
        "audio/ogg;codecs=opus",
        "audio/mp4",
      ].find((t) => MediaRecorder.isTypeSupported(t));
      this.media = new MediaRecorder(
        this.tracks,
        mime ? { mimeType: mime } : undefined,
      );
      this.chunks = [];
      this.media.ondataavailable = (e) => {
        if (e.data.size) this.chunks.push(e.data);
      };
      this.started = performance.now();
      this.media.start(250);
      this.timeout = setTimeout(() => {
        this.cancel();
        onLimit?.();
      }, 120000);
    } catch (e) {
      this.cleanup();
      throw e;
    }
  }
  async stop(): Promise<Blob> {
    const media = this.media;
    if (!media) throw Error("No recording");
    return new Promise((resolve, reject) => {
      media.onstop = () => {
        const blob = new Blob(this.chunks, {
          type: media.mimeType.split(";")[0],
        });
        this.cleanup();
        resolve(blob);
      };
      media.onerror = () => {
        this.cleanup();
        reject(Error("Recording failed"));
      };
      if (media.state === "inactive") {
        this.cleanup();
        reject(Error("Recording already stopped"));
      } else media.stop();
    });
  }
  cancel() {
    if (this.media) {
      this.media.ondataavailable = null;
      this.media.onstop = null;
      if (this.media.state !== "inactive") this.media.stop();
    }
    this.cleanup();
    this.chunks = [];
  }
  cleanup() {
    this.tracks?.getTracks().forEach((t) => t.stop());
    this.tracks = null;
    this.media = null;
    if (this.timeout) clearTimeout(this.timeout);
    this.timeout = null;
  }
}
