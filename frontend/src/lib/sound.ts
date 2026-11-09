/** Board sounds, synthesized with the Web Audio API (no audio files, nothing copied from other
 *  sites): a short filtered-noise "tock" with a low body for a wooden piece, two for castling,
 *  a brighter double hit for captures, a soft bell for check and short chimes for results. */
export type SoundKind = "move" | "capture" | "check" | "castle" | "promote" | "correct" | "wrong" | "illegal" | "start";

let ctx: AudioContext | null = null;
let enabled = true;
let volume = 0.7;
let noise: AudioBuffer | null = null;

export function configureSound(on: boolean, vol: number) {
  enabled = on;
  volume = Math.max(0, Math.min(1, vol));
}

function audio(): AudioContext | null {
  if (!enabled || volume <= 0) return null;
  try {
    if (!ctx) ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    if (ctx.state === "suspended") void ctx.resume();
    if (!noise) {
      noise = ctx.createBuffer(1, Math.floor(ctx.sampleRate * 0.2), ctx.sampleRate);
      const d = noise.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    }
    return ctx;
  } catch {
    return null;
  }
}

function tock(a: AudioContext, t: number, opts: { freq?: number; body?: number; gain?: number; bright?: number } = {}) {
  const { freq = 1700, body = 190, gain = 0.55, bright = 1.4 } = opts;
  const out = a.createGain();
  out.gain.value = gain * volume;
  out.connect(a.destination);
  // click: filtered noise burst
  const src = a.createBufferSource();
  src.buffer = noise;
  const bp = a.createBiquadFilter();
  bp.type = "bandpass";
  bp.frequency.value = freq;
  bp.Q.value = bright;
  const ng = a.createGain();
  ng.gain.setValueAtTime(1, t);
  ng.gain.exponentialRampToValueAtTime(0.001, t + 0.045);
  src.connect(bp).connect(ng).connect(out);
  src.start(t);
  src.stop(t + 0.06);
  // body: quick pitch-dropping sine
  const o = a.createOscillator();
  o.type = "sine";
  o.frequency.setValueAtTime(body, t);
  o.frequency.exponentialRampToValueAtTime(body * 0.6, t + 0.07);
  const og = a.createGain();
  og.gain.setValueAtTime(0.7, t);
  og.gain.exponentialRampToValueAtTime(0.001, t + 0.09);
  o.connect(og).connect(out);
  o.start(t);
  o.stop(t + 0.1);
}

function tone(a: AudioContext, t: number, freq: number, dur: number, gain: number, type: OscillatorType = "sine") {
  const o = a.createOscillator();
  o.type = type;
  o.frequency.value = freq;
  const g = a.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(gain * volume, t + 0.012);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g).connect(a.destination);
  o.start(t);
  o.stop(t + dur + 0.02);
}

export function play(kind: SoundKind) {
  const a = audio();
  if (!a) return;
  const t = a.currentTime + 0.005;
  switch (kind) {
    case "move":
      tock(a, t);
      break;
    case "capture":
      tock(a, t, { freq: 2400, body: 150, gain: 0.7, bright: 1.1 });
      tock(a, t + 0.035, { freq: 1300, body: 120, gain: 0.45 });
      break;
    case "castle":
      tock(a, t);
      tock(a, t + 0.11, { freq: 1500, body: 170 });
      break;
    case "check":
      tock(a, t);
      tone(a, t + 0.02, 880, 0.22, 0.12, "triangle");
      break;
    case "promote":
      tock(a, t);
      tone(a, t + 0.04, 660, 0.12, 0.1, "triangle");
      tone(a, t + 0.13, 990, 0.2, 0.1, "triangle");
      break;
    case "correct":
      tone(a, t, 1046.5, 0.18, 0.12, "triangle");
      tone(a, t + 0.11, 1318.5, 0.28, 0.12, "triangle");
      break;
    case "wrong":
      tone(a, t, 233, 0.22, 0.18, "sine");
      tone(a, t + 0.09, 175, 0.3, 0.16, "sine");
      break;
    case "illegal":
      tone(a, t, 140, 0.08, 0.12, "square");
      break;
    case "start":
      tone(a, t, 784, 0.12, 0.07, "triangle");
      break;
  }
}

/** Sound for a chess.js move result. */
export function moveSound(m: { san: string; flags: string } | null | undefined) {
  if (!m) return;
  if (m.san.includes("+") || m.san.includes("#")) play("check");
  else if (m.flags.includes("k") || m.flags.includes("q")) play("castle");
  else if (m.flags.includes("p")) play("promote");
  else if (m.flags.includes("c") || m.flags.includes("e")) play("capture");
  else play("move");
}
