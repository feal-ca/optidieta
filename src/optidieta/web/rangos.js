// Gráfico de rangos: banda sana EFSA por nutriente y un punto (la dieta) que se arrastra para forzar un objetivo.
// data = {axis_max, rows: [...], selected, picked} (ver optidieta.rangos.nutrient_rows). Al soltar: trigger "move"
// {key, pct, from}; doble clic en el nombre: "reset" {key}; clic en el nombre: "pick" {key}.

const fmt = (v) =>
  v.toLocaleString("es-ES", { maximumFractionDigits: Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 1 ? 1 : 2 });

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  let root = parentElement.querySelector(".rg");
  if (!root) {
    root = document.createElement("div");
    root.className = "rg";
    parentElement.appendChild(root);
  }
  root.innerHTML = "";
  if (!data || !data.rows) return;

  const AX = data.axis_max;
  const clamp = (p) => Math.max(0, Math.min(AX, p));
  const left = (p) => (clamp(p) / AX) * 100 + "%";
  const el = (tag, cls, parent, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  };

  // Eje superior: 0 %, 100 % (referencia EFSA), 200 %, 300 %
  const axis = el("div", "row axis", root);
  el("div", "lab", axis);
  const at = el("div", "track", axis);
  for (let p = 0; p <= AX; p += 100) {
    const t = el("span", "tick", at, p === 100 ? "100 % (ref.)" : p + " %");
    t.style.left = left(p);
  }
  el("div", "val", axis);

  let group = null;
  for (const r of data.rows) {
    if (r.group !== group) {
      group = r.group;
      el("div", "group", root, group);
    }
    const row = el("div", "row" + (r.active ? "" : " inactive") + (r.edited ? " edited" : "")
      + (data.picked === r.key ? " picked" : ""), root);
    const lab = el("div", "lab", row, (r.warn ? "⚠ " : r.estimated ? "≈ " : "") + r.label);
    lab.title = "Clic: qué alimentos lo aportan" + (r.edited ? " · doble clic: volver al objetivo EFSA" : "");
    lab.addEventListener("click", () => setTriggerValue("pick", { key: r.key }));
    lab.addEventListener("dblclick", () => r.edited && setTriggerValue("reset", { key: r.key }));

    const track = el("div", "track", row);
    el("div", "ref", track).style.left = left(100);
    const band = el("div", "band" + (r.band_hi == null ? " open" : ""), track);
    band.style.left = left(r.band_lo);
    band.style.width = `calc(${left(r.band_hi ?? AX)} - ${left(r.band_lo)})`;
    if (r.band_hi == null && r.active) {
      // Sin máximo EFSA: sólida hasta +50 % sobre el mínimo y se desvanece hasta +100 %.
      const span = AX - r.band_lo;
      const a = Math.min(100, (50 / span) * 100), b = Math.min(100, (100 / span) * 100);
      band.style.background = `linear-gradient(to right, var(--band) ${a}%, transparent ${b}%)`;
    }
    band.title = `Rango sano EFSA: ${r.range_txt} ${r.unit}`;

    if (r.target_shown && (r.target_lo != null || r.target_hi != null)) {
      const tg = el("div", "target", track);
      const lo = r.target_lo ?? 0, hi = r.target_hi ?? AX;
      tg.style.left = left(lo);
      tg.style.width = `max(2px, calc(${left(hi)} - ${left(lo)}))`;
      tg.title = `Objetivo: ${r.target_txt} ${r.unit}`;
    }

    if (r.contrib != null && r.contrib > 0) {
      const cb = el("div", "contrib" + (r.contrib > AX ? " over" : ""), track);
      cb.style.left = "0";
      cb.style.width = left(r.contrib);
      cb.title = `${data.selected}: ${r.contrib_txt}`;
    }

    const val = el("div", "val", row);
    const main = el("span", "num", val, r.value_txt ?? "—");
    if (r.status === "bajo" || r.status === "alto") {
      el("span", "st " + r.status, val, r.status === "bajo" ? " ▼ bajo" : " ▲ alto");
    }
    if (data.selected) {
      const share = r.contrib_share != null ? ` (${Math.round(r.contrib_share * 100)} %)` : "";
      el("span", "aporte", val, ` aporta ${r.contrib_txt ?? "—"}${share}`);
    } else {
      el("span", "obj", val, r.edited ? ` tu obj. ${r.target_txt}` : r.target_shown ? ` obj. ${r.target_txt}` : ` EFSA ${r.range_txt}`);
    }

    if (r.value == null) continue;

    const dot = el("div", "dot" + (r.value > AX ? " over" : ""), track);
    dot.style.left = left(r.value);
    dot.tabIndex = 0;
    dot.setAttribute("role", "slider");
    dot.setAttribute("aria-label", `${r.label}: ${r.value_txt}`);
    dot.title = `${r.label}: ${r.value_txt}. Arrastra para pedir más o menos.`;

    let cur = r.value;
    const show = (p) => {
      cur = clamp(p);
      dot.style.left = left(cur);
      main.textContent = `→ ${fmt((cur / 100) * r.ref)} ${r.unit}`;
      row.classList.add("dragging");
    };
    const commit = () => {
      row.classList.remove("dragging");
      if (Math.abs(cur - Math.min(r.value, AX)) < 0.5) {
        main.textContent = r.value_txt;
        return;
      }
      setTriggerValue("move", { key: r.key, pct: cur, from: r.value });
    };
    const pctAt = (ev) => {
      const b = track.getBoundingClientRect();
      return ((ev.clientX - b.left) / b.width) * AX;
    };

    track.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      ev.preventDefault();
      track.setPointerCapture(ev.pointerId);
      show(pctAt(ev));
      const move = (e) => show(pctAt(e));
      const up = () => {
        track.removeEventListener("pointermove", move);
        track.removeEventListener("pointerup", up);
        track.removeEventListener("pointercancel", up);
        commit();
      };
      track.addEventListener("pointermove", move);
      track.addEventListener("pointerup", up);
      track.addEventListener("pointercancel", up);
    });
    dot.addEventListener("keydown", (ev) => {
      const step = ev.shiftKey ? 25 : 5;
      if (ev.key === "ArrowRight" || ev.key === "ArrowUp") show(cur + step);
      else if (ev.key === "ArrowLeft" || ev.key === "ArrowDown") show(cur - step);
      else if (ev.key === "Enter") commit();
      else return;
      ev.preventDefault();
    });
  }
}
