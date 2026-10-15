import type { Recorder } from "./recording";
type Owner = {
  session: string;
  generation: number;
  selected: () => boolean;
  rejectStop?: () => void;
};
const cancelled = () => new DOMException("Recording cancelled", "AbortError");

/** Conversation/policy lifetime around the existing device recorder. */
export class RecordingSession {
  private generation = 0;
  private owner: Owner | null = null;
  constructor(
    private readonly recorder: Pick<Recorder, "start" | "stop" | "cancel">,
  ) {}
  private current(owner: Owner) {
    return this.owner === owner && owner.generation === this.generation;
  }
  private requireCurrent(owner: Owner) {
    if (!this.current(owner) || !owner.selected()) throw cancelled();
  }
  cancel(): boolean {
    const owner = this.owner;
    this.owner = null;
    this.generation++;
    owner?.rejectStop?.();
    this.recorder.cancel();
    return !!owner;
  }
  reconcile(
    session: string | null,
    microphoneAllowed: boolean | undefined,
  ): "conversation" | "permission" | null {
    if (!this.owner) return null;
    const reason =
      this.owner.session !== session
        ? "conversation"
        : microphoneAllowed === false
          ? "permission"
          : null;
    if (reason) this.cancel();
    return reason;
  }
  async start(
    session: string,
    authorize: () => Promise<unknown>,
    selected: () => boolean,
    callbacks: Parameters<Recorder["start"]>,
  ) {
    this.cancel();
    const owner = { session, generation: this.generation, selected };
    this.owner = owner;
    try {
      this.requireCurrent(owner);
      await authorize();
      this.requireCurrent(owner);
      await this.recorder.start(...callbacks);
      this.requireCurrent(owner);
    } catch (error) {
      const stale = !this.current(owner) || !selected();
      if (this.current(owner)) this.cancel();
      if (stale) throw cancelled();
      throw error;
    }
  }
  async stop(): Promise<Blob>;
  async stop<T>(prepare: (blob: Blob) => Promise<T>): Promise<T>;
  async stop<T>(prepare?: (blob: Blob) => Promise<T>): Promise<Blob | T> {
    const owner = this.owner;
    if (!owner) throw cancelled();
    const interrupted = new Promise<never>((_, reject) => {
      owner.rejectStop = () => reject(cancelled());
    });
    const finish = async () => {
      const blob = await this.recorder.stop();
      this.requireCurrent(owner);
      const result = prepare ? await prepare(blob) : blob;
      this.requireCurrent(owner);
      return result;
    };
    try {
      const result = await Promise.race([finish(), interrupted]);
      this.requireCurrent(owner);
      this.owner = null;
      this.generation++;
      return result;
    } catch (error) {
      if (this.current(owner)) this.cancel();
      throw error;
    } finally {
      owner.rejectStop = undefined;
    }
  }
}
