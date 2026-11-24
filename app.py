"""Optidieta: la dieta más barata con productos de Mercadona. Ejecutar con `uv run streamlit run app.py`."""

import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import optidieta
from optidieta.catalog import load_catalog
from optidieta.cli import paths
from optidieta.mapping import read_mapping
from optidieta.nutrients import BY_KEY, col
from optidieta.optimizer import compare, solve
from optidieta.rangos import AXIS_MAX, combine_contrib, drag_edit, food_contrib, nutrient_rows, range_text, reference
from optidieta.state import EDAD, MARGEN, MAX_G, PESO_KG, UserState, apply_edits, load_state, save_state
from optidieta.targets import SIN_PESCADO, Profile, apply_margin, default_constraints, for_diet
from optidieta.ui import editor_key, reset_editors

st.set_page_config(page_title="Optidieta", page_icon="🥕", layout="wide")
P = paths()
FUENTES = {"mercadona": "etiqueta", "off": "Open Food Facts", "bedca": "BEDCA"}
DIETAS = {"omnivora": "Omnívora", "vegetariana": "Vegetariana", "vegana": "Vegana"}
WEB = Path(optidieta.__file__).resolve().parent / "web"
rangos_chart = st.components.v2.component(
    "optidieta_rangos", js=(WEB / "rangos.js").read_text(encoding="utf-8"),
    css=(WEB / "rangos.css").read_text(encoding="utf-8"))


def eur(x: float) -> str:
    return f"{x:.2f} €".replace(".", ",")


def num(x: float, d: int = 1) -> str:
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


if not P["catalog"].exists():
    st.title("Optidieta")
    st.info("Todavía no hay catálogo. Desde la carpeta del proyecto, ejecuta:\n\n"
            "```\nuv run optidieta fetch\nuv run optidieta propose\n# revisa data/mapping.csv\nuv run optidieta build\n```")
    st.stop()


@st.cache_data
def _catalog(path: str, mtime: float) -> pd.DataFrame:
    return load_catalog(path)


@st.cache_data
def _pending(path: str, mtime: float) -> int:
    m = read_mapping(path)
    return int(((m.revisado != "sí") & (m.excluir != "sí")).sum()) if len(m) else 0


cat = _catalog(str(P["catalog"]), P["catalog"].stat().st_mtime)
if "state" not in st.session_state:
    st.session_state.state = load_state(P["data"] / "estado.json")
S: UserState = st.session_state.state
names = dict(zip(cat.id.astype(str), cat.nombre))


def save_and_rerun():
    save_state(st.session_state.state, P["data"] / "estado.json")
    reset_editors(st.session_state)  # si no, Streamlit reaplica la última edición sobre las filas nuevas
    st.rerun()


def set_edit(key: str, e: dict):
    if e:
        S.constraint_edits[key] = e
    else:
        S.constraint_edits.pop(key, None)


base = for_diet(default_constraints(S.profile), S.diet)  # EFSA: la banda verde
defaults = apply_margin(base, S.margen)  # EFSA con el margen de seguridad: el objetivo si no tocas nada
defaults_by = {c.key: c for c in defaults}
constraints = apply_edits(defaults, S.constraint_edits)

# ---------- barra lateral: dieta, perfil y requisitos extra ----------
with st.sidebar:
    st.header("Dieta")
    diet = st.radio("Dieta", list(DIETAS), format_func=DIETAS.get, index=list(DIETAS).index(S.diet),
                    horizontal=True, label_visibility="collapsed")

    st.header("Perfil")
    sexo = st.radio("Sexo", ["h", "m"], format_func={"h": "Hombre", "m": "Mujer"}.get,
                    index=["h", "m"].index(S.profile.sexo), horizontal=True)
    c1, c2 = st.columns(2)
    edad = c1.number_input("Edad", *EDAD, S.profile.edad)
    peso = c2.number_input("Peso (kg)", *PESO_KG, float(S.profile.peso_kg), step=1.0)

    st.header("Requisitos extra")
    max_g = st.slider("Máximo por alimento (g/día)", int(MAX_G[0]), int(MAX_G[1]), int(S.max_g), step=50)
    margen = st.slider("Margen de seguridad", int(MARGEN[0] * 100), int(MARGEN[1] * 100), round(S.margen * 100),
                       step=5, format="%d %%",
                       help="Sube los mínimos y baja los máximos EFSA este porcentaje, para que la dieta no quede "
                            "justo en el límite. No afecta a la energía ni a los objetivos que hayas movido tú.")
    new = (diet, Profile(sexo, int(edad), float(peso)), float(max_g), margen / 100)
    if new != (S.diet, S.profile, S.max_g, S.margen):
        S.diet, S.profile, S.max_g, S.margen = new
        save_and_rerun()

    for c in constraints:
        b = defaults_by[c.key]
        if b.active:
            continue  # solo los límites opcionales (desactivados por defecto) van aquí
        verbo = "Mínimo de" if b.min is not None and b.max is None else "Limitar"
        ayuda = b.fuente + (". Sin pescado solo se cumple con un suplemento (p. ej. aceite de algas)."
                            if c.key in SIN_PESCADO else "")
        on = st.toggle(f"{verbo} {c.label} ({range_text(b)} {c.unit})", value=c.active, help=ayuda)
        if on != c.active:
            e = dict(S.constraint_edits.get(c.key, {}))
            if on == b.active:
                e.pop("active", None)
            else:
                e["active"] = on
            set_edit(c.key, e)
            save_and_rerun()

    vet = st.multiselect("Productos que no quiero", options=sorted(names, key=names.get), default=sorted(S.excluded),
                         format_func=lambda i: names.get(i, i), placeholder="Busca un producto…",
                         key=editor_key("vetos", sorted(S.excluded)))
    if set(vet) != S.excluded:
        S.excluded = set(vet)
        save_and_rerun()

    st.divider()
    ajustes = len(S.constraint_edits)
    st.caption(f"{len(S.excluded)} vetados · {len(S.price_overrides)} precios propios · {ajustes} objetivos ajustados")
    if st.button("Restablecer todo"):
        st.session_state.state = UserState.default()
        save_and_rerun()

# ---------- cálculo ----------
sol = solve(cat, constraints, excluded=frozenset(S.excluded), price_overrides=S.price_overrides,
            max_g=S.max_g, diet=S.diet)
prev = st.session_state.get("prev")
st.session_state.prev = sol if sol.feasible else prev

st.title("Optidieta")
pend = _pending(str(P["mapping"]), P["mapping"].stat().st_mtime) if P["mapping"].exists() else 0
fetched = P["merca"] / "fetched_at.txt"
st.caption(f"{len(cat)} productos de Mercadona (Barcelona)"
           + (f" · precios del {fetched.read_text().strip()[:10]}" if fetched.exists() else "")
           + (f" · ⚠ {pend} productos sin revisar en mapping.csv" if pend else ""))

# ---------- alimentos ----------
selected: list[tuple[str, str, float]] = []  # (id, nombre, gramos) elegidos en la lista
if not sol.feasible:
    labels = [BY_KEY[k].label for k in sol.blocking] or ["el cálculo falló"]
    st.error("No hay ninguna dieta que cumpla todos los objetivos. Lo impiden: **" + ", ".join(labels) + "**.")
    st.markdown("Puedes desactivar o volver al valor EFSA del objetivo que lo bloquea, permitir más gramos por "
                "alimento o quitar vetos.")
    cols = st.columns(min(len(sol.blocking), 4) or 1)
    for i, k in enumerate(sol.blocking):
        col_ = cols[i % len(cols)]
        if k in S.constraint_edits and col_.button(f"{BY_KEY[k].label}: volver a EFSA", key=f"efsa_{k}"):
            S.constraint_edits.pop(k)
            save_and_rerun()
        if col_.button(f"Desactivar {BY_KEY[k].label}", key=f"off_{k}"):
            S.constraint_edits.setdefault(k, {})["active"] = False
            save_and_rerun()
else:
    d = compare(prev, sol) if prev else None
    c1, c2, c3 = st.columns(3)
    c1.metric("Coste al día", eur(sol.cost_day), delta=(eur(d.cost_delta) if d and abs(d.cost_delta) > 0.005 else None),
              delta_color="inverse")
    c2.metric("Coste a la semana", eur(sol.cost_day * 7))
    c3.metric("Alimentos", len(sol.portions))
    apagados = [c for c in constraints if c.key in SIN_PESCADO and not c.active]
    if apagados and S.diet != "omnivora":
        omni = solve(cat, constraints, excluded=frozenset(S.excluded), price_overrides=S.price_overrides,
                     max_g=S.max_g, diet="omnivora")
        st.caption(f"Este precio no incluye el mínimo de {', '.join(c.label for c in apagados)}, que sin pescado solo "
                   "se cubre con un suplemento (p. ej. de algas)."
                   + (f" Con los mismos objetivos, la omnívora costaría {eur(omni.cost_day)}." if omni.feasible else ""))
    if d and (d.added or d.removed):
        st.caption(" · ".join(filter(None, [
            ("Entra: " + ", ".join(names.get(i, i) for i in d.added)) if d.added else "",
            ("Sale: " + ", ".join(names.get(i, i) for i in d.removed)) if d.removed else ""])))

    info = cat.set_index(cat.id.astype(str))
    por = pd.DataFrame([{
        "id": p.id, "Producto": p.nombre, "g/día": round(p.grams), "€/día": round(p.cost, 2),
        "Fuente": FUENTES.get(info.fuente_etiqueta[p.id], "BEDCA"), "Mercadona": info.url[p.id],
    } for p in sol.portions])
    if por.empty:
        st.info("Con los objetivos activos no hace falta comer nada. Activa alguno en «Editar objetivos».")
    else:
        left, right = st.columns([1, 1], gap="large")
        with left:
            ev = st.dataframe(
                por, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="multi-row",
                column_config={"id": None, "Mercadona": st.column_config.LinkColumn(display_text="ver"),
                               "€/día": st.column_config.NumberColumn(format="%.2f €")},
                key=editor_key("portions", por.id))
            grams = {p.id: p.grams for p in sol.portions}
            selected = [(por.id.iloc[i], por.Producto.iloc[i], grams[por.id.iloc[i]]) for i in (ev.selection.rows if ev else [])]
            if selected:
                quitar = (f"«{selected[0][1]}»" if len(selected) == 1 else f"los {len(selected)} alimentos elegidos")
                if st.button(f"Quitar {quitar} de la dieta", icon="🚫"):
                    S.excluded |= {i for i, _, _ in selected}
                    save_and_rerun()
            else:
                st.caption("Selecciona uno o varios alimentos para ver qué aportan entre todos, o para quitarlos.")
        with right:
            if "_pick" in st.session_state:
                st.session_state["ver_nutriente"] = st.session_state.pop("_pick")
            ver = st.selectbox("Barras", ["gramos"] + [c.key for c in constraints], key="ver_nutriente",
                               format_func=lambda k: "Gramos de cada alimento" if k == "gramos"
                               else f"Quién aporta: {BY_KEY[k].label}",
                               help="También puedes hacer clic en el nombre de un nutriente en el gráfico de abajo.")
            sel_ids = {i for i, _, _ in selected}
            if ver == "gramos":
                bars = por.assign(v=por["g/día"].astype(float), etiqueta=por["g/día"].astype(str) + " g")
                xtitle = "gramos al día"
            else:
                cv = next(c for c in constraints if c.key == ver)
                vals = [food_contrib(info.loc[i], grams[i], [cv], sol)[ver] for i in por.id]
                tot = sum(v for v in vals if v is not None) or 0
                bars = por.assign(
                    v=[v or 0.0 for v in vals],
                    etiqueta=["sin dato" if v is None else f"{num(v, 2 if v < 10 else 0)} {cv.unit}"
                              + (f" ({v / tot:.0%})" if tot else "") for v in vals])
                xtitle = f"{cv.label} ({cv.unit}) que aporta cada alimento"
            bars = bars.assign(sel=bars["id"].isin(sel_ids))
            base_ch = alt.Chart(bars).encode(
                y=alt.Y("Producto:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
                x=alt.X("v:Q", title=xtitle, axis=alt.Axis(grid=False)),
                tooltip=["Producto", alt.Tooltip("etiqueta:N", title="aporta" if ver != "gramos" else "g/día"),
                         alt.Tooltip("€/día:Q", title="€/día", format=".2f")])
            color = (alt.condition("datum.sel", alt.value("#2a78d6"), alt.value("#9ec2ee")) if selected
                     else alt.value("#2a78d6"))
            chart = (base_ch.mark_bar(cornerRadiusEnd=4, height={"band": 0.7}).encode(color=color)
                     + base_ch.mark_text(align="left", dx=4, color="gray").encode(text="etiqueta:N"))
            st.altair_chart(chart.properties(height=max(120, 30 * len(bars))), use_container_width=True)

# ---------- nutrientes: rango sano y punto arrastrable ----------
st.subheader("Nutrientes")
st.caption("La banda verde es el rango sano EFSA para tu perfil; el punto negro, dónde te deja esta dieta (en % de la "
           "referencia). **Arrastra el punto** para pedir más o menos de un nutriente: a la derecha fija un mínimo, a la "
           "izquierda un máximo. La raya negra bajo la banda es tu objetivo; doble clic en el nombre (en negrita) lo "
           "devuelve a EFSA. Un clic en el nombre muestra arriba qué alimentos lo aportan. ⚠ = falta el dato en parte de los alimentos (cuenta como 0). ≈ = parte del dato es una "
           "estimación por subcategoría (azúcares, grasa saturada o grasa de fruta y verdura).")
contrib, contrib_partial = None, set()
if selected:
    contrib, contrib_partial = combine_contrib([food_contrib(info.loc[i], g, constraints, sol) for i, _, g in selected])
    quien = (f"**{selected[0][1]}** ({selected[0][2]:.0f} g/día)" if len(selected) == 1
             else f"los **{len(selected)} alimentos elegidos** ({sum(g for _, _, g in selected):.0f} g/día)")
    st.markdown(f"Aporte de {quien}: la barra azul de cada fila. Quita la selección de la lista para volver a ver "
                "los objetivos.")
est_keys = set()
if sol.feasible and "estimados" in cat:
    est_col = cat.set_index(cat.id.astype(str))["estimados"]
    for p in sol.portions:
        est_keys |= set(filter(None, str(est_col.get(p.id, "")).split(",")))
rows = nutrient_rows(base, constraints, sol, contrib=contrib, defaults=defaults, estimated=est_keys,
                     contrib_partial=contrib_partial)
nombre_sel = (selected[0][1] if len(selected) == 1 else f"{len(selected)} alimentos") if selected else None
res = rangos_chart(data={"axis_max": AXIS_MAX, "rows": rows, "selected": nombre_sel,
                         "picked": st.session_state.get("ver_nutriente")},
                   key="rangos",
                   on_move_change=lambda: None, on_reset_change=lambda: None, on_pick_change=lambda: None)
if res.pick and res.pick["key"] != st.session_state.get("ver_nutriente"):
    st.session_state["_pick"] = res.pick["key"]  # el selectbox ya existe: se aplica al principio de la próxima pasada
    st.rerun()
if res.move:
    m = res.move
    set_edit(m["key"], drag_edit(defaults_by[m["key"]], m.get("from"), float(m["pct"]),
                                      ref=reference(next(b for b in base if b.key == m["key"]))))
    save_and_rerun()
if res.reset:
    S.constraint_edits.pop(res.reset["key"], None)
    save_and_rerun()
if S.constraint_edits and st.button(f"Volver a los objetivos EFSA ({len(S.constraint_edits)} ajustados)"):
    S.constraint_edits = {}
    save_and_rerun()

with st.expander("Tabla de nutrientes"):
    trows = []
    cby = {c.key: c for c in constraints}
    for r in rows:
        c, t = cby[r["key"]], sol.totals.get(r["key"])
        ok = r["status"] == "ok" if r["status"] else None
        trows.append({"": "—" if not c.active else "" if ok is None else ("⚠" if r["warn"] else "✓") if ok else "✗",
                      "Nutriente": c.label, "Total": r["value_txt"] or "—", "Objetivo": range_text(c) + " " + c.unit,
                      "Con dato": f"{t.known_fraction:.0%}" if t else "—"})
    st.dataframe(pd.DataFrame(trows), hide_index=True, use_container_width=True)

with st.expander("Editar objetivos"):
    st.caption("Valores de referencia EFSA para tu perfil. Los % E son porcentaje de la energía total.")
    pct = lambda c, v: None if v is None else (v * 100 if c.kind == "pct_energia" else v)
    odf = pd.DataFrame([{"key": c.key, "Activo": c.active, "Nutriente": c.label, "Unidad": c.unit,
                         "Mínimo": pct(c, c.min), "Máximo": pct(c, c.max), "Fuente": c.fuente} for c in constraints])
    okey = editor_key("objetivos", [json.dumps(S.constraint_edits, sort_keys=True)])
    oed = st.data_editor(odf, hide_index=True, use_container_width=True, disabled=["Nutriente", "Unidad", "Fuente"],
                         column_config={"key": None}, key=okey)
    if st.session_state.get(okey, {}).get("edited_rows"):
        edits = {}
        for r in oed.itertuples():
            b = defaults_by[r.key]
            unpct = lambda v: None if v is None or pd.isna(v) else (v / 100 if b.kind == "pct_energia" else float(v))
            e = {}
            if bool(r.Activo) != b.active:
                e["active"] = bool(r.Activo)
            mn, mx = unpct(r.Mínimo), unpct(r.Máximo)
            if (mn is None) != (b.min is None) or (mn is not None and abs(mn - b.min) > 1e-9):
                e["min"] = mn
            if (mx is None) != (b.max is None) or (mx is not None and abs(mx - b.max) > 1e-9):
                e["max"] = mx
            if e:
                edits[r.key] = e
        if edits != S.constraint_edits:
            S.constraint_edits = edits
            save_and_rerun()

with st.expander("Catálogo y precios"):
    c1, c2, c3 = st.columns([3, 2, 1])
    q = c1.text_input("Buscar", placeholder="lentejas, leche, atún…")
    cats = ["Todas"] + sorted(cat.categoria.unique())
    fc = c2.selectbox("Categoría", cats)
    only = c3.radio("Mostrar", ["Todos", "En la dieta", "Vetados"], horizontal=False)
    view = cat
    if q:
        words = q.lower().split()
        view = view[view.nombre.str.lower().apply(lambda s: all(w in s for w in words))]
    if fc != "Todas":
        view = view[view.categoria == fc]
    in_diet = {p.id for p in sol.portions}
    if only == "En la dieta":
        view = view[view.id.astype(str).isin(in_diet)]
    elif only == "Vetados":
        view = view[view.id.astype(str).isin(S.excluded)]
    if S.diet != "omnivora":
        view = view[view["vegano" if S.diet == "vegana" else "vegetariano"]]
    cdf = pd.DataFrame({
        "id": view.id.astype(str), "Vetado": view.id.astype(str).isin(S.excluded), "Producto": view.nombre,
        "Categoría": view.subcategoria, "€/100 g Mercadona": view.precio_100g.round(3),
        "Mi precio €/100 g": [S.price_overrides.get(str(i)) for i in view.id],
        "Proteína g": view[col("proteina_g")].round(1), "kcal": view[col("energia_kcal")].round(0),
        "Fuente": view.fuente_etiqueta.map(FUENTES),
        "BEDCA": view.bedca_nombre, "Mercadona": view.url,
    }).head(500)
    st.caption(f"{len(view)} productos" + (" (se muestran 500)" if len(view) > 500 else ""))
    ced = st.data_editor(
        cdf, hide_index=True, use_container_width=True,
        disabled=[c for c in cdf.columns if c not in ("Vetado", "Mi precio €/100 g")],
        column_config={"id": None, "Mercadona": st.column_config.LinkColumn(display_text="ver"),
                       "Mi precio €/100 g": st.column_config.NumberColumn(min_value=0.01, format="%.3f",
                                                                          help="Vacío = precio de Mercadona")},
        key=editor_key("catalogo", cdf.id))  # con otras filas (otro filtro), otra tabla: sin ediciones fantasma
    changed = False
    for r in ced.to_dict("records"):
        rid = r["id"]
        if r["Vetado"] and rid not in S.excluded:
            S.excluded.add(rid); changed = True
        elif not r["Vetado"] and rid in S.excluded:
            S.excluded.discard(rid); changed = True
        v = r["Mi precio €/100 g"]
        cur = S.price_overrides.get(rid)
        if v is None or pd.isna(v):
            if cur is not None:
                del S.price_overrides[rid]; changed = True
        elif v >= 0.01 and cur != float(v):
            S.price_overrides[rid] = float(v); changed = True
    if changed:
        save_and_rerun()
