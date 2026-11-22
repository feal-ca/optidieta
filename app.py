"""Optidieta: la dieta más barata con productos de Mercadona. Ejecutar con `uv run streamlit run app.py`."""

import pandas as pd
import streamlit as st

from optidieta.catalog import load_catalog
from optidieta.cli import paths
from optidieta.mapping import read_mapping
from optidieta.nutrients import BY_KEY, NUTRIENTS, col
from optidieta.optimizer import compare, solve
from optidieta.state import UserState, apply_edits, load_state, save_state
from optidieta.targets import Profile, default_constraints

st.set_page_config(page_title="Optidieta", page_icon="🥕", layout="wide")
P = paths()
DIETAS = {"omnivora": "Omnívora", "vegetariana": "Vegetariana", "vegana": "Vegana"}


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


def save_and_rerun():
    save_state(S, P["data"] / "estado.json")
    st.rerun()


# ---------- barra lateral ----------
with st.sidebar:
    st.header("Perfil")
    diet = st.radio("Dieta", list(DIETAS), format_func=DIETAS.get, index=list(DIETAS).index(S.diet), horizontal=True)
    sexo = st.radio("Sexo", ["h", "m"], format_func={"h": "Hombre", "m": "Mujer"}.get,
                    index=["h", "m"].index(S.profile.sexo), horizontal=True)
    edad = st.number_input("Edad", 18, 99, S.profile.edad)
    peso = st.number_input("Peso (kg)", 30.0, 200.0, float(S.profile.peso_kg), step=1.0)
    max_g = st.slider("Máximo por alimento (g/día)", 100, 1500, int(S.max_g), step=50)
    new = (diet, Profile(sexo, int(edad), float(peso)), float(max_g))
    if new != (S.diet, S.profile, S.max_g):
        S.diet, S.profile, S.max_g = new
        save_and_rerun()
    st.divider()
    st.caption(f"{len(S.excluded)} vetados · {len(S.price_overrides)} precios editados · "
               f"{len(S.constraint_edits)} objetivos cambiados")
    if st.button("Restablecer todo"):
        st.session_state.state = UserState.default()
        S = st.session_state.state
        save_and_rerun()

base = default_constraints(S.profile)
constraints = apply_edits(base, S.constraint_edits)
sol = solve(cat, constraints, excluded=frozenset(S.excluded), price_overrides=S.price_overrides,
            max_g=S.max_g, diet=S.diet)
prev = st.session_state.get("prev")
st.session_state.prev = sol if sol.feasible else prev
names = dict(zip(cat.id.astype(str), cat.nombre))

st.title("Optidieta")
pend = _pending(str(P["mapping"]), P["mapping"].stat().st_mtime) if P["mapping"].exists() else 0
fetched = P["merca"] / "fetched_at.txt"
st.caption(f"{len(cat)} productos de Mercadona (Barcelona)"
           + (f" · precios del {fetched.read_text().strip()[:10]}" if fetched.exists() else "")
           + (f" · ⚠ {pend} productos sin revisar en mapping.csv" if pend else ""))

t_dieta, t_obj, t_cat = st.tabs(["Dieta", "Objetivos", "Catálogo"])

# ---------- Dieta ----------
with t_dieta:
    if not sol.feasible:
        labels = [BY_KEY[k].label for k in sol.blocking]
        st.error("No hay ninguna dieta que cumpla todos los objetivos. Lo impiden: **" + ", ".join(labels) + "**.")
        st.markdown("Puedes desactivar el objetivo que lo bloquea, permitir más gramos por alimento o quitar vetos.")
        cols = st.columns(min(len(sol.blocking), 4) or 1)
        for i, k in enumerate(sol.blocking):
            if cols[i % len(cols)].button(f"Desactivar {BY_KEY[k].label}", key=f"off_{k}"):
                S.constraint_edits.setdefault(k, {})["active"] = False
                save_and_rerun()
    else:
        d = compare(prev, sol) if prev else None
        c1, c2, c3 = st.columns(3)
        c1.metric("Coste al día", eur(sol.cost_day), delta=(eur(d.cost_delta) if d and abs(d.cost_delta) > 0.005 else None),
                  delta_color="inverse")
        c2.metric("Coste a la semana", eur(sol.cost_day * 7))
        c3.metric("Alimentos", len(sol.portions))
        if d and (d.added or d.removed):
            st.caption(" · ".join(filter(None, [
                ("Entra: " + ", ".join(names.get(i, i) for i in d.added)) if d.added else "",
                ("Sale: " + ", ".join(names.get(i, i) for i in d.removed)) if d.removed else ""])))

        info = cat.set_index(cat.id.astype(str))
        por = pd.DataFrame([{
            "Vetar": False, "id": p.id, "Producto": p.nombre, "g/día": round(p.grams),
            "€/día": round(p.cost, 2), "Fuente": "etiqueta" if info.fuente_etiqueta[p.id] == "off" else "BEDCA",
            "Mercadona": info.url[p.id],
        } for p in sol.portions])
        if por.empty:
            st.info("Con los objetivos activos no hace falta comer nada. Activa alguno en la pestaña Objetivos.")
        else:
            ed = st.data_editor(
                por, hide_index=True, use_container_width=True, disabled=[c for c in por.columns if c != "Vetar"],
                column_config={"id": None, "Mercadona": st.column_config.LinkColumn(display_text="ver"),
                               "€/día": st.column_config.NumberColumn(format="%.2f €"),
                               "Vetar": st.column_config.CheckboxColumn(help="Quitar este producto de la dieta")},
                key="portions")
            vet = ed.loc[ed.Vetar, "id"].tolist()
            if vet:
                S.excluded |= set(vet)
                save_and_rerun()

        st.subheader("Nutrientes")
        kcal = sol.totals["energia_kcal"].value if "energia_kcal" in sol.totals else 0
        rows = []
        for c in constraints:
            t = sol.totals.get(c.key)
            if t is None:
                continue
            if c.kind == "pct_energia":
                val = (c.kcal_por_g or 0) * t.value / kcal * 100 if kcal else 0
                lo, hi, unit = (c.min * 100 if c.min is not None else None), (c.max * 100 if c.max is not None else None), "% E"
            else:
                val, lo, hi, unit = t.value, c.min, c.max, c.unit
            ok = (lo is None or val >= lo - 1e-6) and (hi is None or val <= hi + 1e-6)
            aviso = t.known_fraction < 0.999 or c.key in sol.unverified_max
            estado = "—" if not c.active else ("⚠" if aviso else "✓") if ok else "✗"
            obj = (f"≥ {num(lo)}" if lo is not None else "") + (" · " if lo is not None and hi is not None else "") + (
                f"≤ {num(hi)}" if hi is not None else "")
            rows.append({"": estado, "Nutriente": c.label, "Total": num(val), "Unidad": unit, "Objetivo": obj,
                         "Con dato": f"{t.known_fraction:.0%}"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption("⚠ = parte de los alimentos elegidos no tiene ese dato (cuenta como 0) o un máximo no se puede "
                   "verificar. «Con dato» = % de los gramos con valor conocido. — = objetivo desactivado.")

# ---------- Objetivos ----------
with t_obj:
    st.caption("Valores de referencia EFSA para tu perfil. Los % E son porcentaje de la energía total.")
    base_by = {c.key: c for c in base}
    pct = lambda c, v: None if v is None else (v * 100 if c.kind == "pct_energia" else v)
    odf = pd.DataFrame([{"key": c.key, "Activo": c.active, "Nutriente": c.label, "Unidad": c.unit,
                         "Mínimo": pct(c, c.min), "Máximo": pct(c, c.max), "Fuente": c.fuente} for c in constraints])
    oed = st.data_editor(odf, hide_index=True, use_container_width=True, disabled=["Nutriente", "Unidad", "Fuente"],
                         column_config={"key": None}, key="objetivos")
    if st.button("Volver a los valores EFSA"):
        S.constraint_edits = {}
        save_and_rerun()
    edits = {}
    for r in oed.itertuples():
        b = base_by[r.key]
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

# ---------- Catálogo ----------
with t_cat:
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
        "Fuente": view.fuente_etiqueta.map({"off": "etiqueta", "bedca": "BEDCA"}),
        "BEDCA": view.bedca_nombre, "Mercadona": view.url,
    }).head(500)
    st.caption(f"{len(view)} productos" + (" (se muestran 500)" if len(view) > 500 else ""))
    ced = st.data_editor(
        cdf, hide_index=True, use_container_width=True,
        disabled=[c for c in cdf.columns if c not in ("Vetado", "Mi precio €/100 g")],
        column_config={"id": None, "Mercadona": st.column_config.LinkColumn(display_text="ver"),
                       "Mi precio €/100 g": st.column_config.NumberColumn(min_value=0.01, format="%.3f",
                                                                          help="Vacío = precio de Mercadona")},
        key="catalogo")
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
