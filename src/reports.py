from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .config import (
    APP_TITLE,
    APP_VERSION,
    DISCLAIMER,
    LOGO_SISTEMAS_PATH,
    LOGO_UNAMAD_PATH,
    STATUS_LABELS,
    UNAMAD_DARK,
    UNAMAD_GOLD,
    UNAMAD_GREEN,
)


PERU_TZ = ZoneInfo("America/Lima")


def _format_datetime_peru(value: Any, *, historical: bool = False) -> str:
    del historical
    if value is None or not str(value).strip():
        return "Sin fecha"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(PERU_TZ).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return str(value)


def _frame_label(value: Any) -> str:
    return {"small": "Pequeña", "medium": "Mediana", "large": "Grande"}.get(str(value), str(value))


def _gender_label(value: Any) -> str:
    return {"female": "Femenino", "male": "Masculino"}.get(str(value), str(value))


def parse_rules_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="University",
        parent=styles["Title"],
        textColor=colors.HexColor(UNAMAD_DARK),
        alignment=TA_CENTER,
        fontSize=15,
        leading=18,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Heading1"],
        textColor=colors.HexColor(UNAMAD_GREEN),
        alignment=TA_CENTER,
        fontSize=13,
        leading=16,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="SectionGreen",
        parent=styles["Heading2"],
        textColor=colors.HexColor(UNAMAD_GREEN),
        fontSize=11.5,
        leading=14,
        spaceBefore=8,
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="SmallNote",
        parent=styles["BodyText"],
        textColor=colors.HexColor("#5B6D66"),
        fontSize=8.2,
        leading=10.5,
    ))
    return styles


def _header(story: list[Any], styles: Any, subtitle: str) -> None:
    logos: list[Any] = []
    if Path(LOGO_UNAMAD_PATH).exists():
        logos.append(Image(str(LOGO_UNAMAD_PATH), width=1.7 * cm, height=1.9 * cm))
    if Path(LOGO_SISTEMAS_PATH).exists():
        logos.append(Image(str(LOGO_SISTEMAS_PATH), width=1.7 * cm, height=1.7 * cm))
    if logos:
        cells = [logos[0], ""] if len(logos) == 1 else [logos[0], logos[1]]
        logo_table = Table([cells], colWidths=[8.25 * cm, 8.25 * cm])
        logo_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(logo_table)
    story.append(Paragraph("UNIVERSIDAD NACIONAL AMAZÓNICA DE MADRE DE DIOS", styles["University"]))
    story.append(Paragraph("Escuela Profesional de Ingeniería de Sistemas e Informática", styles["BodyText"]))
    story.append(Paragraph(subtitle, styles["ReportTitle"]))


def _table_style(header: bool = False) -> TableStyle:
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#D7E3DD")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F7FAF8")]),
    ]
    if header:
        commands.extend([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(UNAMAD_GREEN)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ])
    else:
        commands.extend([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(UNAMAD_DARK)),
        ])
    return TableStyle(commands)


def _alert_table(level: str, probability: float | None, score: int, styles: Any) -> Table:
    probability_text = "No disponible" if probability is None else f"{probability * 100:.1f} %"
    alert_color = {"BAJO": "#238657", "MEDIO": "#D39100", "ALTO": "#C23A3A"}.get(level, "#365249")
    alert_label = {"BAJO": "BAJA", "MEDIO": "MEDIA", "ALTO": "ALTA"}.get(level, level)
    table = Table(
        [[
            Paragraph(f"<b>ALERTA {alert_label}</b>", styles["Heading2"]),
            Paragraph(f"Probabilidad ML: <b>{probability_text}</b><br/>Puntaje experto: <b>{score}</b>", styles["BodyText"]),
        ]],
        colWidths=[8.2 * cm, 8.3 * cm],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F6F8F7")),
        ("BOX", (0, 0), (-1, -1), 1.1, colors.HexColor(alert_color)),
        ("LINEBEFORE", (0, 0), (0, 0), 5, colors.HexColor(alert_color)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _number(value: Any, decimals: int = 1) -> str:
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return ""


def _variables_table(evaluation: dict[str, Any], styles: Any) -> Table:
    rows = [
        ["Indicador", "Valor", "Indicador", "Valor"],
        ["Glucosa", f"{_number(evaluation.get('stab_glu'), 1)} mg/dL", "HbA1c / glyhb", f"{_number(evaluation.get('glyhb'), 2)} %"],
        ["Colesterol", f"{_number(evaluation.get('chol'), 1)} mg/dL", "HDL", f"{_number(evaluation.get('hdl'), 1)} mg/dL"],
        ["Relación colesterol/HDL", _number(evaluation.get("ratio"), 2), "Peso", f"{_number(evaluation.get('weight_kg'), 1)} kg"],
        ["Altura", f"{_number(evaluation.get('height_cm'), 1)} cm", "Complexión", _frame_label(evaluation.get("frame", ""))],
        ["PA lectura 1", f"{_number(evaluation.get('bp1s'), 0)}/{_number(evaluation.get('bp1d'), 0)} mmHg", "PA lectura 2", f"{_number(evaluation.get('bp2s'), 0)}/{_number(evaluation.get('bp2d'), 0)} mmHg"],
        ["Cintura", f"{_number(evaluation.get('waist_cm'), 1)} cm", "Cadera", f"{_number(evaluation.get('hip_cm'), 1)} cm"],
        ["Minutos poscomida", _number(evaluation.get("time_ppn"), 0), "Edad / sexo", f"{_number(evaluation.get('age'), 0)} años · {_gender_label(evaluation.get('gender', ''))}"],
    ]
    table = Table(rows, colWidths=[4.2 * cm, 4.0 * cm, 4.2 * cm, 4.1 * cm], repeatRows=1)
    table.setStyle(_table_style(header=True))
    return table


def _rules_section(story: list[Any], rules: dict[str, Any], styles: Any) -> None:
    story.append(Paragraph("Reglas activadas y explicación", styles["SectionGreen"]))
    activated = rules.get("activated", []) if isinstance(rules, dict) else []
    if not activated:
        story.append(Paragraph("No se activaron reglas de alerta.", styles["BodyText"]))
        return
    rows: list[list[Any]] = [["Regla", "Indicador", "Valor / referencia", "Puntos"]]
    for item in activated:
        rows.append([
            item.get("code", ""),
            Paragraph(str(item.get("indicator", "")), styles["BodyText"]),
            Paragraph(
                f"{item.get('patient_value', '')}<br/><font color='#61756E'>{item.get('reference', '')}</font>",
                styles["BodyText"],
            ),
            str(item.get("points", "")),
        ])
    table = Table(rows, colWidths=[1.5 * cm, 5.2 * cm, 7.7 * cm, 1.7 * cm], repeatRows=1)
    table.setStyle(_table_style(header=True))
    story.append(table)


def build_public_pdf(evaluation: dict[str, Any], rules: dict[str, Any]) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title="Consulta pública orientativa de diabetes",
    )
    styles = _styles()
    story: list[Any] = []
    _header(story, styles, "Consulta pública orientativa del riesgo de diabetes")
    story.append(_alert_table(
        str(evaluation.get("alert_level", "")),
        evaluation.get("ml_probability"),
        int(evaluation.get("rule_score", 0)),
        styles,
    ))
    story.append(Paragraph("Datos ingresados", styles["SectionGreen"]))
    story.append(_variables_table(evaluation, styles))
    _rules_section(story, rules, styles)
    story.append(Paragraph("Interpretación", styles["SectionGreen"]))
    story.append(Paragraph(str(evaluation.get("explanation", "")), styles["BodyText"]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph(
        "Esta consulta no fue guardada como registro oficial. Presente el reporte a un profesional si necesita una evaluación clínica.",
        styles["SmallNote"],
    ))
    story.append(Paragraph(DISCLAIMER, styles["SmallNote"]))
    story.append(Paragraph(f"Versión del sistema {APP_VERSION} · Autores: Poldy Raúl Ripa Challco y Frank Hiobert Palomino Usca.", styles["SmallNote"]))
    document.build(story)
    return buffer.getvalue()


def build_official_pdf(
    patient: dict[str, Any],
    evaluation: dict[str, Any],
    rules: dict[str, Any],
    reviews: list[dict[str, Any]] | None = None,
    patient_notes: list[dict[str, Any]] | None = None,
) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title=f"Reporte {patient.get('code', 'Paciente')}",
    )
    styles = _styles()
    story: list[Any] = []
    _header(story, styles, APP_TITLE)
    story.append(_alert_table(
        str(evaluation.get("alert_level", "")),
        evaluation.get("ml_probability"),
        int(evaluation.get("rule_score", 0)),
        styles,
    ))

    story.append(Paragraph("Identificación del registro", styles["SectionGreen"]))
    full_name = f"{patient.get('first_names', '')} {patient.get('last_names', '')}".strip()
    rows = [
        ["Código", patient.get("code", "")],
        ["Paciente", full_name or "Sin nombre"],
        ["Documento", patient.get("document_number") or "No registrado"],
        ["Ubicación", evaluation.get("location_text", "")],
        ["Fecha de evaluación", _format_datetime_peru(
            evaluation.get("created_at"),
            historical=evaluation.get("source") == "HISTORICAL_CSV",
        )],
        ["Registrado por", evaluation.get("nurse_name") or evaluation.get("nurse_username") or "Enfermería"],
        ["Estado", STATUS_LABELS.get(str(evaluation.get("status")), str(evaluation.get("status", "")))],
        ["Modelo", f"{evaluation.get('model_name') or 'Solo reglas'} · {evaluation.get('model_version') or ''}"],
        ["Origen", "Cohorte histórica CSV - código de referencia HIS" if evaluation.get("source") == "HISTORICAL_CSV" else "Registro generado en la plataforma"],
    ]
    table = Table(rows, colWidths=[4.8 * cm, 11.7 * cm])
    table.setStyle(_table_style())
    story.append(table)

    story.append(Paragraph("Variables registradas", styles["SectionGreen"]))
    story.append(_variables_table(evaluation, styles))
    _rules_section(story, rules, styles)

    story.append(Paragraph("Interpretación del sistema", styles["SectionGreen"]))
    story.append(Paragraph(str(evaluation.get("explanation", "")), styles["BodyText"]))
    if evaluation.get("nursing_notes"):
        story.append(Paragraph("Observación de enfermería", styles["SectionGreen"]))
        story.append(Paragraph(str(evaluation.get("nursing_notes")), styles["BodyText"]))

    if reviews:
        story.append(Paragraph("Revisión médica", styles["SectionGreen"]))
        review_rows: list[list[Any]] = [["Fecha", "Profesional", "Estado / conclusión", "Observación"]]
        for review in reviews:
            review_rows.append([
                _format_datetime_peru(review.get("created_at")),
                Paragraph(str(review.get("doctor_name") or review.get("doctor_username") or "Médico"), styles["BodyText"]),
                Paragraph(
                    STATUS_LABELS.get(str(review.get("status")), str(review.get("status", "")))
                    + "<br/><font color='#5B6D66'>" + {
                        "NO_CONCLUSION": "Sin conclusión clínica",
                        "RISK_DISCARDED": "Riesgo descartado en revisión",
                        "REQUIRES_CONFIRMATION": "Requiere prueba de confirmación",
                        "CONFIRMED_EXTERNAL": "Confirmado por prueba externa",
                        "REFERRED": "Derivado a otro servicio",
                    }.get(str(review.get("conclusion")), str(review.get("conclusion") or "")) + "</font>",
                    styles["BodyText"],
                ),
                Paragraph(str(review.get("observation", "")), styles["BodyText"]),
            ])
        review_table = Table(
            review_rows, colWidths=[3.1 * cm, 3.5 * cm, 4.1 * cm, 5.8 * cm], repeatRows=1
        )
        review_table.setStyle(_table_style(header=True))
        story.append(review_table)

    if patient_notes:
        story.append(Paragraph("Notas médicas y derivaciones", styles["SectionGreen"]))
        note_rows: list[list[Any]] = [["Fecha", "Profesional", "Tipo / área", "Observación"]]
        type_labels = {
            "GENERAL": "Nota general", "FOLLOW_UP": "Seguimiento", "REFERRAL": "Derivación",
            "NUTRITION": "Nutrición", "CARDIOLOGY": "Cardiología", "LABORATORY": "Laboratorio",
        }
        for note in patient_notes:
            note_rows.append([
                _format_datetime_peru(note.get("created_at")),
                Paragraph(str(note.get("doctor_name") or note.get("doctor_username") or "Médico"), styles["BodyText"]),
                Paragraph(type_labels.get(str(note.get("note_type")), str(note.get("note_type") or ""))
                          + ("<br/><font color='#5B6D66'>" + str(note.get("referral_area")) + "</font>" if note.get("referral_area") else ""), styles["BodyText"]),
                Paragraph(str(note.get("observation", "")), styles["BodyText"]),
            ])
        notes_table = Table(note_rows, colWidths=[3.1 * cm, 3.4 * cm, 4.2 * cm, 5.8 * cm], repeatRows=1)
        notes_table.setStyle(_table_style(header=True))
        story.append(notes_table)

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(DISCLAIMER, styles["SmallNote"]))
    story.append(Paragraph(
        "Sistema de apoyo al tamizaje desarrollado en la Escuela Profesional de Ingeniería de Sistemas e Informática. El reporte es orientativo y requiere revisión profesional.",
        styles["SmallNote"],
    ))
    document.build(story)
    return buffer.getvalue()


def build_patients_directory_pdf(rows: list[dict[str, Any]], title: str = "Directorio general de pacientes") -> bytes:
    """Generate a paginated landscape PDF with the complete patient directory."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), rightMargin=1.0 * cm, leftMargin=1.0 * cm,
        topMargin=1.0 * cm, bottomMargin=1.0 * cm, title=title,
    )
    styles = _styles()
    story: list[Any] = []
    _header(story, styles, title)
    story.append(Paragraph(f"Total de registros: {len(rows)}", styles["BodyText"]))
    data: list[list[Any]] = [["Código", "Paciente", "Sexo", "Edad", "Fecha de registro", "Origen", "Evaluaciones", "Última alerta"]]
    for row in rows:
        name = f"{row.get('first_names','')} {row.get('last_names','')}".strip()
        age = row.get("display_age")
        data.append([
            str(row.get("code", "")),
            Paragraph(name, styles["BodyText"]),
            _gender_label(row.get("gender", "")),
            "" if age is None else str(age),
            str(row.get("display_created_at") or row.get("created_at") or ""),
            "Histórico" if row.get("source") == "HISTORICAL_CSV" else "Oficial",
            str(row.get("evaluation_count", 0)),
            str(row.get("last_alert") or "Sin evaluación"),
        ])
    table = Table(data, colWidths=[2.6*cm, 5.6*cm, 2.3*cm, 1.8*cm, 3.5*cm, 2.6*cm, 2.5*cm, 2.8*cm], repeatRows=1)
    table.setStyle(_table_style(header=True))
    story.append(table)
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph(
        "Documento generado por el sistema web. Los códigos HIS corresponden a la cohorte histórica importada y los códigos PAC a registros creados en la plataforma.",
        styles["SmallNote"],
    ))
    document.build(story)
    return buffer.getvalue()
