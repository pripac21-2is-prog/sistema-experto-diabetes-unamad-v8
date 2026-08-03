from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class RuleEvidence:
    code: str
    indicator: str
    patient_value: str
    reference: str
    result: str
    points: int
    explanation: str


@dataclass
class ExpertResult:
    level: str
    score: int
    activated: list[RuleEvidence]
    favorable: list[RuleEvidence]

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "score": self.score,
            "activated": [asdict(item) for item in self.activated],
            "favorable": [asdict(item) for item in self.favorable],
        }


def cm_to_inches(value: float) -> float:
    return float(value) / 2.54


def kg_to_pounds(value: float) -> float:
    return float(value) * 2.2046226218


def safe_mean(*values: Any) -> float:
    numbers = [float(v) for v in values if v is not None]
    return sum(numbers) / len(numbers) if numbers else 0.0


def evaluate_rules(values: dict[str, Any]) -> ExpertResult:
    """Evaluate the explicit SI-THEN knowledge base.

    The thresholds reproduce the ranges used in the academic laboratory. They are
    presented as alert rules and not as an autonomous medical diagnosis.
    """
    activated: list[RuleEvidence] = []
    favorable: list[RuleEvidence] = []
    score = 0

    def add_active(code: str, indicator: str, value: str, reference: str, points: int, explanation: str) -> None:
        nonlocal score
        score += points
        activated.append(RuleEvidence(code, indicator, value, reference, "Activa alerta", points, explanation))

    def add_favorable(code: str, indicator: str, value: str, reference: str, explanation: str) -> None:
        favorable.append(RuleEvidence(code, indicator, value, reference, "Sin alerta en esta regla", 0, explanation))

    glyhb = float(values.get("glyhb", 0))
    glucose = float(values.get("stab_glu", values.get("stab.glu", 0)))
    chol = float(values.get("chol", 0))
    hdl = max(float(values.get("hdl", 0)), 0.01)
    ratio = float(values.get("ratio", chol / hdl if hdl else 0))
    gender = str(values.get("gender", "female")).lower()
    age = float(values.get("age", 0))
    waist_cm = float(values.get("waist_cm", 0))
    hip_cm = max(float(values.get("hip_cm", 0)), 0.01)
    sbp = safe_mean(values.get("bp1s"), values.get("bp2s"))
    dbp = safe_mean(values.get("bp1d"), values.get("bp2d"))

    # R1 — glyhb.
    if glyhb >= 6.5:
        add_active("R1", "Hemoglobina glucosilada", f"{glyhb:.1f} %", "glyhb ≥ 6.5", 4,
                   "Alcanza el punto de corte empleado para formar la clase positiva del estudio.")
    elif glyhb >= 5.7:
        add_active("R1", "Hemoglobina glucosilada", f"{glyhb:.1f} %", "5.7–6.4", 2,
                   "Se ubica en una zona intermedia y requiere seguimiento dentro del sistema.")
    else:
        add_favorable("R1", "Hemoglobina glucosilada", f"{glyhb:.1f} %", "< 5.7",
                      "No activa la regla de glyhb elevada.")

    # R2 — fasting/stabilized glucose.
    if glucose >= 125:
        add_active("R2", "Glucosa", f"{glucose:.0f} mg/dL", "≥ 125 mg/dL", 3,
                   "Se encuentra en el intervalo superior definido en el laboratorio.")
    elif glucose >= 100:
        add_active("R2", "Glucosa", f"{glucose:.0f} mg/dL", "100–124 mg/dL", 1,
                   "Se ubica en el intervalo intermedio del análisis.")
    elif glucose < 70:
        add_active("R2", "Glucosa", f"{glucose:.0f} mg/dL", "< 70 mg/dL", 1,
                   "Es un valor bajo que requiere revisión, aunque no implica diabetes por sí solo.")
    else:
        add_favorable("R2", "Glucosa", f"{glucose:.0f} mg/dL", "70–99 mg/dL",
                      "Se ubica en el intervalo central usado por el proyecto.")

    # R3 — concordance between glyhb and glucose.
    if glyhb >= 6.5 and glucose >= 125:
        add_active("R3", "Concordancia glucémica", f"glyhb {glyhb:.1f}% + glucosa {glucose:.0f}",
                   "Ambas variables elevadas", 3,
                   "La coincidencia de dos indicadores aumenta la prioridad de la alerta.")

    # R4 — total cholesterol.
    if chol >= 240:
        add_active("R4", "Colesterol total", f"{chol:.0f} mg/dL", "≥ 240 mg/dL", 2,
                   "Se ubica en la categoría alta utilizada en el análisis exploratorio.")
    elif chol >= 200:
        add_active("R4", "Colesterol total", f"{chol:.0f} mg/dL", "200–239 mg/dL", 1,
                   "Se ubica en la categoría de advertencia del estudio.")
    else:
        add_favorable("R4", "Colesterol total", f"{chol:.0f} mg/dL", "< 200 mg/dL",
                      "No activa la regla de colesterol elevado.")

    # R5 — HDL, with sex-specific threshold used in the notebook.
    hdl_limit = 50 if gender in {"female", "femenino", "f"} else 40
    if hdl < hdl_limit:
        add_active("R5", "HDL", f"{hdl:.0f} mg/dL", f"< {hdl_limit} mg/dL", 2,
                   "El HDL está por debajo del límite configurado para el sexo registrado.")
    elif hdl >= 60:
        add_favorable("R5", "HDL", f"{hdl:.0f} mg/dL", "≥ 60 mg/dL",
                      "El HDL se encuentra en el grupo alto del análisis.")
    else:
        add_favorable("R5", "HDL", f"{hdl:.0f} mg/dL", f"{hdl_limit}–59 mg/dL",
                      "No activa la regla de HDL bajo.")

    # R6 — cholesterol/HDL ratio.
    if ratio >= 7.5:
        add_active("R6", "Relación colesterol/HDL", f"{ratio:.2f}", "≥ 7.5", 2,
                   "La relación se separa claramente del grupo central del dataset.")
    elif ratio >= 5:
        add_active("R6", "Relación colesterol/HDL", f"{ratio:.2f}", "5.0–7.49", 1,
                   "La relación se encuentra por encima del grupo central.")
    else:
        add_favorable("R6", "Relación colesterol/HDL", f"{ratio:.2f}", "< 5.0",
                      "No activa la regla de ratio elevado.")

    # R7 — average systolic pressure from two readings.
    if sbp >= 180:
        add_active("R7", "Presión sistólica promedio", f"{sbp:.0f} mmHg", "≥ 180 mmHg", 3,
                   "El promedio de las dos lecturas está en el intervalo extremo del proyecto.")
    elif sbp >= 140:
        add_active("R7", "Presión sistólica promedio", f"{sbp:.0f} mmHg", "140–179 mmHg", 2,
                   "El promedio se ubica en una categoría elevada.")
    elif sbp >= 130:
        add_active("R7", "Presión sistólica promedio", f"{sbp:.0f} mmHg", "130–139 mmHg", 1,
                   "El promedio activa una advertencia leve.")
    else:
        add_favorable("R7", "Presión sistólica promedio", f"{sbp:.0f} mmHg", "< 130 mmHg",
                      "No activa la regla sistólica elevada.")

    # R8 — average diastolic pressure from two readings.
    if dbp >= 120:
        add_active("R8", "Presión diastólica promedio", f"{dbp:.0f} mmHg", "≥ 120 mmHg", 3,
                   "El promedio está en el intervalo extremo del proyecto.")
    elif dbp >= 90:
        add_active("R8", "Presión diastólica promedio", f"{dbp:.0f} mmHg", "90–119 mmHg", 2,
                   "El promedio se ubica en una categoría elevada.")
    elif dbp >= 80:
        add_active("R8", "Presión diastólica promedio", f"{dbp:.0f} mmHg", "80–89 mmHg", 1,
                   "El promedio activa una advertencia leve.")
    else:
        add_favorable("R8", "Presión diastólica promedio", f"{dbp:.0f} mmHg", "< 80 mmHg",
                      "No activa la regla diastólica elevada.")

    # R9 — waist threshold.
    waist_limit = 88 if gender in {"female", "femenino", "f"} else 102
    if waist_cm >= waist_limit:
        add_active("R9", "Circunferencia de cintura", f"{waist_cm:.1f} cm", f"≥ {waist_limit} cm", 1,
                   "La medida supera el límite configurado para el sexo registrado.")
    else:
        add_favorable("R9", "Circunferencia de cintura", f"{waist_cm:.1f} cm", f"< {waist_limit} cm",
                      "No activa la regla de cintura elevada.")

    # R10 — waist-to-hip ratio.
    waist_hip_ratio = waist_cm / hip_cm
    whr_limit = 0.85 if gender in {"female", "femenino", "f"} else 0.90
    if waist_hip_ratio >= whr_limit:
        add_active("R10", "Relación cintura/cadera", f"{waist_hip_ratio:.2f}", f"≥ {whr_limit:.2f}", 1,
                   "La proporción corporal activa una advertencia metabólica complementaria.")
    else:
        add_favorable("R10", "Relación cintura/cadera", f"{waist_hip_ratio:.2f}", f"< {whr_limit:.2f}",
                      "No activa la regla de relación cintura/cadera elevada.")

    # R11 — age plus intermediate/elevated glucose.
    if age >= 45 and glucose >= 100:
        add_active("R11", "Edad y glucosa", f"{age:.0f} años + {glucose:.0f} mg/dL", "Edad ≥ 45 y glucosa ≥ 100", 1,
                   "La combinación incrementa la prioridad de seguimiento en el sistema.")

    level = "ALTO" if score >= 10 else "MEDIO" if score >= 4 else "BAJO"
    return ExpertResult(level=level, score=score, activated=activated, favorable=favorable)


def hybrid_decision(expert: ExpertResult, probability: float | None, values: dict[str, Any]) -> tuple[str, str, float | None]:
    glyhb = float(values.get("glyhb", 0))
    glucose = float(values.get("stab_glu", values.get("stab.glu", 0)))
    direct_concordance = glyhb >= 6.5 and glucose >= 125

    if probability is None:
        level = expert.level
    elif direct_concordance or probability >= 0.72 or (expert.level == "ALTO" and probability >= 0.45):
        level = "ALTO"
    elif expert.level in {"MEDIO", "ALTO"} or probability >= 0.35:
        level = "MEDIO"
    else:
        level = "BAJO"

    messages = {
        "ALTO": (
            "El sistema detectó un patrón de alerta compatible con posible riesgo de diabetes. "
            "Debe confirmarse mediante evaluación profesional y pruebas clínicas."
        ),
        "MEDIO": (
            "El sistema detectó factores que requieren revisión y seguimiento. El resultado no "
            "confirma diabetes, pero recomienda evaluación profesional."
        ),
        "BAJO": (
            "El sistema no detectó un patrón alto con los datos ingresados. Esto no descarta "
            "diabetes ni sustituye controles médicos."
        ),
    }
    return level, messages[level], probability


def evidence_rows(result: ExpertResult) -> list[dict[str, Any]]:
    rows = result.activated + result.favorable
    return [asdict(row) for row in rows]
