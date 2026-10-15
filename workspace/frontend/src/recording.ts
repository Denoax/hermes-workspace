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
  meter: AudioContext | null = null;
  meterSource: MediaStreamAudioSourceNode | null = null;
  meterFrame = 0;
  generation = 0;
  trackListeners: (() => void)[] = [];
  async start(
    onLimit?: () => void,
    onLevels?: (values: number[]) => void,
    onInterrupted?: () => void,
  ) {
    this.cancel();
    const generation = this.generation;
    const tracks = await navigator.mediaDevices.getUserMedia({ audio: true });
    // Browser permission can resolve after the operator cancelled or navigated.
    if (generation !== this.generation) {
      tracks.getTracks().forEach((track) => track.stop());
      throw new DOMException("Recording cancelled", "AbortError");
    }
    this.tracks = tracks;
    try {
      const interrupted = () => {
        this.cancel();
        onInterrupted?.();
      };
      for (const track of tracks.getTracks()) {
        track.addEventListener?.("ended", interrupted);
        this.trackListeners.push(() =>
          track.removeEventListener?.("ended", interrupted),
        );
      }
      const mime = [
        "audio/webm;codecs=opus",
        "audio/ogg;codecs=opus",
        "audio/mp4",
      ].find((t) => MediaRecorder.isTypeSupported(t));
      this.media = new MediaRecorder(
        this.tracks,
        mime ? { mimeType: mime } : undefined,
      );
      this.media.onerror = interrupted;
      this.chunks = [];
      this.media.ondataavailable = (e) => {
        if (e.data.size) this.chunks.push(e.data);
      };
      this.started = performance.now();
      this.media.start(250);
      if (onLevels) {
        this.meter = new AudioContext();
        this.meterSource = this.meter.createMediaStreamSource(this.tracks);
        const analyser = this.meter.createAnalyser();
        analyser.fftSize = 1024;
        this.meterSource.connect(analyser);
        const samples = new Float32Array(analyser.fftSize);
        let last = 0;
        const measure = (now: number) => {
          if (!this.meter) return;
          if (now - last >= 70) {
            analyser.getFloatTimeDomainData(samples);
            const levels = Array.from({ length: 32 }, (_, index) => {
              let peak = 0;
              for (let offset = index * 32; offset < (index + 1) * 32; offset++)
                peak = Math.max(peak, Math.abs(samples[offset]));
              return peak;
            });
            onLevels(levels);
            last = now;
          }
          this.meterFrame = requestAnimationFrame(measure);
        };
        this.meterFrame = requestAnimationFrame(measure);
      }
      this.timeout = setTimeout(() => {
        this.cancel();
        onLimit?.();
      }, 120000);
    } catch (e) {
      this.cancel();
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
    this.generation++;
    if (this.media) {
      this.media.ondataavailable = null;
      this.media.onstop = null;
      this.media.onerror = null;
      if (this.media.state !== "inactive") this.media.stop();
    }
    this.cleanup();
    this.chunks = [];
  }
  cleanup() {
    this.trackListeners.forEach((remove) => remove());
    this.trackListeners = [];
    if (this.meterFrame) cancelAnimationFrame(this.meterFrame);
    this.meterFrame = 0;
    this.meterSource?.disconnect();
    this.meterSource = null;
    const meter = this.meter;
    this.meter = null;
    if (meter) void meter.close();
    this.tracks?.getTracks().forEach((t) => t.stop());
    this.tracks = null;
    this.media = null;
    if (this.timeout) clearTimeout(this.timeout);
    this.timeout = null;
  }
}
