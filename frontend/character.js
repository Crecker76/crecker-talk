// Крекер — character controller.
// Poses are CSS-driven (see style.css, keyed off data-state). The mouth is
// driven here in real time from the TTS audio level (lip-sync) while speaking.
(function () {
  "use strict";

  const STATES = ["idle", "listening", "thinking", "speaking"];

  const Character = {
    el: null,
    label: null,
    mouth: null,
    _raf: 0,

    init() {
      this.el = document.getElementById("character");
      this.label = document.getElementById("stateLabel");
      this.mouth = this.el ? this.el.querySelector(".mouth") : null;
      this._setMouth(0.05);
      this.setState("idle");
    },

    setState(state) {
      if (!STATES.includes(state)) return;
      if (!this.el) this.init();
      this.el.dataset.state = state;
      if (this.label) this.label.textContent = state;
      if (state === "speaking") this._startLipSync();
      else this._stopLipSync();
    },

    getState() {
      return this.el ? this.el.dataset.state : "idle";
    },

    // open: 0..1 -> mouth vertical scale
    _setMouth(open) {
      if (!this.mouth) return;
      const v = Math.max(0, Math.min(1, open));
      const sy = 0.15 + v * 1.7;
      this.mouth.style.transform = "scaleY(" + sy.toFixed(3) + ")";
    },

    _startLipSync() {
      if (this._raf) return;
      const loop = () => {
        const lvl = (window.AudioPlayer && window.AudioPlayer.getLevel)
          ? window.AudioPlayer.getLevel()
          : 0;
        this._setMouth(lvl);
        this._raf = requestAnimationFrame(loop);
      };
      this._raf = requestAnimationFrame(loop);
    },

    _stopLipSync() {
      if (this._raf) {
        cancelAnimationFrame(this._raf);
        this._raf = 0;
      }
      this._setMouth(0.05); // rest: nearly-closed mouth
    },
  };

  window.Character = Character;
  document.addEventListener("DOMContentLoaded", () => Character.init());
})();
