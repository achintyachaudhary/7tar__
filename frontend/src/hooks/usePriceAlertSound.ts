import { useEffect } from "react";
import { useAppSocket } from "../context/AppSocketContext";

function playSoftChime(ctx: AudioContext, startAt: number) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();

  osc.type = "sine";
  osc.frequency.value = 520;

  // Gentle attack and decay — avoids the sharp click of an instant full-volume tone.
  gain.gain.setValueAtTime(0, startAt);
  gain.gain.linearRampToValueAtTime(0.08, startAt + 0.06);
  gain.gain.exponentialRampToValueAtTime(0.001, startAt + 0.45);

  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(startAt);
  osc.stop(startAt + 0.5);
}

function playAlertChime() {
  try {
    const ctx = new AudioContext();
    const t0 = ctx.currentTime;
    playSoftChime(ctx, t0);
    playSoftChime(ctx, t0 + 0.55);
    window.setTimeout(() => {
      void ctx.close();
    }, 1200);
  } catch {
    // Audio may be blocked until user interaction
  }
}

/** Listen for server price-alert triggers and play a beep in the browser. */
export function usePriceAlertSound() {
  const { subscribe } = useAppSocket();

  useEffect(() => {
    return subscribe("alert:triggered", () => {
      playAlertChime();
    });
  }, [subscribe]);
}
