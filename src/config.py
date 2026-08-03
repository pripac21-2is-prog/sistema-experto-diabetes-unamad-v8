from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = APP_DIR / "assets"
DATA_DIR = APP_DIR / "data"
LOGO_UNAMAD_PATH = ASSETS_DIR / "logo_unamad.png"
LOGO_SISTEMAS_PATH = ASSETS_DIR / "logo_sistemas.png"
MEDICAL_DOCTOR_PATH = ASSETS_DIR / "medical_doctor.png"
ARCHITECTURE_SYSTEM_PATH = ASSETS_DIR / "architecture_system.png"
ARCHITECTURE_ROLES_PATH = ASSETS_DIR / "architecture_roles.png"
ARCHITECTURE_WORKFLOW_PATH = ASSETS_DIR / "architecture_workflow.png"
LOCAL_CSV = APP_DIR / "diabetes.csv"
LOCAL_DB = DATA_DIR / "sistema_diabetes_v8.db"

APP_TITLE = "Sistema inteligente de apoyo al tamizaje del riesgo de diabetes"
APP_SHORT_TITLE = "Diabetes UNAMAD V8"
APP_VERSION = "8.0.0"
MODEL_VERSION = "V8-RF-2026-08"

# Paleta clínica V8: azul hospitalario más profundo, blanco y acentos cian.
HOSPITAL_NAVY = "#062B49"
HOSPITAL_BLUE = "#075E91"
HOSPITAL_CYAN = "#0A8FC2"
HOSPITAL_SKY = "#CFEAF6"
HOSPITAL_PALE = "#EEF7FB"
HOSPITAL_TEAL = "#087C89"
INK = "#0A2940"
MUTED = "#496879"
LINE = "#BFDCE8"
WHITE = "#FFFFFF"

# Alias para compatibilidad con componentes existentes.
UNAMAD_GREEN = HOSPITAL_BLUE
UNAMAD_DARK = HOSPITAL_NAVY
UNAMAD_GOLD = "#F3B53F"
UNAMAD_MINT = HOSPITAL_SKY
SOFT_BG = HOSPITAL_PALE
BLUE = HOSPITAL_BLUE

ROLE_LABELS = {
    "nurse": "Enfermería",
    "doctor": "Médico",
    "admin": "Administrador",
}

ROLE_PREFIXES = {
    "nurse": "enfermeria",
    "doctor": "medico",
    "admin": "administrador",
}

STATUS_LABELS = {
    "PENDING": "Pendiente de revisión",
    "REVIEWED": "Revisado",
    "CORRECTION": "Requiere corrección",
    "FOLLOW_UP": "Requiere seguimiento",
    "CLOSED": "Cerrado",
    "NO_REVIEW": "Sin derivación médica",
    "HISTORICAL": "Registro histórico",
}

ORIGINAL_COLUMNS = [
    "id", "chol", "stab.glu", "hdl", "ratio", "glyhb", "location", "age",
    "gender", "height", "weight", "frame", "bp.1s", "bp.1d", "bp.2s",
    "bp.2d", "waist", "hip", "time.ppn",
]

# glyhb construye la clase objetivo, pero no entra como predictor del Random
# Forest para evitar fuga de información. El motor de reglas sí puede usarla.
MODEL_FEATURES = [
    "chol", "stab.glu", "hdl", "ratio", "age", "gender", "height", "weight",
    "frame", "bp.1s", "bp.1d", "bp.2s", "bp.2d", "waist", "hip", "time.ppn",
]
NUMERIC_FEATURES = [
    "chol", "stab.glu", "hdl", "ratio", "age", "height", "weight", "bp.1s",
    "bp.1d", "bp.2s", "bp.2d", "waist", "hip", "time.ppn",
]
CATEGORICAL_FEATURES = ["gender", "frame"]

ALERT_COLORS = {"BAJO": "#138A72", "MEDIO": "#D28B00", "ALTO": "#C84646"}

DISCLAIMER = (
    "Herramienta de apoyo al tamizaje. La alerta no confirma ni descarta diabetes "
    "y no sustituye una evaluación médica profesional."
)

PUBLIC_NOTICE = (
    "La consulta pública es temporal: no crea una historia clínica ni almacena la "
    "información ingresada en la base oficial."
)

AUTH_MAX_ATTEMPTS = 5
AUTH_LOCK_MINUTES = 5
