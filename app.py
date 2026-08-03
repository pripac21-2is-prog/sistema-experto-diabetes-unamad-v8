from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.config import (
    APP_TITLE,
    APP_VERSION,
    ARCHITECTURE_SYSTEM_PATH,
    ARCHITECTURE_ROLES_PATH,
    ARCHITECTURE_WORKFLOW_PATH,
    DISCLAIMER,
    LOCAL_CSV,
    MODEL_VERSION,
    PUBLIC_NOTICE,
    ROLE_LABELS,
    ROLE_PREFIXES,
    STATUS_LABELS,
)
from src.database import SQLiteRepository, create_repository, rows_to_dataframe
from src.expert_system import evaluate_rules, hybrid_decision
from src.model_service import (
    ModelBundle,
    metrics_dataframe,
    predict_probability,
    train_models_from_bytes,
)
from src.reports import build_official_pdf, build_public_pdf, build_patients_directory_pdf, parse_rules_json
from src.security import normalize_username, validate_password_strength
from src.ui import (
    alert_box,
    apply_styles,
    architecture_cards,
    architecture_diagram,
    hero,
    info_cards,
    institutional_header,
    section,
    sidebar_brand,
    source_note,
    status_card,
    visitor_information_banner,
)

st.set_page_config(
    page_title=f"{APP_TITLE} | UNAMAD",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_styles()


# -----------------------------------------------------------------------------
# Infrastructure
# -----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_repository() -> SQLiteRepository:
    return create_repository()


@st.cache_resource(show_spinner="Entrenando el modelo Random Forest...")
def get_model_bundle(csv_path_text: str, modified_ns: int) -> ModelBundle | None:
    del modified_ns
    path = Path(csv_path_text)
    if not path.exists():
        return None
    return train_models_from_bytes(path.read_bytes(), source_name=path.name)


REPOSITORY = get_repository()
try:
    MODEL_BUNDLE = get_model_bundle(str(LOCAL_CSV), LOCAL_CSV.stat().st_mtime_ns if LOCAL_CSV.exists() else 0)
    MODEL_ERROR: str | None = None
except Exception as exc:  # The rules engine remains available if model training fails.
    MODEL_BUNDLE = None
    MODEL_ERROR = str(exc)

if MODEL_BUNDLE is not None:
    try:
        REPOSITORY.ensure_historical_model_predictions(
            lambda values: predict_probability(MODEL_BUNDLE, values) or 0.0,
            MODEL_BUNDLE.selected.name,
            MODEL_VERSION,
        )
    except Exception:
        # The application remains usable even if historical enrichment fails.
        pass


@st.cache_data(show_spinner=False)
def load_dataset_overview(csv_path_text: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    path = Path(csv_path_text)
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    for column in ["glyhb", "stab.glu", "age", "chol", "hdl", "weight", "height"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "glyhb" in frame.columns:
        frame["grupo_referencia"] = frame["glyhb"].apply(
            lambda value: "HbA1c ≥ 6.5" if pd.notna(value) and float(value) >= 6.5 else "HbA1c < 6.5"
        )
    return frame


def dataset_overview() -> pd.DataFrame:
    return load_dataset_overview(
        str(LOCAL_CSV), LOCAL_CSV.stat().st_mtime_ns if LOCAL_CSV.exists() else 0
    )


def clean_plot(fig: go.Figure, *, height: int = 330) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=18, r=18, t=50, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        font=dict(color="#24495C"),
        title_font=dict(color="#073B5C", size=17),
        legend_title_text="",
    )
    fig.update_xaxes(gridcolor="#E7F1F5", zerolinecolor="#E7F1F5")
    fig.update_yaxes(gridcolor="#E7F1F5", zerolinecolor="#E7F1F5")
    return fig


def render_dataset_statistics() -> None:
    frame = dataset_overview()
    if frame.empty or "grupo_referencia" not in frame.columns:
        st.info("El resumen estadístico se mostrará cuando el archivo diabetes.csv esté disponible.")
        return
    valid = frame.dropna(subset=["glyhb"]).copy()
    counts = valid["grupo_referencia"].value_counts().rename_axis("Grupo").reset_index(name="Registros")
    c1, c2 = st.columns([0.85, 1.15])
    with c1:
        fig = px.pie(
            counts, names="Grupo", values="Registros", hole=.58,
            title="Distribución de la variable objetivo",
            color="Grupo",
            color_discrete_map={"HbA1c < 6.5": "#19A7CE", "HbA1c ≥ 6.5": "#F0A43A"},
        )
        fig.update_traces(textposition="inside", textinfo="percent+value")
        st.plotly_chart(clean_plot(fig), use_container_width=True, config={"displayModeBar": False})
    with c2:
        chart_frame = valid.dropna(subset=["age", "stab.glu"]).copy()
        fig = px.histogram(
            chart_frame, x="age", color="grupo_referencia", nbins=12, barmode="group",
            title="Distribución por edad en el conjunto histórico",
            labels={"age": "Edad", "count": "Registros", "grupo_referencia": "Grupo"},
            color_discrete_map={"HbA1c < 6.5": "#19A7CE", "HbA1c ≥ 6.5": "#F0A43A"},
        )
        st.plotly_chart(clean_plot(fig), use_container_width=True, config={"displayModeBar": False})
    source_note(
        "Las gráficas describen únicamente el archivo histórico incluido en el proyecto. "
        "No representan la prevalencia de diabetes en Puerto Maldonado ni sustituyen estadísticas sanitarias oficiales."
    )


def evaluation_dashboard_charts() -> None:
    evaluations = REPOSITORY.list_evaluations(source="OFFICIAL", limit=50000)
    if not evaluations:
        st.info("Las gráficas operativas aparecerán cuando se registren evaluaciones oficiales.")
        return
    frame = pd.DataFrame(evaluations)
    c1, c2 = st.columns(2)
    with c1:
        alert_counts = frame["alert_level"].value_counts().rename_axis("Alerta").reset_index(name="Casos")
        fig = px.bar(
            alert_counts, x="Alerta", y="Casos", text="Casos", title="Evaluaciones por nivel de alerta",
            color="Alerta", color_discrete_map={"BAJO": "#138A72", "MEDIO": "#D28B00", "ALTO": "#C84646"},
        )
        fig.update_traces(textposition="outside")
        st.plotly_chart(clean_plot(fig, height=315), use_container_width=True, config={"displayModeBar": False})
    with c2:
        status_counts = frame["status"].map(status_label).value_counts().rename_axis("Estado").reset_index(name="Casos")
        fig = px.bar(
            status_counts, x="Casos", y="Estado", orientation="h", text="Casos",
            title="Estado de revisión médica", color_discrete_sequence=["#0B78A8"],
        )
        fig.update_traces(textposition="outside")
        st.plotly_chart(clean_plot(fig, height=315), use_container_width=True, config={"displayModeBar": False})

def historical_cohort_charts() -> None:
    evaluations = REPOSITORY.list_evaluations(source="HISTORICAL_CSV", limit=5000)
    if not evaluations:
        st.info("La cohorte histórica todavía no está disponible.")
        return
    frame = pd.DataFrame(evaluations)
    c1, c2 = st.columns(2)
    with c1:
        counts = frame["alert_level"].value_counts().rename_axis("Alerta").reset_index(name="Casos")
        fig = px.bar(
            counts, x="Alerta", y="Casos", text="Casos",
            title="Cohorte histórica por nivel de alerta",
            color="Alerta", color_discrete_map={"BAJO":"#138A72","MEDIO":"#D28B00","ALTO":"#C84646"},
        )
        fig.update_traces(textposition="outside")
        st.plotly_chart(clean_plot(fig, height=315), use_container_width=True, config={"displayModeBar": False})
    with c2:
        age_frame = frame.copy()
        age_frame["Grupo de edad"] = pd.cut(
            age_frame["age"], bins=[0,29,39,49,59,69,120],
            labels=["≤29","30–39","40–49","50–59","60–69","70+"],
        )
        grouped = age_frame.groupby(["Grupo de edad","alert_level"], observed=True).size().reset_index(name="Casos")
        fig = px.bar(
            grouped, x="Grupo de edad", y="Casos", color="alert_level", barmode="stack",
            title="Alertas históricas por grupo de edad",
            labels={"alert_level":"Alerta"},
            color_discrete_map={"BAJO":"#138A72","MEDIO":"#D28B00","ALTO":"#C84646"},
        )
        st.plotly_chart(clean_plot(fig, height=315), use_container_width=True, config={"displayModeBar": False})
    source_note("Estas gráficas pertenecen al dataset académico. No representan estadísticas sanitarias de Puerto Maldonado.")


if "user" not in st.session_state:
    st.session_state.user = None
if "public_result" not in st.session_state:
    st.session_state.public_result = None
if "official_result_id" not in st.session_state:
    st.session_state.official_result_id = None
if "patient_request_key" not in st.session_state:
    st.session_state.patient_request_key = str(uuid.uuid4())
if "evaluation_request_key" not in st.session_state:
    st.session_state.evaluation_request_key = str(uuid.uuid4())
if "patient_created_id" not in st.session_state:
    st.session_state.patient_created_id = None
if "evaluation_selected_patient_id" not in st.session_state:
    st.session_state.evaluation_selected_patient_id = None


# -----------------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------------
PERU_TZ = ZoneInfo("America/Lima")


def format_datetime_peru(value: Any, *, historical: bool = False) -> str:
    del historical
    if value is None or str(value).strip() in {"", "None", "NaT"}:
        return "Sin fecha"
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return str(value)
    return parsed.tz_convert(PERU_TZ).strftime("%d/%m/%Y %H:%M")


def age_from_birth(value: Any) -> float:
    if not value:
        return 50.0
    try:
        born = pd.to_datetime(value).date()
        today = date.today()
        return float(today.year - born.year - ((today.month, today.day) < (born.month, born.day)))
    except Exception:
        return 50.0


def gender_label(value: str) -> str:
    return "Femenino" if str(value).lower() == "female" else "Masculino"


def frame_label(value: str) -> str:
    return {"small": "Pequeña", "medium": "Mediana", "large": "Grande"}.get(str(value), str(value))


def status_label(value: str) -> str:
    return STATUS_LABELS.get(str(value), str(value))


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    meters = max(float(height_cm) / 100.0, 0.1)
    return float(weight_kg) / (meters * meters)


def evaluate_case(values: dict[str, Any]) -> dict[str, Any]:
    expert = evaluate_rules(values)
    probability = predict_probability(MODEL_BUNDLE, values)
    level, message, probability = hybrid_decision(expert, probability, values)
    return {
        "alert_level": level,
        "rule_score": expert.score,
        "ml_probability": probability,
        "rules": expert.to_dict(),
        "rules_json": json.dumps(expert.to_dict(), ensure_ascii=False),
        "explanation": message,
        "model_name": MODEL_BUNDLE.selected.name if MODEL_BUNDLE else "Solo reglas",
        "model_version": MODEL_VERSION if MODEL_BUNDLE else "REGLAS-V8",
    }


def spanish_weekday(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return "Sin día"
    names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    return names[parsed.tz_convert(PERU_TZ).weekday()]


def patient_age(patient: dict[str, Any], evaluations: list[dict[str, Any]] | None = None) -> int:
    if evaluations:
        try:
            return int(round(float(evaluations[0].get("age", 0))))
        except Exception:
            pass
    return int(round(age_from_birth(patient.get("birth_date"))))


def directory_export_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exported: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["display_created_at"] = format_datetime_peru(row.get("created_at"))
        item["display_age"] = int(round(age_from_birth(row.get("birth_date"))))
        exported.append(item)
    return exported


def pagination(rows: list[dict[str, Any]], key: str, page_size: int = 50) -> tuple[list[dict[str, Any]], int, int]:
    total = len(rows)
    pages = max(1, (total + page_size - 1) // page_size)
    page = st.selectbox(
        "Página", list(range(1, pages + 1)), key=key,
        format_func=lambda value: f"Página {value} de {pages}",
    )
    start = (int(page) - 1) * page_size
    return rows[start:start + page_size], int(page), pages


def body_profile_svg(patient: dict[str, Any], evaluation: dict[str, Any] | None) -> str:
    height = float((evaluation or {}).get("height_cm") or patient.get("height_cm") or 0)
    weight = float((evaluation or {}).get("weight_kg") or patient.get("weight_kg") or 0)
    waist = float((evaluation or {}).get("waist_cm") or 0)
    hip = float((evaluation or {}).get("hip_cm") or 0)
    bmi = calculate_bmi(weight, max(height, 1))
    return f"""
    <div class='panel' style='text-align:center'>
      <h3>Perfil corporal registrado</h3>
      <svg viewBox='0 0 330 410' style='max-width:300px;width:100%' role='img' aria-label='Silueta con medidas del paciente'>
        <defs><linearGradient id='bodyg' x1='0' y1='0' x2='1' y2='1'><stop stop-color='#1A8FC6'/><stop offset='1' stop-color='#0B4B7A'/></linearGradient></defs>
        <circle cx='165' cy='52' r='34' fill='url(#bodyg)'/>
        <path d='M118 100 Q165 78 212 100 L232 215 Q220 245 205 260 L218 386 H178 L165 270 L152 386 H112 L125 260 Q108 240 98 215Z' fill='url(#bodyg)' opacity='.92'/>
        <line x1='75' y1='100' x2='75' y2='386' stroke='#D04343' stroke-width='3'/><line x1='66' y1='100' x2='84' y2='100' stroke='#D04343' stroke-width='3'/><line x1='66' y1='386' x2='84' y2='386' stroke='#D04343' stroke-width='3'/>
        <text x='18' y='240' fill='#17324D' font-size='16' font-family='Arial'>{height:.1f} cm</text>
        <line x1='96' y1='190' x2='234' y2='190' stroke='#F0A43A' stroke-width='4' stroke-dasharray='7 6'/>
        <text x='238' y='196' fill='#17324D' font-size='15' font-family='Arial'>Cintura {waist:.1f} cm</text>
        <line x1='110' y1='235' x2='220' y2='235' stroke='#31A36D' stroke-width='4' stroke-dasharray='7 6'/>
        <text x='224' y='241' fill='#17324D' font-size='15' font-family='Arial'>Cadera {hip:.1f} cm</text>
        <text x='165' y='405' text-anchor='middle' fill='#17324D' font-size='16' font-weight='bold' font-family='Arial'>Peso {weight:.1f} kg · IMC {bmi:.1f}</text>
      </svg>
      <p style='color:#567283;font-size:.8rem'>Representación informativa de las medidas registradas; no es una reconstrucción anatómica.</p>
    </div>
    """


def gauge_figure(value: float, title: str, maximum: float, threshold: float, ranges: list[tuple[float, float, str]]) -> go.Figure:
    steps = [{"range": [a, b], "color": color} for a, b, color in ranges]
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=float(value), title={"text": title},
        gauge={"axis": {"range": [0, maximum]}, "bar": {"color": "#0B64A0"},
               "steps": steps, "threshold": {"line": {"color": "#C84444", "width": 5}, "thickness": .8, "value": threshold}},
    ))
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=55, b=20), paper_bgcolor="rgba(0,0,0,0)")
    return fig


def render_patient_profile(patient: dict[str, Any], evaluations: list[dict[str, Any]]) -> None:
    latest = evaluations[0] if evaluations else None
    height = float(patient.get("height_cm") or (latest or {}).get("height_cm") or 0)
    weight = float(patient.get("weight_kg") or (latest or {}).get("weight_kg") or 0)
    waist = float((latest or {}).get("waist_cm") or 0)
    hip = float((latest or {}).get("hip_cm") or 1)
    bmi = calculate_bmi(weight, max(height, 1))
    gender = str((latest or {}).get("gender") or patient.get("gender") or "female")
    waist_limit = 88.0 if gender == "female" else 102.0
    ratio = waist / max(hip, .1)
    ratio_limit = .85 if gender == "female" else .90

    c1, c2 = st.columns([.78, 1.22])
    with c1:
        st.markdown(body_profile_svg(patient, latest), unsafe_allow_html=True)
    with c2:
        g1, g2 = st.columns(2)
        with g1:
            st.plotly_chart(gauge_figure(bmi, "Índice de masa corporal", 45, 25,
                [(0,18.5,"#DCECF5"),(18.5,25,"#DDF3E8"),(25,30,"#FFF0C9"),(30,45,"#F9D4D4")]), use_container_width=True, config={"displayModeBar":False})
        with g2:
            st.plotly_chart(gauge_figure(waist, "Circunferencia de cintura", 160, waist_limit,
                [(0,waist_limit,"#DDF3E8"),(waist_limit,160,"#F9D4D4")]), use_container_width=True, config={"displayModeBar":False})
        st.caption(f"Relación cintura/cadera: {ratio:.2f} · referencia configurada en el proyecto: {ratio_limit:.2f}")
        if latest:
            m1, m2, m3, m4 = st.columns(4)
            with m1: st.metric("Glucosa", f"{float(latest.get('stab_glu',0)):.0f} mg/dL")
            with m2: st.metric("HbA1c", f"{float(latest.get('glyhb',0)):.1f} %")
            with m3: st.metric("Colesterol", f"{float(latest.get('chol',0)):.0f} mg/dL")
            with m4: st.metric("Alerta", str(latest.get("alert_level") or "—"))

    if len(evaluations) >= 2:
        trend = pd.DataFrame(evaluations).copy()
        trend["Fecha"] = pd.to_datetime(trend["created_at"], errors="coerce", utc=True).dt.tz_convert(PERU_TZ)
        trend = trend.sort_values("Fecha")
        long = trend.melt(id_vars=["Fecha"], value_vars=["stab_glu","glyhb","weight_kg"], var_name="Indicador", value_name="Valor")
        long["Indicador"] = long["Indicador"].map({"stab_glu":"Glucosa", "glyhb":"HbA1c", "weight_kg":"Peso"})
        fig = px.line(long, x="Fecha", y="Valor", color="Indicador", markers=True, title="Evolución de indicadores registrados")
        st.plotly_chart(clean_plot(fig, height=330), use_container_width=True, config={"displayModeBar":False})


def render_rule_evidence(rules: dict[str, Any]) -> None:
    activated = rules.get("activated", []) if isinstance(rules, dict) else []
    favorable = rules.get("favorable", []) if isinstance(rules, dict) else []
    tab1, tab2 = st.tabs([f"Reglas activadas ({len(activated)})", f"Factores sin alerta ({len(favorable)})"])
    with tab1:
        if activated:
            frame = pd.DataFrame(activated)
            frame = frame.rename(columns={
                "code": "Regla", "indicator": "Indicador", "patient_value": "Valor",
                "reference": "Referencia", "points": "Puntos", "explanation": "Explicación",
            })
            st.dataframe(frame[["Regla", "Indicador", "Valor", "Referencia", "Puntos", "Explicación"]], use_container_width=True, hide_index=True)
        else:
            st.success("No se activaron reglas de alerta.")
    with tab2:
        if favorable:
            frame = pd.DataFrame(favorable).rename(columns={
                "code": "Regla", "indicator": "Indicador", "patient_value": "Valor",
                "reference": "Referencia", "explanation": "Explicación",
            })
            st.dataframe(frame[["Regla", "Indicador", "Valor", "Referencia", "Explicación"]], use_container_width=True, hide_index=True)
        else:
            st.info("No existen factores favorables registrados para este caso.")


def render_case_result(evaluation: dict[str, Any], rules: dict[str, Any], *, public: bool) -> None:
    alert_box(
        str(evaluation.get("alert_level", "MEDIO")),
        str(evaluation.get("explanation", "")),
        int(evaluation.get("rule_score", 0)),
        evaluation.get("ml_probability"),
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Glucosa", f"{float(evaluation.get('stab_glu', 0)):.0f} mg/dL")
    with c2:
        st.metric("HbA1c / glyhb", f"{float(evaluation.get('glyhb', 0)):.1f} %")
    with c3:
        st.metric("IMC calculado", f"{calculate_bmi(float(evaluation.get('weight_kg', 0)), float(evaluation.get('height_cm', 1))):.1f}")
    with c4:
        probability = evaluation.get("ml_probability")
        st.metric("Estimación ML", "No disponible" if probability is None else f"{float(probability) * 100:.1f} %")
    render_rule_evidence(rules)
    st.caption(DISCLAIMER)
    if public:
        st.info(PUBLIC_NOTICE)


def patient_display(patient: dict[str, Any]) -> str:
    return f"{patient.get('code')} · {patient.get('last_names')}, {patient.get('first_names')}"


def evaluation_display(evaluation: dict[str, Any]) -> str:
    created = format_datetime_peru(
        evaluation.get("created_at"),
        historical=evaluation.get("source") == "HISTORICAL_CSV",
    )
    return f"{evaluation.get('patient_code')} · {created} · {evaluation.get('alert_level')} · {status_label(str(evaluation.get('status')))}"


def require_role(*roles: str) -> dict[str, Any] | None:
    user = st.session_state.user
    if not user or user.get("role") not in roles:
        st.error("No tiene permiso para acceder a esta sección.")
        return None
    return user


def official_pdf_for(evaluation: dict[str, Any]) -> bytes:
    patient = REPOSITORY.get_patient(str(evaluation["patient_id"])) or {}
    reviews = REPOSITORY.list_reviews(str(evaluation["id"]))
    notes = REPOSITORY.list_patient_notes(str(evaluation["patient_id"]))
    return build_official_pdf(patient, evaluation, parse_rules_json(evaluation.get("rules_json")), reviews, notes)


def show_evaluation_detail(evaluation: dict[str, Any], *, allow_download: bool = True) -> None:
    patient = REPOSITORY.get_patient(str(evaluation["patient_id"])) or {}
    detail_date = format_datetime_peru(
        evaluation.get("created_at"),
        historical=evaluation.get("source") == "HISTORICAL_CSV",
    )
    section(
        "Detalle de la evaluación",
        f"{patient_display(patient)} · {detail_date} · {status_label(str(evaluation.get('status')))}",
    )
    render_case_result(evaluation, parse_rules_json(evaluation.get("rules_json")), public=False)
    st.markdown("#### Variables completas de la evaluación")
    variable_rows = [
        ("Edad", f"{float(evaluation.get('age',0)):.0f} años"),
        ("Sexo", gender_label(str(evaluation.get('gender')))),
        ("Altura", f"{float(evaluation.get('height_cm',0)):.1f} cm"),
        ("Peso", f"{float(evaluation.get('weight_kg',0)):.1f} kg"),
        ("Complexión", frame_label(str(evaluation.get('frame')))),
        ("Colesterol", f"{float(evaluation.get('chol',0)):.1f} mg/dL"),
        ("Glucosa", f"{float(evaluation.get('stab_glu',0)):.1f} mg/dL"),
        ("HDL", f"{float(evaluation.get('hdl',0)):.1f} mg/dL"),
        ("Relación col/HDL", f"{float(evaluation.get('ratio',0)):.2f}"),
        ("HbA1c / glyhb", f"{float(evaluation.get('glyhb',0)):.2f} %"),
        ("PA lectura 1", f"{float(evaluation.get('bp1s',0)):.0f}/{float(evaluation.get('bp1d',0)):.0f} mmHg"),
        ("PA lectura 2", f"{float(evaluation.get('bp2s',0)):.0f}/{float(evaluation.get('bp2d',0)):.0f} mmHg"),
        ("Cintura", f"{float(evaluation.get('waist_cm',0)):.1f} cm"),
        ("Cadera", f"{float(evaluation.get('hip_cm',0)):.1f} cm"),
        ("Tiempo poscomida", f"{float(evaluation.get('time_ppn',0)):.0f} min"),
        ("Ubicación", str(evaluation.get('location_text') or '')),
    ]
    variable_frame = pd.DataFrame(variable_rows, columns=["Variable", "Valor"])
    st.dataframe(variable_frame, use_container_width=True, hide_index=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Registro de enfermería**")
        st.write(evaluation.get("nursing_notes") or "Sin observación adicional.")
        st.caption(f"Registrado por: {evaluation.get('nurse_name') or evaluation.get('nurse_username') or 'Enfermería'}")
    with c2:
        st.markdown("**Última revisión médica**")
        st.write(evaluation.get("last_medical_observation") or "Aún no se registró una revisión médica.")
        conclusion_labels = {
            "NO_CONCLUSION": "Sin conclusión clínica",
            "RISK_DISCARDED": "Riesgo descartado en revisión",
            "REQUIRES_CONFIRMATION": "Requiere prueba de confirmación",
            "CONFIRMED_EXTERNAL": "Confirmado por prueba externa",
            "REFERRED": "Derivado a otro servicio",
        }
        if evaluation.get("last_medical_conclusion"):
            st.caption(f"Conclusión: {conclusion_labels.get(str(evaluation.get('last_medical_conclusion')), evaluation.get('last_medical_conclusion'))}")
        if evaluation.get("last_doctor_name"):
            st.caption(f"Revisado por: {evaluation.get('last_doctor_name')}")
    if evaluation.get("source") == "HISTORICAL_CSV":
        st.caption(
            f"Origen: cohorte histórica diabetes.csv · Calidad del registro: "
            f"{evaluation.get('data_quality') or 'no indicada'} · Código de referencia HIS"
        )
    if allow_download:
        st.download_button(
            "Descargar reporte PDF",
            data=official_pdf_for(evaluation),
            file_name=f"reporte_{evaluation.get('patient_code')}_{str(evaluation.get('created_at'))[:10]}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


# -----------------------------------------------------------------------------
# Authentication UI
# -----------------------------------------------------------------------------
def login_panel(*, sidebar: bool = False) -> None:
    target = st.sidebar if sidebar else st
    key_suffix = "side" if sidebar else "main"
    visible_key = f"show_password_{key_suffix}"
    current_visible = bool(st.session_state.get(visible_key, False))
    monkey_label = "🐵 Ocultar contraseña" if current_visible else "🙈 Mostrar contraseña"
    show_password = target.toggle(monkey_label, key=visible_key)
    with target.form(f"login_form_{key_suffix}"):
        username = st.text_input("Usuario", key=f"username_{key_suffix}", placeholder="Ejemplo: enfermeria1")
        password = st.text_input(
            "Contraseña",
            type="default" if show_password else "password",
            key=f"password_{key_suffix}",
            placeholder="Ingrese su contraseña",
        )
        submitted = st.form_submit_button("Ingresar al sistema", use_container_width=True, type="primary")
    if submitted:
        result = REPOSITORY.authenticate(username, password)
        if result.user:
            st.session_state.user = result.user
            st.session_state.patient_created_id = None
            st.session_state.official_result_id = None
            st.session_state.evaluation_selected_patient_id = None
            target.success(f"Bienvenido, {result.user.get('display_name')}.")
            st.rerun()
        else:
            target.error(result.message)

def logout_button() -> None:
    if not st.session_state.user:
        return
    if st.sidebar.button("Cerrar sesión", use_container_width=True):
        user = st.session_state.user
        REPOSITORY.audit(user, "LOGOUT", "session")
        st.session_state.user = None
        st.session_state.patient_created_id = None
        st.session_state.official_result_id = None
        st.session_state.evaluation_selected_patient_id = None
        st.rerun()


# -----------------------------------------------------------------------------
# Public pages
# -----------------------------------------------------------------------------
def page_home() -> None:
    counts = REPOSITORY.dashboard_counts()
    institutional_header()
    hero(counts)

    section(
        "Atención organizada en una sola plataforma",
        "Consulta pública, registro de pacientes, evaluación híbrida, revisión médica y administración de datos.",
        "Sistema web V8",
    )
    info_cards([
        ("01", "Consulta pública", "Orientación temporal sin crear una ficha dentro de la base operativa del sistema."),
        ("02", "Enfermería", "Registra pacientes, completa variables clínicas y genera resultados descargables."),
        ("03", "Medicina", "Consulta alertas por fecha, actualiza fichas y registra seguimiento o derivación."),
        ("04", "Administración", "Gestiona usuarios, auditoría, exportaciones, respaldo y calidad del modelo."),
    ])

    c1, c2, c3, c4 = st.columns(4)
    with c1: status_card("Pacientes en el sistema", str(counts.get("patients", 0)), "Cohorte histórica y nuevos registros.")
    with c2: status_card("Evaluaciones disponibles", str(counts.get("evaluations", 0)), "Resultados consultables por el personal.")
    with c3: status_card("Pendientes médicos", str(counts.get("pending", 0)), "Alertas medias y altas por revisar.")
    with c4: status_card("Usuarios activos", str(counts.get("users", 0)), "Enfermería, medicina y administración.")

    section("Panorama del conjunto de datos", "Distribución de los registros utilizados durante el trabajo en JupyterLab.", "Analítica")
    render_dataset_statistics()
    source_note(DISCLAIMER)

def page_public_consultation() -> None:
    institutional_header()
    section(
        "Consulta pública de orientación",
        "Complete las variables disponibles para obtener una alerta temporal y un reporte PDF.",
        "Evaluación sin registro",
    )
    info_cards([
        ("01", "Datos temporales", "La información desaparece al finalizar la sesión y no crea un paciente."),
        ("02", "Resultado explicable", "Se muestran nivel de alerta, reglas activadas y estimación del modelo."),
        ("03", "Reporte PDF", "El visitante puede descargar un resumen de la consulta."),
        ("04", "Uso responsable", "La salida es orientativa y debe interpretarse con apoyo profesional."),
    ])
    st.markdown(f'<div class="notice">{PUBLIC_NOTICE}</div>', unsafe_allow_html=True)
    with st.form("public_consultation_form"):
        st.markdown("#### Datos generales")
        c1, c2 = st.columns(2)
        with c1:
            age = st.number_input("Edad", min_value=18, max_value=100, value=45)
            height_cm = st.number_input("Altura (cm)", min_value=120.0, max_value=220.0, value=165.0, step=0.5)
        with c2:
            gender_label_input = st.selectbox("Sexo", ["Femenino", "Masculino"])
            weight_kg = st.number_input("Peso (kg)", min_value=30.0, max_value=250.0, value=70.0, step=0.5)

        st.markdown("#### Variables principales")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            glucose = st.number_input("Glucosa (mg/dL)", min_value=40.0, max_value=500.0, value=95.0, step=1.0)
        with c2:
            glyhb = st.number_input("HbA1c / glyhb (%)", min_value=3.0, max_value=20.0, value=5.4, step=0.1)
        with c3:
            chol = st.number_input("Colesterol total (mg/dL)", min_value=70.0, max_value=600.0, value=190.0, step=1.0)
        with c4:
            hdl = st.number_input("HDL (mg/dL)", min_value=10.0, max_value=150.0, value=50.0, step=1.0)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            bp1s = st.number_input("Presión sistólica", min_value=70.0, max_value=260.0, value=120.0, step=1.0)
        with c2:
            bp1d = st.number_input("Presión diastólica", min_value=40.0, max_value=160.0, value=75.0, step=1.0)
        with c3:
            waist_cm = st.number_input("Cintura (cm)", min_value=45.0, max_value=200.0, value=85.0, step=0.5)
        with c4:
            hip_cm = st.number_input("Cadera (cm)", min_value=45.0, max_value=220.0, value=98.0, step=0.5)

        with st.expander("Datos complementarios para el modelo"):
            c1, c2 = st.columns(2)
            with c1:
                frame_text = st.selectbox("Complexión", ["Pequeña", "Mediana", "Grande"], index=1)
            with c2:
                time_ppn = st.number_input("Minutos desde la última comida", min_value=0.0, max_value=1440.0, value=120.0, step=10.0)
            st.caption("En la consulta pública la segunda lectura de presión se toma igual a la primera. Enfermería registra ambas lecturas por separado.")

        consent = st.checkbox("Comprendo que es una orientación inicial y no un diagnóstico.")
        submitted = st.form_submit_button("Evaluar riesgo", type="primary", use_container_width=True)

    if submitted:
        if not consent:
            st.error("Debe aceptar la advertencia para realizar la consulta.")
        elif hdl <= 0 or hip_cm <= 0:
            st.error("HDL y cadera deben ser mayores que cero.")
        else:
            gender = "female" if gender_label_input == "Femenino" else "male"
            frame = {"Pequeña": "small", "Mediana": "medium", "Grande": "large"}[frame_text]
            values = {
                "age": float(age), "gender": gender, "height_cm": float(height_cm),
                "weight_kg": float(weight_kg), "frame": frame, "chol": float(chol),
                "stab_glu": float(glucose), "hdl": float(hdl), "ratio": float(chol / hdl),
                "glyhb": float(glyhb), "bp1s": float(bp1s), "bp1d": float(bp1d),
                "bp2s": float(bp1s), "bp2d": float(bp1d), "waist_cm": float(waist_cm),
                "hip_cm": float(hip_cm), "time_ppn": float(time_ppn),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            result = evaluate_case(values)
            st.session_state.public_result = {**values, **result}

    result = st.session_state.public_result
    if result:
        section("Resultado de la consulta")
        render_case_result(result, result["rules"], public=True)
        pdf = build_public_pdf(result, result["rules"])
        st.download_button(
            "Descargar consulta en PDF",
            data=pdf,
            file_name=f"consulta_diabetes_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


def page_information() -> None:
    institutional_header()
    section(
        "Centro de información sobre diabetes y el sistema",
        "Contenido educativo, variables observadas y explicación del funcionamiento del sistema.",
        "Información para el visitante",
    )

    visitor_information_banner()

    info_cards([
        ("A", "Glucosa", "Concentración de azúcar en sangre registrada en la evaluación."),
        ("B", "HbA1c", "Indicador relacionado con el promedio de glucosa de un periodo anterior."),
        ("C", "Presión y lípidos", "Factores complementarios considerados por las reglas del sistema."),
        ("D", "Medidas corporales", "Peso, talla, cintura y cadera ayudan a contextualizar el caso."),
    ])

    variable_map = pd.DataFrame([
        ("id", "Metadato", "Identificador del registro histórico"),
        ("location", "Metadato", "Lugar registrado en el dataset original"),
        ("glyhb", "Referencia + reglas", "Construye la clase objetivo; no entra como predictor para evitar fuga"),
        ("chol, stab.glu, hdl, ratio", "Predictores", "Perfil glucémico y lipídico"),
        ("age, gender, height, weight, frame", "Predictores", "Datos demográficos y antropométricos"),
        ("bp.1s, bp.1d, bp.2s, bp.2d", "Predictores", "Dos lecturas de presión arterial"),
        ("waist, hip, time.ppn", "Predictores", "Medidas corporales y tiempo poscomida"),
    ], columns=["Columnas", "Uso", "Descripción"])
    with st.expander("Ver cómo se utilizan las 19 columnas del diabetes.csv", expanded=False):
        st.dataframe(variable_map, use_container_width=True, hide_index=True)

    tab1, tab2, tab3, tab4 = st.tabs(["Diabetes", "Tamizaje y triaje", "Cómo razona", "Preguntas frecuentes"])
    with tab1:
        c1, c2 = st.columns([1.15, .85])
        with c1:
            st.markdown("""
            ### Concepto general
            La diabetes es una enfermedad metabólica crónica relacionada con niveles elevados de glucosa en la sangre. El sistema analiza variables incluidas en el proyecto para producir una **alerta orientativa**, no un diagnóstico.

            La confirmación corresponde a profesionales de salud y pruebas clínicas. Una alerta baja tampoco garantiza ausencia total de riesgo.

            ### Variables utilizadas por el sistema
            - Glucosa y HbA1c.
            - Colesterol total, HDL y relación colesterol/HDL.
            - Presión arterial.
            - Edad, peso, talla, cintura, cadera y complexión.
            """)
        with c2:
            st.markdown("""
            <div class="panel">
              <h3>Alcance de la herramienta</h3>
              <p>La salida se presenta como nivel de alerta bajo, medio o alto, acompañada de las reglas que se activaron y de la estimación del modelo.</p>
              <p>El objetivo es apoyar una evaluación inicial y facilitar una revisión posterior por personal autorizado.</p>
            </div>
            """, unsafe_allow_html=True)
    with tab2:
        st.markdown("""
        ### Diferencia entre tamizaje y triaje
        **Tamizaje** es una evaluación inicial orientada a identificar personas que podrían necesitar una revisión más completa.

        **Triaje** es el proceso inicial de atención en un establecimiento de salud, donde se recopilan signos, antecedentes y motivo de consulta para organizar la atención.

        En este proyecto, enfermería puede utilizar el sistema durante la atención inicial para apoyar un tamizaje de riesgo de diabetes.
        """)
        architecture_cards([
            ("01", "Recepción", "Se identifica al paciente y se registran datos básicos."),
            ("02", "Medición", "Se incorporan variables clínicas y medidas corporales."),
            ("03", "Evaluación", "El motor híbrido procesa reglas y modelo predictivo."),
            ("04", "Revisión", "El médico consulta el caso y documenta observaciones."),
            ("05", "Seguimiento", "El historial permite comparar evaluaciones posteriores."),
        ])
    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("""
            ### Sistema experto
            Las reglas fueron definidas previamente. No aprenden solas ni cambian al ingresar un paciente. Cada regla explica qué indicador activó una alerta y cuántos puntos aportó.

            Ejemplo conceptual: **si** ciertos valores superan los rangos establecidos por el proyecto, **entonces** aumenta el nivel de alerta.
            """)
        with c2:
            st.markdown("""
            ### Random Forest
            El modelo fue entrenado previamente con `diabetes.csv`. Al recibir un nuevo caso utiliza `predict_proba()` para estimar una probabilidad.

            **No vuelve a entrenarse con cada paciente.** Un reentrenamiento futuro requeriría datos anonimizados, validados y un proceso controlado de evaluación.
            """)
        source_note("El sistema combina explicación basada en reglas y estimación estadística. Ninguno de los dos componentes reemplaza el juicio clínico.")
    with tab4:
        for question, answer in [
            ("¿La consulta pública se guarda?", "No. Es temporal y no forma parte de la base oficial."),
            ("¿El paciente necesita usuario?", "No. Solo el personal autorizado inicia sesión."),
            ("¿Quién registra pacientes oficiales?", "Enfermería."),
            ("¿Qué hace el médico?", "Revisa evaluaciones, registra observaciones y actualiza el estado del caso."),
            ("¿Qué hace el administrador?", "Crea cuentas, controla accesos, revisa auditoría y descarga respaldos."),
            ("¿El sistema diagnostica diabetes?", "No. Genera una alerta de apoyo al tamizaje."),
        ]:
            with st.expander(question):
                st.write(answer)

    source_note("Fuentes informativas de referencia: Organización Panamericana de la Salud e International Diabetes Federation. El contenido se presenta con fines educativos.")
    st.markdown("[OPS/OMS — Diabetes](https://www.paho.org/es/temas/diabetes) · [International Diabetes Federation](https://idf.org/es/)")


def page_architecture() -> None:
    institutional_header()
    section("Arquitectura del sistema", "Diagramas completos del desarrollo, los permisos y el funcionamiento por roles.", "Diseño funcional")
    st.markdown("### 1. Arquitectura general del sistema")
    st.image(str(ARCHITECTURE_SYSTEM_PATH), use_container_width=True)
    st.markdown("### 2. Matriz de permisos por rol")
    st.image(str(ARCHITECTURE_ROLES_PATH), use_container_width=True)
    st.markdown("### 3. Funcionamiento de enfermería, medicina y administración")
    st.image(str(ARCHITECTURE_WORKFLOW_PATH), use_container_width=True)

def page_project() -> None:
    institutional_header()
    section("Acerca del proyecto", "Del análisis en JupyterLab a una plataforma web operativa.", "UNAMAD · 2026")
    c1, c2 = st.columns([1.05, .95])
    with c1:
        st.markdown(f"""
        ### {APP_TITLE}
        **Universidad Nacional Amazónica de Madre de Dios**  
        Escuela Profesional de Ingeniería de Sistemas e Informática  
        Curso: Sistemas Expertos

        **Autores**  
        Poldy Raúl Ripa Challco  
        Frank Hiobert Palomino Usca

        **Versión:** {APP_VERSION}  
        **Lugar:** Puerto Maldonado, Madre de Dios · 2026
        """)
    with c2:
        st.markdown("""
        <div class="panel">
          <h3>Propósito</h3>
          <p>Convertir el análisis del archivo diabetes.csv en una aplicación que reciba datos, explique la alerta, conserve historiales, permita revisión médica y produzca reportes.</p>
          <p>La plataforma integra investigación, sistema experto, aprendizaje automático, base de datos, seguridad y control de accesos.</p>
        </div>
        """, unsafe_allow_html=True)

    section("Trabajo realizado en JupyterLab", "Etapas de investigación que dieron origen al sistema web.", "Investigación")
    architecture_cards([
        ("01", "Carga del CSV", "Revisión de 403 registros y 19 columnas."),
        ("02", "Limpieza", "Conversión de tipos, análisis de faltantes e imputación."),
        ("03", "Exploración", "Gráficos de glucosa, HbA1c, edad, lípidos y presión."),
        ("04", "Comparación", "Evaluación de Random Forest y regresión logística."),
        ("05", "Validación", "Matriz de confusión, accuracy, precision, recall, F1 y ROC-AUC."),
    ])
    if MODEL_BUNDLE is not None:
        st.dataframe(metrics_dataframe(MODEL_BUNDLE).style.format({
            "Accuracy":"{:.3f}","Precision":"{:.3f}","Recall":"{:.3f}","F1":"{:.3f}","ROC-AUC":"{:.3f}","F1 validación cruzada":"{:.3f}"
        }), use_container_width=True, hide_index=True)
    render_dataset_statistics()
    source_note(DISCLAIMER)

def page_login() -> None:
    institutional_header()
    section("Acceso seguro del personal", "Ingrese con la cuenta asignada por administración. No se requiere correo electrónico.", "Zona privada")
    c1, c2 = st.columns([.92, 1.08])
    with c1:
        st.markdown("""
        <div class="login-intro">
          <h2>Acceso por funciones</h2>
          <p>Las cuentas están separadas por rol y cada panel valida los permisos antes de mostrar o modificar información.</p>
          <div class="login-list">
            <div class="login-item"><b>Enfermería:</b> registra pacientes y evaluaciones.</div>
            <div class="login-item"><b>Médico:</b> revisa casos y documenta seguimiento.</div>
            <div class="login-item"><b>Administrador:</b> crea cuentas, controla accesos y respaldos.</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        login_panel(sidebar=False)
    source_note("El visitante no necesita cuenta. Las credenciales de demostración se entregan fuera de la página pública.")


def page_nurse_dashboard() -> None:
    user = require_role("nurse")
    if not user:
        return
    counts = REPOSITORY.dashboard_counts()
    institutional_header()
    section("Panel de enfermería", "Consulte los pacientes existentes, registre nuevos casos y complete evaluaciones clínicas.")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Pacientes en el sistema", counts["patients"])
    with c2: st.metric("Evaluaciones", counts["evaluations"])
    with c3: st.metric("Pendientes médicos", counts["pending"])
    with c4: st.metric("Alertas altas", counts["high"])

    section("Pacientes registrados por fecha", "Se muestran 50 registros por página, ordenados desde la fecha más reciente.")
    all_rows = REPOSITORY.list_patients(limit=100000)
    current, page, pages = pagination(all_rows, "nurse_dashboard_page", 50)
    frame = pd.DataFrame(current)
    if not frame.empty:
        show = frame[["code","first_names","last_names","created_at","source","evaluation_count","last_alert"]].copy()
        show["Día"] = [spanish_weekday(value) for value in show["created_at"]]
        show["created_at"] = [format_datetime_peru(value) for value in show["created_at"]]
        show["source"] = show["source"].map({"OFFICIAL":"Registro web","HISTORICAL_CSV":"CSV histórico"})
        show["last_alert"] = show["last_alert"].fillna("Sin evaluación")
        show.columns = ["Código","Nombres","Apellidos","Fecha","Origen","Evaluaciones","Última alerta","Día"]
        show = show[["Código","Nombres","Apellidos","Fecha","Día","Origen","Evaluaciones","Última alerta"]]
        st.dataframe(show, use_container_width=True, hide_index=True, height=520)
        st.caption(f"Página {page} de {pages} · Total: {len(all_rows)} pacientes")

def page_register_patient() -> None:
    user = require_role("nurse")
    if not user:
        return
    institutional_header()
    section("Registrar paciente oficial", "Cree un registro único y verificable antes de ingresar una evaluación.")

    created_id = st.session_state.patient_created_id
    if created_id:
        patient = REPOSITORY.get_patient(str(created_id))
        if patient:
            st.success(f"Paciente registrado correctamente con código {patient['code']}.")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Código", patient["code"])
            with c2:
                st.metric("Paciente", f"{patient['first_names']} {patient['last_names']}")
            with c3:
                st.metric("Estado", "Activo" if patient.get("active") else "Inactivo")
            st.info("El formulario quedó bloqueado después del registro para evitar duplicados. Use el botón siguiente para crear otra ficha.")
            if st.button("Registrar otro paciente", type="primary", use_container_width=True):
                st.session_state.patient_created_id = None
                st.session_state.patient_request_key = str(uuid.uuid4())
                st.rerun()
            return
        st.session_state.patient_created_id = None

    request_key = st.session_state.patient_request_key
    with st.form("patient_registration_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            first_names = st.text_input("Nombres*", max_chars=80)
        with c2:
            last_names = st.text_input("Apellidos*", max_chars=100)
        with c3:
            document = st.text_input("Documento opcional", max_chars=25, help="Si se registra, no puede repetirse.")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            gender_text = st.selectbox("Sexo*", ["Femenino", "Masculino"])
        with c2:
            birth_date = st.date_input(
                "Fecha de nacimiento",
                value=date(1985, 1, 1),
                min_value=date(1920, 1, 1),
                max_value=date.today(),
            )
        with c3:
            height_cm = st.number_input("Altura (cm)*", min_value=100.0, max_value=230.0, value=165.0, step=0.5)
        with c4:
            weight_kg = st.number_input("Peso (kg)*", min_value=20.0, max_value=300.0, value=70.0, step=0.5)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            frame_text = st.selectbox("Complexión*", ["Pequeña", "Mediana", "Grande"], index=1)
        with c2:
            department = st.text_input("Departamento", value="Madre de Dios")
        with c3:
            province = st.text_input("Provincia", value="Tambopata")
        with c4:
            district = st.text_input("Distrito", value="Tambopata")
        c1, c2 = st.columns(2)
        with c1:
            city = st.text_input("Ciudad", value="Puerto Maldonado")
        with c2:
            phone = st.text_input("Teléfono opcional", max_chars=25)
        notes = st.text_area("Observaciones", max_chars=1500)
        submitted = st.form_submit_button("Registrar paciente", type="primary", use_container_width=True)

    if submitted:
        if not first_names.strip() or not last_names.strip():
            st.error("Nombres y apellidos son obligatorios.")
            return
        payload = {
            "document_number": document.strip() or None,
            "first_names": first_names.strip(),
            "last_names": last_names.strip(),
            "gender": "female" if gender_text == "Femenino" else "male",
            "birth_date": birth_date,
            "phone": phone.strip(),
            "department": department.strip() or "Madre de Dios",
            "province": province.strip() or "Tambopata",
            "district": district.strip() or "Tambopata",
            "city": city.strip() or "Puerto Maldonado",
            "frame": {"Pequeña": "small", "Mediana": "medium", "Grande": "large"}[frame_text],
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "notes": notes.strip(),
            "request_key": request_key,
        }
        try:
            created = REPOSITORY.create_patient(payload, user)
            st.session_state.patient_created_id = created["id"]
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def official_values_form(patient: dict[str, Any], key_suffix: str) -> tuple[dict[str, Any], str, bool]:
    age = age_from_birth(patient.get("birth_date"))
    location_text = f"{patient.get('city')}, {patient.get('district')}, {patient.get('province')}, {patient.get('department')}"
    st.info(f"Paciente: **{patient_display(patient)}** · {gender_label(str(patient.get('gender')))} · {age:.0f} años · {location_text}")
    st.markdown(
        '<div class="notice"><b>Correspondencia con las 19 columnas:</b> <code>id</code> y <code>location</code> son metadatos; <code>glyhb</code> es la referencia del estudio; las otras 16 variables forman la entrada predictiva. Edad, sexo, talla, peso y complexión provienen del perfil del paciente.</div>',
        unsafe_allow_html=True,
    )
    st.markdown("#### Perfil antropométrico y contexto")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        height_cm = st.number_input(
            "Altura (cm)*", min_value=100.0, max_value=230.0,
            value=float(patient["height_cm"]), step=0.5,
            key=f"official_height_{key_suffix}",
        )
    with c2:
        weight_kg = st.number_input(
            "Peso (kg)*", min_value=20.0, max_value=300.0,
            value=float(patient["weight_kg"]), step=0.5,
            key=f"official_weight_{key_suffix}",
        )
    with c3:
        frame_text = st.selectbox(
            "Complexión*", ["Pequeña", "Mediana", "Grande"],
            index={"small": 0, "medium": 1, "large": 2}.get(str(patient.get("frame")), 1),
            key=f"official_frame_{key_suffix}",
        )
    with c4:
        st.metric("IMC calculado", f"{calculate_bmi(weight_kg, height_cm):.1f}")

    st.markdown("#### Glucosa y perfil lipídico")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        glucose = st.number_input("Glucosa estable (mg/dL)*", 30.0, 700.0, 95.0, 1.0, key=f"official_glucose_{key_suffix}")
    with c2:
        glyhb = st.number_input("HbA1c / glyhb (%)*", 2.0, 25.0, 5.4, 0.1, key=f"official_glyhb_{key_suffix}")
    with c3:
        chol = st.number_input("Colesterol total (mg/dL)*", 40.0, 800.0, 190.0, 1.0, key=f"official_chol_{key_suffix}")
    with c4:
        hdl = st.number_input("HDL (mg/dL)*", 5.0, 250.0, 50.0, 1.0, key=f"official_hdl_{key_suffix}")
    st.caption(f"Relación colesterol/HDL calculada automáticamente: {chol / max(hdl, .01):.2f}")

    st.markdown("#### Presión arterial")
    st.caption("El conjunto de datos incluye dos lecturas. Registrar ambas permite distinguir una medición aislada de un valor persistente.")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        bp1s = st.number_input("Primera lectura · sistólica*", 50.0, 300.0, 120.0, 1.0, key=f"official_bp1s_{key_suffix}")
    with c2:
        bp1d = st.number_input("Primera lectura · diastólica*", 30.0, 200.0, 75.0, 1.0, key=f"official_bp1d_{key_suffix}")
    with c3:
        bp2s = st.number_input("Segunda lectura · sistólica*", 50.0, 300.0, 120.0, 1.0, key=f"official_bp2s_{key_suffix}")
    with c4:
        bp2d = st.number_input("Segunda lectura · diastólica*", 30.0, 200.0, 75.0, 1.0, key=f"official_bp2d_{key_suffix}")

    st.markdown("#### Medidas corporales y tiempo posprandial")
    c1, c2, c3 = st.columns(3)
    with c1:
        waist_cm = st.number_input("Cintura (cm)*", 30.0, 250.0, 85.0, 0.5, key=f"official_waist_{key_suffix}")
    with c2:
        hip_cm = st.number_input("Cadera (cm)*", 30.0, 250.0, 98.0, 0.5, key=f"official_hip_{key_suffix}")
    with c3:
        time_ppn = st.number_input("Minutos desde la última comida*", 0.0, 1440.0, 120.0, 10.0, key=f"official_time_{key_suffix}")
    nursing_notes = st.text_area("Observación de enfermería", max_chars=2000, key=f"official_notes_{key_suffix}")
    values = {
        "patient_id": patient["id"],
        "location_text": location_text,
        "age": age,
        "gender": patient["gender"],
        "height_cm": float(height_cm),
        "weight_kg": float(weight_kg),
        "frame": {"Pequeña": "small", "Mediana": "medium", "Grande": "large"}[frame_text],
        "chol": float(chol),
        "stab_glu": float(glucose),
        "hdl": float(hdl),
        "ratio": float(chol / max(hdl, 0.01)),
        "glyhb": float(glyhb),
        "bp1s": float(bp1s),
        "bp1d": float(bp1d),
        "bp2s": float(bp2s),
        "bp2d": float(bp2d),
        "waist_cm": float(waist_cm),
        "hip_cm": float(hip_cm),
        "time_ppn": float(time_ppn),
    }
    submitted = st.form_submit_button("Guardar evaluación oficial", type="primary", use_container_width=True)
    return values, nursing_notes, submitted


def page_new_evaluation() -> None:
    user = require_role("nurse")
    if not user:
        return
    institutional_header()
    section("Nueva evaluación oficial", "Las alertas medias y altas se envían a revisión médica; las bajas permanecen en el historial.")

    if st.session_state.official_result_id:
        evaluation = REPOSITORY.get_evaluation(str(st.session_state.official_result_id))
        if evaluation:
            st.success("La evaluación fue guardada correctamente.")
            show_evaluation_detail(evaluation)
            if st.button("Registrar otra evaluación", type="primary", use_container_width=True):
                st.session_state.official_result_id = None
                st.session_state.evaluation_request_key = str(uuid.uuid4())
                st.session_state.evaluation_selected_patient_id = None
                st.rerun()
            return
        st.session_state.official_result_id = None

    search = st.text_input("Buscar paciente oficial", placeholder="Código, documento, nombre o apellido")
    patients = REPOSITORY.list_patients(search=search, source="OFFICIAL", limit=100)
    if not patients:
        st.warning("No se encontraron pacientes oficiales. Registre uno primero o cambie la búsqueda.")
        return
    options = {patient_display(item): item for item in patients}
    selected_label = st.selectbox("Seleccione paciente", list(options))
    patient = options[selected_label]

    if st.session_state.evaluation_selected_patient_id != patient["id"]:
        st.session_state.evaluation_selected_patient_id = patient["id"]
        st.session_state.evaluation_request_key = str(uuid.uuid4())

    request_key = st.session_state.evaluation_request_key
    suffix = str(patient["id"]).replace("-", "")[-10:]
    with st.form(f"official_evaluation_form_{suffix}", clear_on_submit=False):
        values, nursing_notes, submitted = official_values_form(patient, suffix)
    if submitted:
        try:
            result = evaluate_case(values)
            payload = {
                **values,
                **{
                    key: result[key]
                    for key in [
                        "alert_level", "rule_score", "ml_probability", "model_name",
                        "model_version", "rules_json", "explanation",
                    ]
                },
                "nursing_notes": nursing_notes.strip(),
                "request_key": request_key,
            }
            created = REPOSITORY.create_evaluation(payload, user)
            st.session_state.official_result_id = created["id"]
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def page_patients_history() -> None:
    user = require_role("nurse", "doctor")
    if not user:
        return
    institutional_header()
    section("Directorio de pacientes", "Busque una persona, abra su ficha visual, consulte evaluaciones y descargue información.")
    c1, c2 = st.columns([1.4, .6])
    with c1:
        search = st.text_input("Buscar paciente", placeholder="Código, documento, nombre o apellido")
    with c2:
        source_text = st.selectbox("Origen", ["Todos", "Registro web", "CSV histórico"])
    source = {"Registro web":"OFFICIAL", "CSV histórico":"HISTORICAL_CSV"}.get(source_text)
    all_patients = REPOSITORY.list_patients(search=search, source=source, limit=100000)
    if not all_patients:
        st.info("No se encontraron pacientes.")
        return
    current, page, pages = pagination(all_patients, f"patient_directory_page_{user['role']}", 50)
    frame = pd.DataFrame(current)
    show = frame[["code","first_names","last_names","created_at","source","evaluation_count","last_alert"]].copy()
    show["Día"] = [spanish_weekday(value) for value in show["created_at"]]
    show["created_at"] = [format_datetime_peru(value) for value in show["created_at"]]
    show["source"] = show["source"].map({"OFFICIAL":"Registro web","HISTORICAL_CSV":"CSV histórico"})
    show["last_alert"] = show["last_alert"].fillna("Sin evaluación")
    show.columns = ["Código","Nombres","Apellidos","Fecha","Origen","Evaluaciones","Última alerta","Día"]
    show = show[["Código","Nombres","Apellidos","Fecha","Día","Origen","Evaluaciones","Última alerta"]]
    st.dataframe(show, use_container_width=True, hide_index=True, height=520)
    st.caption(f"Página {page} de {pages} · {len(all_patients)} coincidencias")

    export_rows = directory_export_rows(all_patients)
    export_frame = pd.DataFrame(export_rows)
    ec1, ec2 = st.columns(2)
    with ec1:
        st.download_button("Descargar directorio CSV", export_frame.to_csv(index=False).encode("utf-8-sig"), "directorio_pacientes.csv", "text/csv", use_container_width=True)
    with ec2:
        st.download_button("Descargar directorio PDF", build_patients_directory_pdf(export_rows), "directorio_pacientes.pdf", "application/pdf", use_container_width=True)

    options = {patient_display(item): item for item in current}
    patient = options[st.selectbox("Abrir ficha del paciente", list(options))]
    evaluations = REPOSITORY.list_evaluations(patient_id=patient["id"], limit=500)
    notes = REPOSITORY.list_patient_notes(patient["id"])
    section("Ficha detallada", f"{patient_display(patient)} · Registrado el {format_datetime_peru(patient.get('created_at'))} ({spanish_weekday(patient.get('created_at'))})")
    d1, d2, d3 = st.columns(3)
    with d1: st.metric("Fecha de registro", format_datetime_peru(patient.get("created_at")))
    with d2: st.metric("Última actualización", format_datetime_peru(patient.get("updated_at")))
    with d3: st.metric("Origen", "Registro web" if patient.get("source") == "OFFICIAL" else "Cohorte histórica")
    render_patient_profile(patient, evaluations)

    if evaluations:
        st.markdown("### Evaluaciones del paciente")
        eval_frame = pd.DataFrame(evaluations)
        timeline = eval_frame[["created_at","alert_level","status","source","last_doctor_name"]].copy()
        timeline["Día"] = [spanish_weekday(value) for value in timeline["created_at"]]
        timeline["created_at"] = [format_datetime_peru(value) for value in timeline["created_at"]]
        timeline["status"] = timeline["status"].map(status_label)
        timeline["source"] = timeline["source"].map({"OFFICIAL":"Registro web","HISTORICAL_CSV":"CSV histórico"})
        timeline["last_doctor_name"] = timeline["last_doctor_name"].fillna("Sin revisión")
        timeline.columns = ["Fecha","Alerta","Estado","Origen","Último médico","Día"]
        st.dataframe(timeline[["Fecha","Día","Alerta","Estado","Origen","Último médico"]], use_container_width=True, hide_index=True)
        eval_options = {evaluation_display(item): item for item in evaluations}
        selected_eval = eval_options[st.selectbox("Abrir resultado", list(eval_options), key=f"dir_eval_{patient['id']}")]
        show_evaluation_detail(selected_eval)
    else:
        st.info("Este paciente todavía no tiene una evaluación disponible.")

    if notes:
        st.markdown("### Notas médicas y derivaciones")
        note_frame = pd.DataFrame(notes)
        note_frame["created_at"] = [format_datetime_peru(value) for value in note_frame["created_at"]]
        note_frame = note_frame[["created_at","doctor_name","note_type","referral_area","observation"]]
        note_frame.columns = ["Fecha","Médico","Tipo","Área de derivación","Observación"]
        st.dataframe(note_frame, use_container_width=True, hide_index=True)

    can_edit = user.get("role") == "doctor" or (user.get("role") == "nurse" and patient.get("source") == "OFFICIAL")
    if can_edit:
        with st.expander("Actualizar ficha del paciente"):
            try:
                birth_default = pd.to_datetime(patient.get("birth_date"), errors="coerce").date()
                if pd.isna(pd.to_datetime(patient.get("birth_date"), errors="coerce")):
                    birth_default = date(1980, 1, 1)
            except Exception:
                birth_default = date(1980, 1, 1)
            with st.form(f"edit_patient_{patient['id']}"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    first_names = st.text_input("Nombres", value=str(patient.get("first_names", "")))
                    document_number = st.text_input("Documento", value=str(patient.get("document_number") or ""), max_chars=25)
                    gender_text = st.selectbox(
                        "Sexo", ["Femenino", "Masculino"],
                        index=0 if str(patient.get("gender")) == "female" else 1,
                    )
                with c2:
                    last_names = st.text_input("Apellidos", value=str(patient.get("last_names", "")))
                    phone = st.text_input("Teléfono", value=str(patient.get("phone") or ""), max_chars=25)
                    birth_date_value = st.date_input("Fecha de nacimiento", value=birth_default, max_value=date.today())
                with c3:
                    frame_text = st.selectbox(
                        "Complexión", ["Pequeña", "Mediana", "Grande"],
                        index={"small": 0, "medium": 1, "large": 2}.get(str(patient.get("frame")), 1),
                    )
                    height = st.number_input("Altura (cm)", 100.0, 230.0, float(patient.get("height_cm") or 165.0), step=0.5)
                    weight = st.number_input("Peso (kg)", 20.0, 300.0, float(patient.get("weight_kg") or 70.0), step=0.5)
                l1, l2, l3, l4 = st.columns(4)
                with l1: department = st.text_input("Departamento", value=str(patient.get("department") or "Madre de Dios"))
                with l2: province = st.text_input("Provincia", value=str(patient.get("province") or "Tambopata"))
                with l3: district = st.text_input("Distrito", value=str(patient.get("district") or "Tambopata"))
                with l4: city = st.text_input("Ciudad", value=str(patient.get("city") or "Puerto Maldonado"))
                notes_text = st.text_area("Observaciones de ficha", value=str(patient.get("notes") or ""), max_chars=1500)
                save = st.form_submit_button("Guardar actualización", type="primary", use_container_width=True)
            if save:
                try:
                    REPOSITORY.update_patient(patient["id"], {
                        "first_names": first_names.strip(),
                        "last_names": last_names.strip(),
                        "document_number": document_number.strip(),
                        "phone": phone.strip(),
                        "gender": "female" if gender_text == "Femenino" else "male",
                        "birth_date": birth_date_value.isoformat(),
                        "frame": {"Pequeña": "small", "Mediana": "medium", "Grande": "large"}[frame_text],
                        "height_cm": height,
                        "weight_kg": weight,
                        "department": department.strip(),
                        "province": province.strip(),
                        "district": district.strip(),
                        "city": city.strip(),
                        "notes": notes_text.strip(),
                    }, user)
                    st.success("Ficha actualizada. La fecha de modificación y el usuario quedaron registrados en auditoría.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    if user.get("role") == "doctor":
        with st.expander("Agregar nota médica o derivación"):
            with st.form(f"patient_note_{patient['id']}"):
                type_text = st.selectbox("Tipo de registro", ["Nota general","Seguimiento","Derivación","Nutrición","Cardiología","Laboratorio"])
                referral = st.text_input("Área de derivación", placeholder="Ejemplo: Nutrición, cardiología o laboratorio")
                observation = st.text_area("Observación médica", placeholder="Registre hallazgos, actualización del caso o motivo de derivación.", max_chars=2000)
                save_note = st.form_submit_button("Guardar nota", type="primary", use_container_width=True)
            if save_note:
                mapping={"Nota general":"GENERAL","Seguimiento":"FOLLOW_UP","Derivación":"REFERRAL","Nutrición":"NUTRITION","Cardiología":"CARDIOLOGY","Laboratorio":"LABORATORY"}
                try:
                    REPOSITORY.add_patient_note(patient["id"], mapping[type_text], observation, user, referral)
                    st.success("Nota médica guardada.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

# -----------------------------------------------------------------------------
# Doctor pages
# -----------------------------------------------------------------------------
def page_doctor_dashboard() -> None:
    user = require_role("doctor")
    if not user:
        return
    counts = REPOSITORY.dashboard_counts()
    institutional_header()
    section("Panel médico", "Alertas medias y altas ordenadas por fecha para revisión y seguimiento.")
    pending_all = REPOSITORY.list_evaluations(status="PENDING", alert_levels=["MEDIO","ALTO"], limit=100000)
    high_pending = sum(1 for row in pending_all if row.get("alert_level") == "ALTO")
    c1,c2,c3,c4 = st.columns(4)
    with c1: st.metric("Pendientes", len(pending_all))
    with c2: st.metric("Prioridad alta", high_pending)
    with c3: st.metric("Pacientes en sistema", counts["patients"])
    with c4: st.metric("Evaluaciones", counts["evaluations"])
    search = st.text_input("Buscar en la cola", placeholder="Código, documento, nombre o apellido")
    pending = REPOSITORY.list_evaluations(status="PENDING", search=search, alert_levels=["MEDIO","ALTO"], limit=100000)
    if pending:
        current,page,pages = pagination(pending, "doctor_pending_page", 50)
        frame=pd.DataFrame(current)
        show=frame[["patient_code","first_names","last_names","created_at","alert_level","source","nurse_name"]].copy()
        show["Día"]=[spanish_weekday(value) for value in show["created_at"]]
        show["created_at"]=[format_datetime_peru(value) for value in show["created_at"]]
        show["source"]=show["source"].map({"OFFICIAL":"Registro web","HISTORICAL_CSV":"CSV histórico"})
        show.columns=["Código","Nombres","Apellidos","Fecha","Alerta","Origen","Registrado por","Día"]
        st.dataframe(show[["Código","Nombres","Apellidos","Fecha","Día","Alerta","Origen","Registrado por"]],use_container_width=True,hide_index=True,height=520)
        st.caption(f"Página {page} de {pages} · {len(pending)} casos pendientes")
    else:
        st.success("No existen alertas medias o altas pendientes.")
    section("Distribución general", "Resumen de los resultados existentes en la base de datos.")
    historical_cohort_charts()

def page_medical_review() -> None:
    user = require_role("doctor")
    if not user:
        return
    institutional_header()
    section("Revisión médica", "Busque un caso, revise la evidencia y registre conclusión, estado y observación.")
    search = st.text_input("Buscar evaluación", placeholder="Código, documento, nombre o apellido")
    candidates = REPOSITORY.list_evaluations(
        search=search, alert_levels=["MEDIO", "ALTO"],
        statuses=["PENDING", "CORRECTION", "FOLLOW_UP", "REVIEWED"], limit=2000,
    )
    if not candidates:
        st.info("No hay evaluaciones medias o altas disponibles para revisar.")
        return
    options = {evaluation_display(item): item for item in candidates}
    evaluation = options[st.selectbox("Seleccione evaluación", list(options))]
    show_evaluation_detail(evaluation, allow_download=False)
    with st.form("medical_review_form"):
        c1, c2 = st.columns(2)
        with c1:
            status_text = st.selectbox("Estado", ["Revisado", "Requiere corrección", "Requiere seguimiento", "Cerrado"])
        with c2:
            conclusion_text = st.selectbox("Conclusión documentada", [
                "Sin conclusión clínica", "Riesgo descartado en revisión", "Requiere prueba de confirmación",
                "Confirmado por prueba externa", "Derivado a otro servicio",
            ])
        observation = st.text_area(
            "Observación médica*", max_chars=2000,
            placeholder="Ejemplo: se revisaron los datos; solicitar control de laboratorio y nueva evaluación.",
        )
        submitted = st.form_submit_button("Guardar revisión", type="primary", use_container_width=True)
    if submitted:
        status_map = {"Revisado":"REVIEWED","Requiere corrección":"CORRECTION","Requiere seguimiento":"FOLLOW_UP","Cerrado":"CLOSED"}
        conclusion_map = {
            "Sin conclusión clínica":"NO_CONCLUSION", "Riesgo descartado en revisión":"RISK_DISCARDED",
            "Requiere prueba de confirmación":"REQUIRES_CONFIRMATION", "Confirmado por prueba externa":"CONFIRMED_EXTERNAL",
            "Derivado a otro servicio":"REFERRED",
        }
        try:
            REPOSITORY.add_medical_review(evaluation["id"], status_map[status_text], observation, user, conclusion_map[conclusion_text])
            st.success("Revisión médica guardada en el historial.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

def page_medical_history() -> None:
    user = require_role("doctor")
    if not user:
        return
    institutional_header()
    section("Historial general de evaluaciones", "Línea de tiempo de resultados, revisiones y estados; diferente del directorio detallado de pacientes.")
    search = st.text_input("Buscar paciente", placeholder="Código, nombre o apellido")
    c1,c2,c3 = st.columns(3)
    with c1: status_filter = st.multiselect("Estado", list(STATUS_LABELS), format_func=status_label)
    with c2: alert_filter = st.multiselect("Alerta", ["BAJO","MEDIO","ALTO"])
    with c3: source_filter = st.selectbox("Origen", ["Todos","Registro web","CSV histórico"])
    source_value={"Registro web":"OFFICIAL","CSV histórico":"HISTORICAL_CSV"}.get(source_filter)
    filtered=REPOSITORY.list_evaluations(search=search,source=source_value,statuses=status_filter,alert_levels=alert_filter,limit=100000)
    if not filtered:
        st.info("No hay resultados con esos filtros.")
        return
    current,page,pages=pagination(filtered,"medical_history_page",50)
    frame=pd.DataFrame(current)
    show=frame[["patient_code","first_names","last_names","created_at","alert_level","status","source","last_doctor_name"]].copy()
    show["Día"]=[spanish_weekday(value) for value in show["created_at"]]
    show["created_at"]=[format_datetime_peru(value) for value in show["created_at"]]
    show["status"]=show["status"].map(status_label)
    show["source"]=show["source"].map({"OFFICIAL":"Registro web","HISTORICAL_CSV":"CSV histórico"})
    show["last_doctor_name"]=show["last_doctor_name"].fillna("Sin revisión")
    show.columns=["Código","Nombres","Apellidos","Fecha","Alerta","Estado","Origen","Último médico","Día"]
    st.dataframe(show[["Código","Nombres","Apellidos","Fecha","Día","Alerta","Estado","Origen","Último médico"]],use_container_width=True,hide_index=True,height=520)
    st.caption(f"Página {page} de {pages} · {len(filtered)} evaluaciones")
    options={evaluation_display(item):item for item in current}
    selected=options[st.selectbox("Abrir evaluación",list(options))]
    show_evaluation_detail(selected)

# -----------------------------------------------------------------------------
# Administration pages
# -----------------------------------------------------------------------------
def page_admin_dashboard() -> None:
    user = require_role("admin")
    if not user:
        return
    counts = REPOSITORY.dashboard_counts()
    institutional_header()
    section("Panel de administración", "Control de cuentas, trazabilidad, cohortes, exportación y continuidad de datos.", "Administración")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("Usuarios activos", counts["users"])
    with c2: st.metric("Históricos CSV", counts["historical_patients"])
    with c3: st.metric("Pacientes oficiales", counts["official_patients"])
    with c4: st.metric("Evaluaciones oficiales", counts["official_evaluations"])
    with c5: st.metric("Pendientes", counts["pending"])
    st.markdown(f'<div class="notice"><b>Base activa:</b> {REPOSITORY.status.label}. {REPOSITORY.status.detail}</div>', unsafe_allow_html=True)
    if MODEL_ERROR:
        st.error(f"Modelo no disponible: {MODEL_ERROR}")
    else:
        st.success(f"Modelo activo: {MODEL_BUNDLE.selected.name if MODEL_BUNDLE else 'Solo reglas'} · {MODEL_VERSION}")
    section("Separación de datos", "Los registros históricos sirven para investigación y demostración; los oficiales provienen de enfermería.")
    info_cards([
        (str(counts["historical_patients"]), "Filas históricas", "Importadas del CSV y organizadas mediante códigos de referencia HIS."),
        (str(counts["historical_evaluations"]), "Casos con glyhb", "Disponibles para análisis de la variable objetivo."),
        ("PAC", "Registros oficiales", "Se crean en la web y conservan seguimiento clínico académico."),
        ("AUD", "Auditoría", "Registra creación, revisión, acceso y cambios administrativos."),
    ])
    section("Estadísticas operativas", "Distribución de alertas y revisión de la operación oficial.")
    evaluation_dashboard_charts()
    section("Cohorte histórica", "Resumen de los casos importados desde diabetes.csv.")
    historical_cohort_charts()

def page_user_management() -> None:
    actor = require_role("admin")
    if not actor:
        return
    institutional_header()
    section("Gestión de usuarios", "El administrador crea cuentas sin correo electrónico y asigna el rol correspondiente.", "Control de acceso")
    tab1, tab2 = st.tabs(["Crear usuario", "Administrar existentes"])
    with tab1:
        role_text = st.selectbox("Rol de la nueva cuenta", ["Enfermería", "Médico", "Administrador"], key="new_user_role")
        role = {"Enfermería": "nurse", "Médico": "doctor", "Administrador": "admin"}[role_text]
        prefix = ROLE_PREFIXES[role]
        st.markdown(f'<div class="notice">El identificador debe comenzar con <b>{prefix}</b>. Ejemplos: <b>{prefix}4</b> o <b>{prefix}_apellido</b>. La demostración permite una clave de 7 caracteres; para un despliegue real se recomienda una clave más larga y distinta del usuario.</div>', unsafe_allow_html=True)
        create_visible = bool(st.session_state.get("show_admin_create_password", False))
        create_label = "🐵 Ocultar contraseñas" if create_visible else "🙈 Mostrar contraseñas"
        show_create_password = st.toggle(create_label, key="show_admin_create_password")
        with st.form("create_user_form"):
            c1, c2 = st.columns(2)
            with c1:
                username = st.text_input("Usuario", max_chars=40, placeholder=f"{prefix}4")
                display_name = st.text_input("Nombre mostrado", max_chars=80, placeholder="Nombre del personal")
            with c2:
                field_type = "default" if show_create_password else "password"
                password = st.text_input("Contraseña inicial", type=field_type, max_chars=128)
                confirm_password = st.text_input("Confirmar contraseña", type=field_type, max_chars=128)
            submitted = st.form_submit_button("Crear cuenta", type="primary", use_container_width=True)
        if submitted:
            if password != confirm_password:
                st.error("Las contraseñas no coinciden.")
            elif not password:
                st.error("Escriba una contraseña inicial.")
            else:
                problems = validate_password_strength(password, normalize_username(username))
                if problems:
                    st.warning("Recomendación de seguridad: " + " ".join(problems))
                try:
                    created = REPOSITORY.create_user(username, password, role, display_name, actor)
                    st.success(f"Cuenta creada: {created['username']} · {ROLE_LABELS[created['role']]}")
                except Exception as exc:
                    st.error(str(exc))
    with tab2:
        users = REPOSITORY.list_users(include_inactive=True)
        frame = rows_to_dataframe(users)
        if not frame.empty:
            show = frame[["username", "display_name", "role", "active", "failed_attempts", "locked_until", "last_login"]].copy()
            show["role"] = show["role"].map(ROLE_LABELS)
            show["active"] = show["active"].map({1: "Activo", 0: "Inactivo"})
            show["locked_until"] = [format_datetime_peru(value) if pd.notna(value) else "Sin bloqueo" for value in show["locked_until"]]
            show["last_login"] = [format_datetime_peru(value) if pd.notna(value) else "Nunca" for value in show["last_login"]]
            show.columns = ["Usuario", "Nombre", "Rol", "Estado", "Intentos", "Bloqueado hasta", "Último acceso"]
            st.dataframe(show, use_container_width=True, hide_index=True)
        if not users:
            st.info("No hay usuarios registrados.")
            return
        options = {f"{item['username']} · {ROLE_LABELS.get(item['role'])}": item for item in users}
        target = options[st.selectbox("Seleccione usuario", list(options))]
        c1, c2 = st.columns(2)
        with c1:
            reset_visible = bool(st.session_state.get("show_admin_reset", False))
            reset_label = "🐵 Ocultar nueva contraseña" if reset_visible else "🙈 Mostrar nueva contraseña"
            show_reset = st.toggle(reset_label, key="show_admin_reset")
            new_password = st.text_input("Nueva contraseña", type="default" if show_reset else "password", max_chars=128, key="admin_reset_password")
            if st.button("Restablecer contraseña", use_container_width=True):
                if not new_password:
                    st.error("Escriba una nueva contraseña.")
                else:
                    try:
                        REPOSITORY.reset_user_password(target["id"], new_password, actor)
                        st.success("Contraseña restablecida.")
                    except Exception as exc:
                        st.error(str(exc))
        with c2:
            active = bool(target.get("active"))
            label = "Desactivar usuario" if active else "Activar usuario"
            if st.button(label, use_container_width=True):
                try:
                    REPOSITORY.set_user_active(target["id"], not active, actor)
                    st.success("Estado actualizado.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def page_audit() -> None:
    actor = require_role("admin")
    if not actor:
        return
    institutional_header()
    section("Auditoría", "Registra accesos y acciones relevantes. No almacena contraseñas ni variables clínicas completas en el log.")
    limit = st.slider("Cantidad de eventos", 50, 1000, 300, 50)
    rows = REPOSITORY.list_audit_logs(limit=limit)
    frame = rows_to_dataframe(rows)
    if frame.empty:
        st.info("No hay eventos.")
        return
    show = frame[["created_at", "username", "role", "action", "entity", "entity_id", "detail_json"]].copy()
    show["created_at"] = [format_datetime_peru(value) for value in show["created_at"]]
    show["role"] = show["role"].map(ROLE_LABELS).fillna("Público / desconocido")
    show.columns = ["Fecha", "Usuario", "Rol", "Acción", "Entidad", "ID", "Detalle"]
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.download_button("Descargar auditoría CSV", show.to_csv(index=False).encode("utf-8-sig"), "auditoria.csv", "text/csv", use_container_width=True)


def page_backups() -> None:
    actor = require_role("admin")
    if not actor:
        return
    institutional_header()
    section("Respaldos y exportación", "Descargue información general, datos anonimizados y una copia completa de la base.", "Continuidad de datos")
    all_patients = REPOSITORY.list_patients(include_inactive=True, limit=100000)
    export_rows = directory_export_rows(all_patients)
    patients_frame = pd.DataFrame(export_rows)
    anonymized_csv = REPOSITORY.anonymized_evaluations_dataframe().to_csv(index=False).encode("utf-8-sig")
    audit_csv = REPOSITORY.dataframe("audit_logs").to_csv(index=False).encode("utf-8-sig")
    c1,c2,c3,c4 = st.columns(4)
    with c1: st.download_button("Pacientes CSV", patients_frame.to_csv(index=False).encode("utf-8-sig"), "pacientes.csv", "text/csv", use_container_width=True)
    with c2: st.download_button("Pacientes PDF", build_patients_directory_pdf(export_rows), "pacientes.pdf", "application/pdf", use_container_width=True)
    with c3: st.download_button("Evaluaciones anonimizadas", anonymized_csv, "evaluaciones_anonimizadas.csv", "text/csv", use_container_width=True)
    with c4: st.download_button("Auditoría CSV", audit_csv, "auditoria.csv", "text/csv", use_container_width=True)
    st.download_button("Descargar base SQLite completa", REPOSITORY.backup_bytes(), f"sistema_diabetes_v8_{datetime.now().strftime('%Y%m%d_%H%M')}.db", "application/octet-stream", use_container_width=True, type="primary")

    section("Restaurar una copia", "Seleccione un archivo .db generado por este sistema.")
    uploaded=st.file_uploader("Seleccione una copia SQLite",type=["db"],key="restore_sqlite_backup")
    confirm=st.checkbox("Confirmo que deseo reemplazar la base actual por la copia seleccionada.")
    if st.button("Restaurar base de datos",use_container_width=True,disabled=uploaded is None or not confirm):
        try:
            REPOSITORY.restore_backup_bytes(uploaded.getvalue(),actor)
            st.success("Copia restaurada correctamente.")
            st.rerun()
        except Exception as exc: st.error(str(exc))

def confusion_figure(bundle: ModelBundle) -> go.Figure:
    cm = bundle.selected.cm
    # Se invierte el orden visual de las filas para coincidir con la presentación del notebook:
    # primero los casos positivos de referencia y luego los negativos.
    visual = cm[[1, 0], :]
    text = [
        [f"Falso negativo<br><b>{cm[1,0]}</b>", f"Verdadero positivo<br><b>{cm[1,1]}</b>"],
        [f"Verdadero negativo<br><b>{cm[0,0]}</b>", f"Falso positivo<br><b>{cm[0,1]}</b>"],
    ]
    fig = go.Figure(go.Heatmap(z=visual, x=["Predijo NO", "Predijo alerta"], y=["Real alerta", "Real NO"], text=text, texttemplate="%{text}", colorscale="YlGnBu", showscale=False))
    fig.update_layout(height=420, margin=dict(l=20,r=20,t=35,b=20), title="Matriz de confusión")
    return fig

def page_model_quality() -> None:
    actor = require_role("admin")
    if not actor:
        return
    institutional_header()
    section("Modelo, métricas y calidad", "El Random Forest se entrena con el diabetes.csv incluido. Los pacientes nuevos solo se predicen y nunca reentrenan automáticamente el modelo.")
    st.markdown('<div class="notice"><b>Uso de las 19 columnas:</b> id y location son metadatos; glyhb construye la clase objetivo; 16 variables actúan como predictores. En la evaluación web, edad, sexo, talla, peso y complexión se toman del perfil del paciente y las demás se completan en el formulario.</div>', unsafe_allow_html=True)
    st.markdown('<div class="source-note"><b>Valores faltantes:</b> durante el entrenamiento, las variables numéricas se completan con la mediana y las categóricas con la categoría más frecuente. En la cohorte navegable, cada registro indica si algún campo fue imputado.</div>', unsafe_allow_html=True)
    if MODEL_ERROR or MODEL_BUNDLE is None:
        st.error(f"No se pudo cargar el modelo: {MODEL_ERROR or 'dataset no disponible'}")
        return
    metrics = metrics_dataframe(MODEL_BUNDLE)
    st.dataframe(metrics.style.format({
        "Accuracy": "{:.3f}", "Precision": "{:.3f}", "Recall": "{:.3f}",
        "F1": "{:.3f}", "ROC-AUC": "{:.3f}", "F1 validación cruzada": "{:.3f}",
    }), use_container_width=True, hide_index=True)
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(confusion_figure(MODEL_BUNDLE), use_container_width=True)
    with c2:
        importance = MODEL_BUNDLE.selected.feature_importance.head(12).sort_values("importance")
        fig = px.bar(importance, x="importance", y="feature", orientation="h", title="Variables con mayor importancia")
        fig.update_layout(height=420, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig, use_container_width=True)
    cm = MODEL_BUNDLE.selected.cm
    e1,e2,e3,e4 = st.columns(4)
    with e1: status_card("Verdaderos negativos", str(int(cm[0,0])), "Personas sin alerta correctamente identificadas.")
    with e2: status_card("Falsos positivos", str(int(cm[0,1])), "Personas marcadas con alerta aunque la referencia era negativa.")
    with e3: status_card("Falsos negativos", str(int(cm[1,0])), "Personas positivas de referencia que el modelo no detectó.")
    with e4: status_card("Verdaderos positivos", str(int(cm[1,1])), "Personas positivas de referencia correctamente detectadas.")
    st.markdown("""
    #### Cómo leer las métricas

    - **Accuracy:** proporción total de casos correctamente clasificados.
    - **Precision:** de las alertas positivas, cuántas coincidieron con la clase de referencia.
    - **Recall o sensibilidad:** de los casos positivos de referencia, cuántos fueron detectados.
    - **F1:** equilibrio entre precision y sensibilidad.
    - **ROC-AUC:** capacidad de separar las dos clases en distintos umbrales.

    #### Control de calidad implementado

    - Validación de rangos en formularios y restricciones en la base.
    - Contraseñas con hash y sal; no se guardan en texto visible.
    - Autorización por roles comprobada en cada página y operación.
    - Auditoría de accesos, creación de registros, revisiones y administración.
    - Trazabilidad de la versión del modelo en cada evaluación.
    - PDF individual, CSV anonimizado y respaldo completo de SQLite.
    - Pruebas automáticas básicas para reglas, autenticación y base de datos.

    El proyecto **no está certificado**. Se presenta como alineado de manera académica con criterios de calidad de software y seguridad, no como cumplimiento formal de una norma ISO.
    """)


# -----------------------------------------------------------------------------
# Navigation
# -----------------------------------------------------------------------------
user = st.session_state.user
sidebar_brand(user)
st.sidebar.divider()

if user is None:
    public_pages = {
        "Inicio": page_home,
        "Consulta pública": page_public_consultation,
        "Información": page_information,
        "Arquitectura": page_architecture,
        "Acerca del proyecto": page_project,
        "Acceso del personal": page_login,
    }
    page_name = st.sidebar.radio("Navegación", list(public_pages), key="public_navigation")
    st.sidebar.divider()
    st.sidebar.caption(f"Modelo: {MODEL_BUNDLE.selected.name if MODEL_BUNDLE else 'Solo reglas'}")
    st.sidebar.caption(f"Base: {REPOSITORY.status.label}")
    if MODEL_ERROR:
        st.sidebar.warning("El componente predictivo no pudo cargarse; las reglas continúan disponibles.")
    public_pages[page_name]()
else:
    role = str(user.get("role"))
    if role == "nurse":
        pages = {
            "Panel de enfermería": page_nurse_dashboard,
            "Registrar paciente": page_register_patient,
            "Nueva evaluación": page_new_evaluation,
            "Directorio de pacientes": page_patients_history,
        }
    elif role == "doctor":
        pages = {
            "Panel médico": page_doctor_dashboard,
            "Revisión médica": page_medical_review,
            "Historial": page_medical_history,
            "Directorio de pacientes": page_patients_history,
        }
    elif role == "admin":
        pages = {
            "Panel administrador": page_admin_dashboard,
            "Usuarios": page_user_management,
            "Auditoría": page_audit,
            "Respaldos": page_backups,
            "Modelo y calidad": page_model_quality,
        }
    else:
        st.error("Rol no reconocido.")
        pages = {"Inicio": page_home}
    page_name = st.sidebar.radio("Navegación", list(pages), key=f"private_navigation_{role}")
    st.sidebar.divider()
    logout_button()
    st.sidebar.divider()
    st.sidebar.caption(f"Sesión: {user.get('username')} · {ROLE_LABELS.get(role, role)}")
    st.sidebar.caption(f"Versión: {APP_VERSION}")
    pages[page_name]()
