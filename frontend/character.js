// Animated character controller.
// All visuals are CSS-driven (see style.css); this just flips the
// data-state attribute and keeps the state label in sync.
(function () {
  "use strict";

  const STATES = ["idle", "listening", "thinking", "speaking"];

  const Character = {
    el: null,
    label: null,

    init() {
      this.el = document.getElementById("character");
      this.label = document.getElementById("stateLabel");
      this.setState("idle");
    },

    setState(state) {
      if (!STATES.includes(state)) return;
      if (!this.el) this.init();
      this.el.dataset.state = state;
      if (this.label) this.label.textContent = state;
    },

    getState() {
      return this.el ? this.el.dataset.state : "idle";
    },
  };

  window.Character = Character;
  document.addEventListener("DOMContentLoaded", () => Character.init());
})();
