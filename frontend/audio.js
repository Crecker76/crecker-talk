// Audio: playback queue (Web Audio) + microphone recorder (MediaRecorder).
// All audio stays in the browser; only encoded bytes cross the WebSocket.
(function () {
  "use strict";

  // ---------- playback: sequential queue of WAV chunks ----------
  const AudioPlayer = (function () {
    let ctx = null;
    let analyser = null;
    let nextTime = 0;
    let pending = 0;
    let onDrain = null;

    function ensure() {
      if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
      if (ctx.state === "suspended") ctx.resume();
      if (!analyser) {
        analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.55;
        analyser.connect(ctx.destination); // analyser -> speakers
      }
      return ctx;
    }

    // Current playback loudness 0..1 (RMS), used by the character for lip-sync.
    function getLevel() {
      if (!analyser) return 0;
      const buf = new Uint8Array(analyser.fftSize);
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) {
        const d = (buf[i] - 128) / 128;
        sum += d * d;
      }
      const rms = Math.sqrt(sum / buf.length);
      return Math.min(1, rms * 3.4);
    }

    async function enqueue(arrayBuffer) {
      ensure();
      pending++;
      let buf;
      try {
        // decodeAudioData detaches the buffer, so hand it a copy
        buf = await ctx.decodeAudioData(arrayBuffer.slice(0));
      } catch (e) {
        pending--;
        return;
      }
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(analyser); // -> analyser -> destination (so we can read the level)
      const start = Math.max(ctx.currentTime + 0.02, nextTime);
      src.start(start);
      nextTime = start + buf.duration;
      src.onended = () => {
        pending--;
        if (pending <= 0 && typeof onDrain === "function") onDrain();
      };
    }

    return {
      enqueue,
      resume: () => ensure(),
      isBusy: () => pending > 0,
      reset: () => { nextTime = 0; },
      setOnDrain: (f) => { onDrain = f; },
      getLevel,
    };
  })();

  // ---------- recording: push-to-talk ----------
  const Mic = (function () {
    let stream = null;
    let rec = null;
    let chunks = [];
    let mime = "";
    let recording = false;
    let onData = null;

    function pickMime() {
      const opts = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
      for (const m of opts) {
        if (window.MediaRecorder && MediaRecorder.isTypeSupported(m)) return m;
      }
      return "";
    }

    async function ensureStream() {
      if (stream) return stream;
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      return stream;
    }

    async function start() {
      if (recording) return;
      await ensureStream();
      mime = pickMime();
      rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunks = [];
      rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
      rec.onstop = () => {
        recording = false;
        const type = mime || "audio/webm";
        const blob = new Blob(chunks, { type });
        if (typeof onData === "function") onData(blob, type);
      };
      rec.start();
      recording = true;
    }

    function stop() {
      if (recording && rec && rec.state !== "inactive") rec.stop();
    }

    return {
      start,
      stop,
      isRecording: () => recording,
      setOnData: (f) => { onData = f; },
    };
  })();

  window.AudioPlayer = AudioPlayer;
  window.Mic = Mic;
})();
