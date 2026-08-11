"use client";

import { useEffect, useRef } from "react";

/**
 * Fullscreen fragment shader driven by the car's energy state.
 *
 * This is a second readout, not decoration — that is the whole justification for it
 * existing. Warmth and brightness track state of charge, motion speed tracks active
 * deployment, and clipping desaturates the field toward grey while very nearly stopping
 * it: the visual language of a car flat out with nothing left to give.
 *
 * Raw WebGL, no library. This is one quad and one fragment shader; three.js would be
 * two orders of magnitude of code weight for a scene graph nothing here needs.
 *
 * Cost control, per the brief's 2 ms/frame budget:
 *   - the field is three rotated sine layers, not fbm. No loops, no texture reads.
 *   - the drawing buffer is capped at 1.5x CSS pixels, so a HiDPI display does not
 *     quadruple the fragment count for a background that is deliberately out of focus.
 *   - the loop stops entirely when the tab is hidden or the canvas scrolls off-screen.
 */

export interface FieldState {
  soc: number; // 0..1
  deploy: number; // 0..1
  clip: number; // 0..1
}

const VERTEX = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const FRAGMENT = `
precision mediump float;

uniform vec2  uRes;
uniform float uTime;
uniform float uSoc;
uniform float uDeploy;
uniform float uClip;

// Palette supplied from CSS so the field follows the active theme.
uniform vec3 uBase;
uniform vec3 uEmber;
uniform vec3 uCool;
uniform vec3 uGrey;
uniform float uLight;

// Three rotated sine layers. Cheap, and at this scale indistinguishable from noise.
float field(vec2 p) {
  float v = sin(p.x * 1.7 + p.y * 0.6);
  v += sin(p.y * 1.3 - p.x * 0.9) * 0.8;
  v += sin((p.x + p.y) * 0.8) * 0.6;
  return v / 2.4;
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  vec2 p = (uv - 0.5) * vec2(uRes.x / uRes.y, 1.0) * 3.2;

  // Clipping nearly freezes the field; deployment speeds it up.
  float rate = mix(0.035, 0.16, uDeploy) * (1.0 - 0.88 * uClip);
  float t = uTime * rate;

  // One cheap domain warp to keep the shapes from reading as plain stripes.
  vec2 warp = vec2(field(p + t), field(p.yx - t * 0.8));
  float f = field(p + warp * 0.75 + t * 0.5);
  f = f * 0.5 + 0.5;

  // A full store reads warm; a depleted one cools toward the harvest hue.
  vec3 tint = mix(uCool, uEmber, clamp(uSoc, 0.0, 1.0));
  tint = mix(tint, uGrey, clamp(uClip, 0.0, 1.0));

  // Brightness follows stored energy, with deployment adding a little lift.
  float energy = clamp(uSoc * 0.75 + uDeploy * 0.35, 0.0, 1.0);
  float intensity = pow(f, 2.6) * mix(0.05, 0.34, energy) * (1.0 - 0.55 * uClip);

  // Vignette keeps the centre of the page readable.
  float edge = smoothstep(1.25, 0.15, length(uv - 0.5) * 1.7);

  // On a pale ground the field has to DARKEN the surface; adding light to near-white
  // washes out to nothing and the background reads as a plain empty page.
  float amount = intensity * edge;
  vec3 lightMix = mix(uBase, tint, amount * 1.6);
  gl_FragColor = vec4(mix(uBase + tint * amount, lightMix, uLight), 1.0);
}
`;

function compile(gl: WebGLRenderingContext, type: number, src: string) {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, src);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

export function ShaderBackground({
  state,
  paused = false,
}: {
  state: React.RefObject<FieldState>;
  paused?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const failed = useRef(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const gl =
      canvas.getContext("webgl", { antialias: false, alpha: false, depth: false }) ??
      (canvas.getContext("experimental-webgl") as WebGLRenderingContext | null);

    if (!gl) {
      // Static fallback: the page must not depend on WebGL existing.
      failed.current = true;
      canvas.style.background =
        "radial-gradient(ellipse at 50% 40%, " +
        "color-mix(in srgb, var(--deploy) 12%, var(--surface)) 0%, var(--surface) 70%)";
      return;
    }

    const vs = compile(gl, gl.VERTEX_SHADER, VERTEX);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT);
    const program = gl.createProgram();
    if (!vs || !fs || !program) {
      canvas.style.background =
        "radial-gradient(ellipse at 50% 40%, " +
        "color-mix(in srgb, var(--deploy) 12%, var(--surface)) 0%, var(--surface) 70%)";
      return;
    }
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      canvas.style.background =
        "radial-gradient(ellipse at 50% 40%, " +
        "color-mix(in srgb, var(--deploy) 12%, var(--surface)) 0%, var(--surface) 70%)";
      return;
    }
    gl.useProgram(program);

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]),
      gl.STATIC_DRAW,
    );
    const aPos = gl.getAttribLocation(program, "aPos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    // Palette read from the stylesheet, so the shader and the page can never disagree
    // about what "deploy red" is, and both follow the theme from one definition.
    const palette = () => {
      const styles = getComputedStyle(document.documentElement);
      const rgb = (name: string, fallback: [number, number, number]) => {
        const raw = styles.getPropertyValue(name).trim();
        const parts = raw.startsWith("#")
          ? [1, 3, 5].map((i) => parseInt(raw.slice(i, i + 2), 16))
          : raw.match(/[\d.]+/g)?.slice(0, 3).map(Number);
        return parts && parts.length === 3
          ? (parts.map((v) => v / 255) as [number, number, number])
          : fallback;
      };
      return {
        base: rgb("--surface", [0.031, 0.035, 0.039]),
        ember: rgb("--deploy", [1, 0.18, 0.09]),
        cool: rgb("--harvest", [0.25, 0.88, 0.82]),
        grey: rgb("--clip", [0.54, 0.56, 0.6]),
        light: document.documentElement.dataset.theme === "light" ? 1 : 0,
      };
    };

    const uRes = gl.getUniformLocation(program, "uRes");
    const uBase = gl.getUniformLocation(program, "uBase");
    const uEmber = gl.getUniformLocation(program, "uEmber");
    const uCool = gl.getUniformLocation(program, "uCool");
    const uGrey = gl.getUniformLocation(program, "uGrey");
    const uLight = gl.getUniformLocation(program, "uLight");
    const uTime = gl.getUniformLocation(program, "uTime");
    const uSoc = gl.getUniformLocation(program, "uSoc");
    const uDeploy = gl.getUniformLocation(program, "uDeploy");
    const uClip = gl.getUniformLocation(program, "uClip");

    const resize = () => {
      // Cap the device pixel ratio: this is an out-of-focus background, and a 3x buffer
      // would cost 9x the fragments for no perceptible gain.
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const w = Math.floor(canvas.clientWidth * dpr);
      const h = Math.floor(canvas.clientHeight * dpr);
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
        gl.viewport(0, 0, w, h);
      }
      gl.uniform2f(uRes, canvas.width, canvas.height);
    };

    let frame: number | null = null;
    let visible = true;
    let onScreen = true;
    const start = performance.now();

    // Re-read only when the theme actually changes; getComputedStyle every frame would
    // force a style recalculation 60 times a second for values that almost never move.
    const applyPalette = () => {
      const p = palette();
      gl.uniform3fv(uBase, p.base);
      gl.uniform3fv(uEmber, p.ember);
      gl.uniform3fv(uCool, p.cool);
      gl.uniform3fv(uGrey, p.grey);
      gl.uniform1f(uLight, p.light);
    };
    applyPalette();

    const render = (now: number) => {
      resize();
      const s = state.current;
      // Reduced motion: draw one frame at the current state and never animate it.
      gl.uniform1f(uTime, reduced ? 0 : (now - start) / 1000);
      gl.uniform1f(uSoc, s?.soc ?? 0.5);
      gl.uniform1f(uDeploy, s?.deploy ?? 0);
      gl.uniform1f(uClip, s?.clip ?? 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      // The synchronous first call must not start the loop; only the scheduler does.
      if (!reduced && frame !== null) frame = requestAnimationFrame(render);
    };

    const stop = () => {
      if (frame !== null) cancelAnimationFrame(frame);
      frame = null;
    };
    const maybeStart = () => {
      if (paused || !visible || !onScreen || frame !== null) return;
      frame = requestAnimationFrame(render);
    };

    // Size and paint synchronously. Doing this only inside the frame loop leaves the
    // canvas at its default 300x150 backing store until the first frame arrives, which
    // shows as a stretched background on load — and never resolves at all anywhere
    // requestAnimationFrame is throttled to a stop.
    render(performance.now());

    // Repaint on theme change, including when the loop is paused or motion is reduced.
    const themeWatcher = new MutationObserver(() => {
      applyPalette();
      render(performance.now());
    });
    themeWatcher.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    if (reduced) {
      // Still repaint so the field tracks the energy state, just without a running
      // clock — uTime stays pinned at 0, so nothing moves. Called directly rather than
      // through requestAnimationFrame, which is throttled to nothing on a background or
      // non-compositing tab and would leave the colour stale.
      const id = window.setInterval(() => render(performance.now()), 400);
      return () => {
        window.clearInterval(id);
        themeWatcher.disconnect();
        stop();
      };
    }

    const onVisibility = () => {
      visible = !document.hidden;
      if (visible) maybeStart();
      else stop();
    };
    document.addEventListener("visibilitychange", onVisibility);

    const observer = new IntersectionObserver(
      ([entry]) => {
        onScreen = entry.isIntersecting;
        if (onScreen) maybeStart();
        else stop();
      },
      { threshold: 0 },
    );
    observer.observe(canvas);

    window.addEventListener("resize", resize);
    maybeStart();

    return () => {
      stop();
      observer.disconnect();
      themeWatcher.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("resize", resize);
      gl.deleteProgram(program);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
      gl.deleteBuffer(buffer);
    };
  }, [state, paused]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="fixed inset-0 -z-10 h-full w-full"
    />
  );
}
