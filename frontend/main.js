// Frontend controller: WebSocket, character states, conversation log.
// Stage 1: text echo only (no mic). Mic/push-to-talk is added in stage 2,
// the EN/RU input switch in stage 3, the mode button in stage 4.
(function () {
  "use strict";

  const WS_URL =
    (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws";

  const state = {
    ws: null,
    connected: false,
    inputLang: "en",      // Whisper language; toggled by Tab (stage 3)
    mode: "conversation", // conversation | explain (stage 4)
    currentBot: null,     // open assistant bubble while streaming
  };

  const els = {};

  function cacheEls() {
    els.log = document.getElementById("log");
    els.connDot = document.getElementById("connDot");
    els.langBadge = document.getElementById("langBadge");
    els.modeLabel = document.getElementById("modeLabel");
    els.modeBtn = document.getElementById("modeBtn");
    els.textForm = document.getElementById("textForm");
    els.textInput = document.getElementById("textInput");
  }

  // ---------- conversation log ----------
  function addMsg(kind, text, who) {
    const div = document.createElement("div");
    div.className = "msg " + kind;
    if (who) {
      const w = document.createElement("span");
      w.className = "who";
      w.textContent = who;
      div.appendChild(w);
    }
    div.appendChild(document.createTextNode(text));
    els.log.appendChild(div);
    els.log.scrollTop = els.log.scrollHeight;
    return div;
  }

  function addUserMsg(text) { addMsg("user", text, "you"); }
  function addSysMsg(text) { addMsg("sys", text); }

  function botAppend(text) {
    if (!state.currentBot) {
      state.currentBot = addMsg("bot", "", "trainer");
    }
    state.currentBot.appendChild(document.createTextNode(text));
    els.log.scrollTop = els.log.scrollHeight;
  }

  function botFinalize() { state.currentBot = null; }

  // ---------- server message router ----------
  function onServerMessage(data) {
    switch (data.type) {
      case "state":
        // While TTS audio is still playing, let the playback drain decide when
        // to go idle (so the mouth keeps moving until the sound actually stops).
        if (data.state === "idle" && window.AudioPlayer && window.AudioPlayer.isBusy()) {
          break;
        }
        window.Character.setState(data.state);
        break;
      case "transcript":
        addUserMsg(data.text);
        break;
      case "llm_text":
        if (data.text) botAppend(data.text);
        if (data.final) botFinalize();
        break;
      case "mode":
        state.mode = data.mode;
        if (els.modeLabel) els.modeLabel.textContent = data.mode;
        break;
      case "info":
        addSysMsg(data.text);
        break;
      case "error":
        addSysMsg("⚠ " + data.text);
        break;
      default:
        break;
    }
  }

  // ---------- WebSocket ----------
  function connect() {
    state.ws = new WebSocket(WS_URL);
    state.ws.binaryType = "arraybuffer";

    state.ws.onopen = () => {
      state.connected = true;
      els.connDot.classList.add("online");
    };
    state.ws.onclose = () => {
      state.connected = false;
      els.connDot.classList.remove("online");
      window.Character.setState("idle");
      setTimeout(connect, 1500); // auto-reconnect
    };
    state.ws.onerror = () => { /* onclose will handle reconnect */ };
    state.ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        try { onServerMessage(JSON.parse(ev.data)); } catch (e) { /* ignore */ }
      } else {
        // binary = WAV audio clause
        window.Character.setState("speaking");
        if (window.AudioPlayer) window.AudioPlayer.enqueue(ev.data);
      }
    };
  }

  function sendJSON(obj) {
    if (state.connected && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify(obj));
    }
  }

  // ---------- input: debug text ----------
  function wireTextInput() {
    els.textForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = els.textInput.value.trim();
      if (!text) return;
      sendJSON({ type: "text", text: text, mode: state.mode, input_lang: state.inputLang });
      els.textInput.value = "";
    });
  }

  // ---------- input: microphone (push-to-talk, Space) ----------
  async function startTalking() {
    if (!state.connected) { addSysMsg("Not connected yet…"); return; }
    if (window.Mic.isRecording()) return;
    window.AudioPlayer.resume(); // unlock audio within the user gesture
    window.AudioPlayer.reset();
    try {
      await window.Mic.start();
    } catch (e) {
      addSysMsg("⚠ Microphone blocked. Allow mic access (needs http://localhost).");
      return;
    }
    document.body.classList.add("ptt-active");
    window.Character.setState("listening");
  }

  function stopTalking() {
    if (!window.Mic.isRecording()) return;
    window.Mic.stop(); // onData -> sendAudio
    document.body.classList.remove("ptt-active");
  }

  async function sendAudio(blob) {
    if (!blob || blob.size < 1200) { // too short to be speech
      window.Character.setState("idle");
      return;
    }
    const buf = await blob.arrayBuffer();
    sendJSON({ type: "audio_meta", input_lang: state.inputLang, mode: state.mode });
    if (state.connected && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(buf);
    }
  }

  function wireMic() {
    window.Mic.setOnData((blob) => sendAudio(blob));
    window.AudioPlayer.setOnDrain(() => window.Character.setState("idle"));
  }

  // ---------- keyboard ----------
  function typingInInput() {
    return document.activeElement === els.textInput;
  }

  function wireKeys() {
    document.addEventListener("keydown", (e) => {
      if (e.code === "Space") {
        if (typingInInput()) return;
        if (e.repeat) return;
        e.preventDefault();
        startTalking();
      }
    });
    document.addEventListener("keyup", (e) => {
      if (e.code === "Space") {
        if (typingInInput()) return;
        e.preventDefault();
        stopTalking();
      }
    });
  }

  // ---------- boot ----------
  document.addEventListener("DOMContentLoaded", async () => {
    cacheEls();
    try {
      const cfg = await fetch("/api/config").then((r) => r.json());
      state.mode = cfg.default_mode || state.mode;
      state.inputLang = cfg.default_input_lang || state.inputLang;
      if (els.modeLabel) els.modeLabel.textContent = state.mode;
      if (els.langBadge) els.langBadge.textContent = state.inputLang.toUpperCase();
    } catch (e) { /* defaults are fine */ }

    wireTextInput();
    wireMic();
    wireKeys();
    connect();
    addSysMsg("Hold Space to talk, or type below to test without a mic.");
  });

  // expose for later stages
  window.App = { state, sendJSON };
})();
