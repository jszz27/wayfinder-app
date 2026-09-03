// Converts the browser's Float32 audio into the wire format agreed with
// backend-ws: 16 kHz mono PCM16, little-endian, in ~100 ms chunks.
//
// This runs on the audio thread. Doing the conversion here rather than on
// the main thread keeps captions from stuttering when React re-renders.
//
// Chrome does not always honour a requested 16 kHz AudioContext, so the
// processor resamples from whatever `sampleRate` it actually got.

class PcmChunker extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const { targetSampleRate, framesPerChunk } = options.processorOptions;

    this.ratio = sampleRate / targetSampleRate;
    this.framesPerChunk = framesPerChunk;

    this.bytes = new Uint8Array(framesPerChunk * 2);
    this.view = new DataView(this.bytes.buffer);
    this.frames = 0;

    // Linear resampling carries state across process() blocks: `tail` is
    // the unconsumed input, `position` the fractional read cursor into it.
    this.tail = new Float32Array(0);
    this.position = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel || channel.length === 0) return true;

    const pending = new Float32Array(this.tail.length + channel.length);
    pending.set(this.tail, 0);
    pending.set(channel, this.tail.length);

    let position = this.position;
    while (Math.floor(position) + 1 < pending.length) {
      const index = Math.floor(position);
      const fraction = position - index;
      const sample =
        pending[index] * (1 - fraction) + pending[index + 1] * fraction;
      this.writeSample(sample);
      position += this.ratio;
    }

    const consumed = Math.floor(position);
    this.tail = pending.slice(consumed);
    this.position = position - consumed;
    return true;
  }

  writeSample(sample) {
    const clamped = Math.max(-1, Math.min(1, sample));
    const pcm = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
    this.view.setInt16(this.frames * 2, pcm, true); // little-endian
    this.frames += 1;

    if (this.frames === this.framesPerChunk) {
      const chunk = this.bytes.slice();
      this.port.postMessage(chunk.buffer, [chunk.buffer]);
      this.frames = 0;
    }
  }
}

registerProcessor("pcm-chunker", PcmChunker);
