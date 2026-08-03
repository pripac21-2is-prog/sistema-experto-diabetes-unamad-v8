from __future__ import annotations

import json
import math
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .config import AUTH_LOCK_MINUTES, AUTH_MAX_ATTEMPTS, LOCAL_CSV, LOCAL_DB, ROLE_LABELS, ROLE_PREFIXES
from .security import hash_password, normalize_username, verify_password
from .expert_system import evaluate_rules, hybrid_decision


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_iso(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: _as_iso(value) for key, value in payload.items()}


def _bounded_text(
    value: Any,
    label: str,
    *,
    required: bool = False,
    min_length: int = 0,
    max_length: int = 200,
    collapse_spaces: bool = True,
) -> str:
    text = str(value or "").strip()
    if collapse_spaces:
        text = " ".join(text.split())
    if required and len(text) < max(1, min_length):
        raise ValueError(f"{label} es obligatorio.")
    if text and len(text) < min_length:
        raise ValueError(f"{label} debe tener al menos {min_length} caracteres.")
    if len(text) > max_length:
        raise ValueError(f"{label} no puede superar {max_length} caracteres.")
    return text


@dataclass(frozen=True)
class DatabaseStatus:
    mode: str
    persistent: bool
    label: str
    detail: str


@dataclass(frozen=True)
class AuthResult:
    user: dict[str, Any] | None
    message: str
    locked_seconds: int = 0


SQLITE_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('nurse','doctor','admin')),
    display_name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    last_login TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    document_number TEXT,
    first_names TEXT NOT NULL,
    last_names TEXT NOT NULL,
    gender TEXT NOT NULL CHECK(gender IN ('female','male')),
    birth_date TEXT,
    phone TEXT,
    department TEXT NOT NULL DEFAULT 'Madre de Dios',
    province TEXT NOT NULL DEFAULT 'Tambopata',
    district TEXT NOT NULL DEFAULT 'Tambopata',
    city TEXT NOT NULL DEFAULT 'Puerto Maldonado',
    frame TEXT NOT NULL CHECK(frame IN ('small','medium','large')),
    height_cm REAL NOT NULL CHECK(height_cm BETWEEN 80 AND 230),
    weight_kg REAL NOT NULL CHECK(weight_kg BETWEEN 20 AND 350),
    notes TEXT,
    source TEXT NOT NULL DEFAULT 'OFFICIAL' CHECK(source IN ('OFFICIAL','HISTORICAL_CSV')),
    source_record_id TEXT,
    synthetic_identity INTEGER NOT NULL DEFAULT 0,
    request_key TEXT UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_document
ON patients(document_number) WHERE document_number IS NOT NULL AND document_number <> '';
CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(last_names, first_names);

CREATE TABLE IF NOT EXISTS evaluations (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id),
    nurse_user_id TEXT NOT NULL REFERENCES users(id),
    location_text TEXT NOT NULL,
    age REAL NOT NULL CHECK(age BETWEEN 0 AND 120),
    gender TEXT NOT NULL,
    height_cm REAL NOT NULL,
    weight_kg REAL NOT NULL,
    frame TEXT NOT NULL,
    chol REAL NOT NULL CHECK(chol BETWEEN 40 AND 800),
    stab_glu REAL NOT NULL CHECK(stab_glu BETWEEN 30 AND 700),
    hdl REAL NOT NULL CHECK(hdl BETWEEN 5 AND 250),
    ratio REAL NOT NULL CHECK(ratio BETWEEN 0.1 AND 50),
    glyhb REAL NOT NULL CHECK(glyhb BETWEEN 2 AND 25),
    bp1s REAL NOT NULL CHECK(bp1s BETWEEN 50 AND 300),
    bp1d REAL NOT NULL CHECK(bp1d BETWEEN 30 AND 200),
    bp2s REAL NOT NULL CHECK(bp2s BETWEEN 50 AND 300),
    bp2d REAL NOT NULL CHECK(bp2d BETWEEN 30 AND 200),
    waist_cm REAL NOT NULL CHECK(waist_cm BETWEEN 30 AND 250),
    hip_cm REAL NOT NULL CHECK(hip_cm BETWEEN 30 AND 250),
    time_ppn REAL NOT NULL CHECK(time_ppn BETWEEN 0 AND 1440),
    alert_level TEXT NOT NULL CHECK(alert_level IN ('BAJO','MEDIO','ALTO')),
    rule_score INTEGER NOT NULL,
    ml_probability REAL,
    model_name TEXT,
    model_version TEXT,
    rules_json TEXT NOT NULL,
    explanation TEXT NOT NULL,
    nursing_notes TEXT,
    source TEXT NOT NULL DEFAULT 'OFFICIAL' CHECK(source IN ('OFFICIAL','HISTORICAL_CSV')),
    data_quality TEXT NOT NULL DEFAULT 'COMPLETE',
    request_key TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK(status IN ('PENDING','REVIEWED','CORRECTION','FOLLOW_UP','CLOSED','NO_REVIEW','HISTORICAL')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evaluations_patient ON evaluations(patient_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_status ON evaluations(status);
CREATE INDEX IF NOT EXISTS idx_evaluations_created ON evaluations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evaluations_alert ON evaluations(alert_level);

CREATE TABLE IF NOT EXISTS medical_reviews (
    id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL REFERENCES evaluations(id),
    doctor_user_id TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL CHECK(status IN ('REVIEWED','CORRECTION','FOLLOW_UP','CLOSED')),
    observation TEXT NOT NULL,
    conclusion TEXT NOT NULL DEFAULT 'NO_CONCLUSION',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_evaluation ON medical_reviews(evaluation_id, created_at DESC);

CREATE TABLE IF NOT EXISTS patient_notes (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id),
    doctor_user_id TEXT NOT NULL REFERENCES users(id),
    note_type TEXT NOT NULL CHECK(note_type IN ('GENERAL','FOLLOW_UP','REFERRAL','NUTRITION','CARDIOLOGY','LABORATORY')),
    referral_area TEXT,
    observation TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patient_notes_patient ON patient_notes(patient_id, created_at DESC);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    username TEXT,
    role TEXT,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id TEXT,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);
"""


class SQLiteRepository:
    """Repository used by the academic prototype.

    It is fully functional on a local computer. On Streamlit Community Cloud the
    file can be recreated when the app container is rebooted, so the administrator
    panel provides explicit CSV and SQLite backups.
    """

    def __init__(self, path: Path = LOCAL_DB) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.status = DatabaseStatus(
            mode="sqlite",
            persistent=True,
            label="SQLite local",
            detail="Base local activa con exportaciones y respaldos disponibles en Administración.",
        )
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(SQLITE_SCHEMA)
        self._seed_users()
        self._seed_historical_dataset()

    def _seed_users(self) -> None:
        demo_users = [
            ("enfermeria1", "nurse", "Enfermería 1"),
            ("enfermeria2", "nurse", "Enfermería 2"),
            ("enfermeria3", "nurse", "Enfermería 3"),
            ("medico1", "doctor", "Médico 1"),
            ("medico2", "doctor", "Médico 2"),
            ("medico3", "doctor", "Médico 3"),
            ("administrador1", "admin", "Administrador 1"),
            ("administrador2", "admin", "Administrador 2"),
        ]
        now = utc_now()
        with self._connect() as connection:
            for username, role, display_name in demo_users:
                exists = connection.execute(
                    "SELECT 1 FROM users WHERE username=?", (username,)
                ).fetchone()
                if exists:
                    continue
                connection.execute(
                    """INSERT INTO users
                    (id, username, password_hash, role, display_name, active,
                     must_change_password, failed_attempts, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, 0, 0, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        username,
                        hash_password(username),
                        role,
                        display_name,
                        now,
                        now,
                    ),
                )

    def _seed_historical_dataset(self) -> None:
        """Load the 403-row academic CSV once as a read-only historical cohort.

        The names are deterministic fictional identities created only to make search
        and navigation realistic. They do not correspond to the original people.
        Rows without glyhb remain as patient records but do not create an evaluation.
        """
        if not Path(LOCAL_CSV).exists():
            return
        with self._connect() as connection:
            existing = int(connection.execute(
                "SELECT COUNT(*) FROM patients WHERE source='HISTORICAL_CSV'"
            ).fetchone()[0])
            if existing:
                return
            nurse = connection.execute(
                "SELECT id FROM users WHERE username='enfermeria1'"
            ).fetchone()
            if not nurse:
                return

        frame = pd.read_csv(LOCAL_CSV)
        frame.columns = [str(column).strip() for column in frame.columns]
        numeric = [
            'chol','stab.glu','hdl','ratio','glyhb','age','height','weight',
            'bp.1s','bp.1d','bp.2s','bp.2d','waist','hip','time.ppn'
        ]
        for column in numeric:
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors='coerce')
        medians = frame[numeric].median(numeric_only=True).to_dict()

        first_names = [
            'Andrea','Beatriz','Camila','Daniela','Elena','Fiorella','Gabriela','Helena',
            'Isabel','Jimena','Karen','Lucía','Mariela','Natalia','Olga','Patricia',
            'Rosa','Sofía','Teresa','Valeria','Alberto','Bruno','Carlos','Diego',
            'Eduardo','Fernando','Gustavo','Héctor','Iván','Jorge','Luis','Miguel',
            'Nicolás','Óscar','Pedro','Raúl','Sergio','Víctor'
        ]
        last_names = [
            'Achahuanco','Aguirre','Alarcón','Apaza','Cárdenas','Castillo','Challco','Condori',
            'Cruz','Delgado','Flores','García','Gonzales','Huamán','Mamani','Medina',
            'Mendoza','Núñez','Ortiz','Palomino','Paredes','Quispe','Ramos','Ripa',
            'Rodríguez','Salazar','Sánchez','Silva','Soto','Torres','Vargas','Yupanqui'
        ]

        now = utc_now()
        patient_rows: list[tuple[Any, ...]] = []
        evaluation_rows: list[tuple[Any, ...]] = []
        for index, source_row in frame.iterrows():
            record_id = str(source_row.get('id', index + 1))
            patient_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'unamad-diabetes-patient-{record_id}'))
            evaluation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'unamad-diabetes-evaluation-{record_id}'))
            gender_raw = str(source_row.get('gender', 'female')).strip().lower()
            gender = 'male' if gender_raw.startswith('m') else 'female'
            first_pool = first_names[20:] if gender == 'male' else first_names[:20]
            first_name = first_pool[index % len(first_pool)]
            last_name = f"{last_names[(index // len(first_pool)) % len(last_names)]} {last_names[(index * 7 + 3) % len(last_names)]}"
            age = int(float(source_row.get('age') if pd.notna(source_row.get('age')) else medians.get('age', 45)))
            birth_year = max(1900, datetime.now().year - age)
            height_in = float(source_row.get('height') if pd.notna(source_row.get('height')) else medians.get('height', 65))
            weight_lb = float(source_row.get('weight') if pd.notna(source_row.get('weight')) else medians.get('weight', 160))
            height_cm = round(height_in * 2.54, 1)
            weight_kg = round(weight_lb / 2.2046226218, 1)
            frame_value = str(source_row.get('frame', '')).strip().lower()
            frame_code = {'small':'small','medium':'medium','large':'large'}.get(frame_value, 'medium')
            location = str(source_row.get('location', 'Dataset histórico')).strip()
            # Fechas de carga organizadas en lotes: 3 registros el 03/08/2026 y
            # bloques de 50 por día desde el 02/08/2026 hacia atrás.
            if index < 3:
                registration_date = datetime(2026, 8, 3, 8, 0 + index * 10, tzinfo=timezone(timedelta(hours=-5)))
            else:
                batch = (index - 3) // 50
                day = datetime(2026, 8, 2, 8, 0, tzinfo=timezone(timedelta(hours=-5))) - timedelta(days=batch)
                position = (index - 3) % 50
                registration_date = day.replace(hour=8 + position // 10, minute=(position % 10) * 5)
            registration_text = registration_date.isoformat()
            patient_rows.append((
                patient_id, f'HIS-{record_id}', None, first_name, last_name, gender,
                f'{birth_year:04d}-01-01', '', 'Dataset académico', location,
                location, location, frame_code, height_cm, weight_kg,
                'Registro de referencia vinculado a una fila histórica del diabetes.csv.',
                'HISTORICAL_CSV', record_id, 1, f'historical-patient-{record_id}',
                1, nurse[0], registration_text, registration_text,
            ))

            if pd.isna(source_row.get('glyhb')):
                continue
            missing_predictors = [column for column in numeric if column != 'glyhb' and pd.isna(source_row.get(column))]
            def value(column: str) -> float:
                raw = source_row.get(column)
                return float(raw if pd.notna(raw) else medians.get(column, 0.0))
            bp1s = value('bp.1s'); bp1d = value('bp.1d')
            bp2s = value('bp.2s') if pd.notna(source_row.get('bp.2s')) else bp1s
            bp2d = value('bp.2d') if pd.notna(source_row.get('bp.2d')) else bp1d
            waist_cm = round(value('waist') * 2.54, 1)
            hip_cm = round(value('hip') * 2.54, 1)
            values = {
                'age': age, 'gender': gender, 'height_cm': height_cm, 'weight_kg': weight_kg,
                'frame': frame_code, 'chol': value('chol'), 'stab_glu': value('stab.glu'),
                'hdl': value('hdl'), 'ratio': value('ratio'), 'glyhb': value('glyhb'),
                'bp1s': bp1s, 'bp1d': bp1d, 'bp2s': bp2s, 'bp2d': bp2d,
                'waist_cm': waist_cm, 'hip_cm': hip_cm, 'time_ppn': min(1440.0, max(0.0, value('time.ppn'))),
            }
            expert = evaluate_rules(values)
            alert = expert.level
            explanation = (
                'Registro histórico del conjunto diabetes.csv, identificado mediante código HIS. '
                'La alerta corresponde al motor híbrido y su versión queda registrada para trazabilidad.'
            )
            quality = 'ORIGINAL' if not missing_predictors else 'IMPUTED: ' + ', '.join(missing_predictors)
            evaluation_rows.append((
                evaluation_id, patient_id, nurse[0], f'{location} · conjunto histórico',
                age, gender, height_cm, weight_kg, frame_code, value('chol'), value('stab.glu'),
                value('hdl'), value('ratio'), value('glyhb'), bp1s, bp1d, bp2s, bp2d,
                waist_cm, hip_cm, min(1440.0, max(0.0, value('time.ppn'))), alert, int(expert.score), None,
                'Cohorte histórica', 'CSV-403', json.dumps(expert.to_dict(), ensure_ascii=False),
                explanation, 'Importado automáticamente desde diabetes.csv.',
                'HISTORICAL_CSV', quality, f'historical-evaluation-{record_id}',
                'PENDING' if alert in {'MEDIO','ALTO'} else 'NO_REVIEW', registration_text, registration_text,
            ))

        with self._connect() as connection:
            connection.executemany(
                """INSERT INTO patients
                (id,code,document_number,first_names,last_names,gender,birth_date,phone,
                 department,province,district,city,frame,height_cm,weight_kg,notes,
                 source,source_record_id,synthetic_identity,request_key,active,created_by,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                patient_rows,
            )
            connection.executemany(
                """INSERT INTO evaluations
                (id,patient_id,nurse_user_id,location_text,age,gender,height_cm,weight_kg,frame,
                 chol,stab_glu,hdl,ratio,glyhb,bp1s,bp1d,bp2s,bp2d,waist_cm,hip_cm,time_ppn,
                 alert_level,rule_score,ml_probability,model_name,model_version,rules_json,
                 explanation,nursing_notes,source,data_quality,request_key,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                evaluation_rows,
            )

    # ------------------------------------------------------------------
    # Auditing and authentication
    # ------------------------------------------------------------------
    def audit(
        self,
        user: dict[str, Any] | None,
        action: str,
        entity: str,
        entity_id: str | None = None,
        detail: dict[str, Any] | None = None,
        *,
        username_override: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO audit_logs
                (id, user_id, username, role, action, entity, entity_id, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    user.get("id") if user else None,
                    user.get("username") if user else username_override,
                    user.get("role") if user else None,
                    action,
                    entity,
                    entity_id,
                    json.dumps(detail or {}, ensure_ascii=False, default=str),
                    utc_now(),
                ),
            )

    def authenticate(self, username: str, password: str) -> AuthResult:
        normalized = normalize_username(username)
        audit_user: dict[str, Any] | None = None
        audit_action = "LOGIN_FAILED"
        audit_detail: dict[str, Any] = {}
        result: AuthResult

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE username=?", (normalized,)
            ).fetchone()
            if not row:
                result = AuthResult(None, "Usuario o contraseña incorrectos.")
                audit_detail = {"reason": "unknown_user"}
            else:
                user = dict(row)
                audit_user = dict(user)
                audit_user.pop("password_hash", None)

                if not int(user.get("active", 0)):
                    result = AuthResult(None, "La cuenta está desactivada. Contacte al administrador.")
                    audit_action = "LOGIN_BLOCKED"
                    audit_detail = {"reason": "inactive"}
                else:
                    locked = False
                    locked_until_text = user.get("locked_until")
                    if locked_until_text:
                        try:
                            locked_until = datetime.fromisoformat(str(locked_until_text))
                            now = datetime.now(timezone.utc)
                            if locked_until > now:
                                seconds = max(1, int((locked_until - now).total_seconds()))
                                result = AuthResult(
                                    None,
                                    "Cuenta bloqueada temporalmente por varios intentos fallidos.",
                                    seconds,
                                )
                                audit_action = "LOGIN_BLOCKED"
                                audit_detail = {"reason": "temporary_lock"}
                                locked = True
                        except ValueError:
                            pass

                    if not locked:
                        check = verify_password(password, str(user["password_hash"]))
                        if not check.valid:
                            attempts = int(user.get("failed_attempts") or 0) + 1
                            lock_until: str | None = None
                            if attempts >= AUTH_MAX_ATTEMPTS:
                                lock_until = (
                                    datetime.now(timezone.utc)
                                    + timedelta(minutes=AUTH_LOCK_MINUTES)
                                ).isoformat()
                                attempts = 0
                            connection.execute(
                                "UPDATE users SET failed_attempts=?, locked_until=?, updated_at=? WHERE id=?",
                                (attempts, lock_until, utc_now(), user["id"]),
                            )
                            audit_detail = {"reason": "bad_password"}
                            if lock_until:
                                result = AuthResult(
                                    None,
                                    f"Cuenta bloqueada por {AUTH_LOCK_MINUTES} minutos.",
                                    AUTH_LOCK_MINUTES * 60,
                                )
                            else:
                                remaining = AUTH_MAX_ATTEMPTS - attempts
                                result = AuthResult(
                                    None,
                                    f"Usuario o contraseña incorrectos. Intentos restantes: {remaining}.",
                                )
                        else:
                            updates: dict[str, Any] = {
                                "failed_attempts": 0,
                                "locked_until": None,
                                "last_login": utc_now(),
                                "updated_at": utc_now(),
                            }
                            if check.needs_rehash:
                                updates["password_hash"] = hash_password(password)
                            assignments = ",".join(f"{key}=?" for key in updates)
                            connection.execute(
                                f"UPDATE users SET {assignments} WHERE id=?",
                                [*updates.values(), user["id"]],
                            )
                            clean_user = dict(user)
                            clean_user.pop("password_hash", None)
                            clean_user.update({
                                "failed_attempts": 0,
                                "locked_until": None,
                                "last_login": updates["last_login"],
                                "role_label": ROLE_LABELS.get(
                                    str(user.get("role")), str(user.get("role"))
                                ),
                            })
                            result = AuthResult(clean_user, "Acceso correcto.")
                            audit_action = "LOGIN_SUCCESS"

        self.audit(
            audit_user if audit_user else result.user,
            audit_action,
            "session",
            detail=audit_detail,
            username_override=normalized if audit_user is None and result.user is None else None,
        )
        return result

    def list_users(self, include_inactive: bool = True) -> list[dict[str, Any]]:
        query = "SELECT id, username, role, display_name, active, must_change_password, failed_attempts, locked_until, last_login, created_at FROM users"
        if not include_inactive:
            query += " WHERE active=1"
        query += " ORDER BY role, username"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query).fetchall()]

    def create_user(
        self,
        username: str,
        password: str,
        role: str,
        display_name: str,
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        if actor.get("role") != "admin":
            raise PermissionError("Solo administración puede crear usuarios.")
        username = normalize_username(username)
        if role not in ROLE_LABELS:
            raise ValueError("Rol no válido.")
        if len(username) < 4:
            raise ValueError("El usuario debe tener al menos 4 caracteres.")
        if len(username) > 40:
            raise ValueError("El usuario no puede superar 40 caracteres.")
        if not isinstance(password, str) or not (7 <= len(password) <= 128):
            raise ValueError("La contraseña debe tener entre 7 y 128 caracteres.")
        display_name = _bounded_text(
            display_name or username, "Nombre mostrado", required=True, min_length=2, max_length=80
        )
        expected_prefix = ROLE_PREFIXES[role]
        if not username.startswith(expected_prefix):
            raise ValueError(
                f"Para el rol {ROLE_LABELS[role]}, el usuario debe comenzar con '{expected_prefix}'."
            )
        suffix = username[len(expected_prefix):]
        if not suffix or not all(char.isalnum() or char == "_" for char in suffix):
            raise ValueError(
                f"Use un identificador como {expected_prefix}4 o {expected_prefix}_apellido."
            )
        now = utc_now()
        row = {
            "id": str(uuid.uuid4()),
            "username": username,
            "password_hash": hash_password(password),
            "role": role,
            "display_name": display_name,
            "active": 1,
            "must_change_password": 0,
            "failed_attempts": 0,
            "created_by": actor.get("id"),
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as connection:
            try:
                connection.execute(
                    """INSERT INTO users
                    (id, username, password_hash, role, display_name, active,
                     must_change_password, failed_attempts, created_by, created_at, updated_at)
                    VALUES (:id,:username,:password_hash,:role,:display_name,:active,
                            :must_change_password,:failed_attempts,:created_by,:created_at,:updated_at)""",
                    row,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Ese nombre de usuario ya existe.") from exc
        self.audit(actor, "CREATE", "user", row["id"], {"username": username, "role": role})
        result = dict(row)
        result.pop("password_hash", None)
        return result

    def reset_user_password(
        self, user_id: str, new_password: str, actor: dict[str, Any]
    ) -> None:
        if actor.get("role") != "admin":
            raise PermissionError("Solo administración puede restablecer contraseñas.")
        if not isinstance(new_password, str) or not (7 <= len(new_password) <= 128):
            raise ValueError("La contraseña debe tener entre 7 y 128 caracteres.")
        with self._connect() as connection:
            target = connection.execute(
                "SELECT username FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if not target:
                raise ValueError("Usuario no encontrado.")
            connection.execute(
                """UPDATE users SET password_hash=?, failed_attempts=0, locked_until=NULL,
                updated_at=? WHERE id=?""",
                (hash_password(new_password), utc_now(), user_id),
            )
        self.audit(actor, "RESET_PASSWORD", "user", user_id, {"username": target["username"]})

    def set_user_active(self, user_id: str, active: bool, actor: dict[str, Any]) -> None:
        if actor.get("role") != "admin":
            raise PermissionError("Solo administración puede activar o desactivar usuarios.")
        if user_id == actor.get("id") and not active:
            raise ValueError("No puede desactivar su propia sesión.")
        with self._connect() as connection:
            target = connection.execute(
                "SELECT username FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if not target:
                raise ValueError("Usuario no encontrado.")
            connection.execute(
                "UPDATE users SET active=?, updated_at=? WHERE id=?",
                (1 if active else 0, utc_now(), user_id),
            )
        self.audit(actor, "ACTIVATE" if active else "DEACTIVATE", "user", user_id, {"username": target["username"]})

    # ------------------------------------------------------------------
    # Patients
    # ------------------------------------------------------------------
    def _next_patient_code(self, connection: sqlite3.Connection) -> str:
        row = connection.execute(
            """SELECT MAX(CAST(SUBSTR(code, 5) AS INTEGER))
               FROM patients WHERE code GLOB 'PAC-[0-9]*'"""
        ).fetchone()
        next_number = int(row[0] or 0) + 1
        return f"PAC-{next_number:04d}"

    def create_patient(self, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        if actor.get("role") != "nurse":
            raise PermissionError("Solo enfermería puede registrar pacientes oficiales.")
        row = clean_payload(payload)
        row["first_names"] = _bounded_text(
            row.get("first_names"), "Nombres", required=True, min_length=2, max_length=80
        )
        row["last_names"] = _bounded_text(
            row.get("last_names"), "Apellidos", required=True, min_length=2, max_length=100
        )
        document = _bounded_text(row.get("document_number"), "Documento", max_length=25)
        row["document_number"] = document or None
        row["phone"] = _bounded_text(row.get("phone"), "Teléfono", max_length=25)
        for key, label in [
            ("department", "Departamento"), ("province", "Provincia"),
            ("district", "Distrito"), ("city", "Ciudad"),
        ]:
            row[key] = _bounded_text(row.get(key), label, required=True, min_length=2, max_length=80)
        row["notes"] = _bounded_text(
            row.get("notes"), "Observaciones", max_length=1500, collapse_spaces=False
        )
        birth_text = str(row.get("birth_date") or "").strip()
        if birth_text:
            try:
                birth = date.fromisoformat(birth_text)
            except ValueError as exc:
                raise ValueError("La fecha de nacimiento no es válida.") from exc
            if birth > date.today():
                raise ValueError("La fecha de nacimiento no puede estar en el futuro.")
            if birth < date.today().replace(year=date.today().year - 120):
                raise ValueError("La fecha de nacimiento supera el rango permitido de 120 años.")
        now = utc_now()
        row.update({
            "id": str(uuid.uuid4()),
            "created_by": actor["id"],
            "created_at": now,
            "updated_at": now,
            "active": 1,
            "source": "OFFICIAL",
            "source_record_id": None,
            "synthetic_identity": 0,
        })
        request_key = str(row.get("request_key") or "").strip() or None
        row["request_key"] = request_key
        with self._connect() as connection:
            if request_key:
                previous = connection.execute(
                    "SELECT * FROM patients WHERE request_key=?", (request_key,)
                ).fetchone()
                if previous:
                    return dict(previous)
            similar = connection.execute(
                """SELECT * FROM patients
                   WHERE source='OFFICIAL' AND active=1
                     AND lower(trim(first_names))=lower(trim(?))
                     AND lower(trim(last_names))=lower(trim(?))
                     AND COALESCE(birth_date,'')=COALESCE(?, '')
                   LIMIT 1""",
                (row.get("first_names", ""), row.get("last_names", ""), row.get("birth_date")),
            ).fetchone()
            if similar:
                raise ValueError(
                    f"Ya existe un paciente similar con código {similar['code']}. "
                    "Revise el directorio antes de crear otro registro."
                )
            row.setdefault("code", self._next_patient_code(connection))
            try:
                connection.execute(
                    """INSERT INTO patients
                    (id, code, document_number, first_names, last_names, gender,
                     birth_date, phone, department, province, district, city, frame,
                     height_cm, weight_kg, notes, source, source_record_id, synthetic_identity,
                     request_key, active, created_by, created_at, updated_at)
                    VALUES (:id,:code,:document_number,:first_names,:last_names,:gender,
                            :birth_date,:phone,:department,:province,:district,:city,:frame,
                            :height_cm,:weight_kg,:notes,:source,:source_record_id,:synthetic_identity,
                            :request_key,:active,:created_by,:created_at,:updated_at)""",
                    row,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("El documento, código o solicitud ya está registrado.") from exc
        self.audit(actor, "CREATE", "patient", row["id"], {"code": row["code"]})
        return row

    def update_patient(self, patient_id: str, payload: dict[str, Any], actor: dict[str, Any]) -> None:
        if actor.get("role") not in {"nurse", "doctor"}:
            raise PermissionError("Solo enfermería o medicina pueden actualizar la ficha del paciente.")
        with self._connect() as connection:
            patient = connection.execute(
                "SELECT source FROM patients WHERE id=?", (patient_id,)
            ).fetchone()
        if not patient:
            raise ValueError("Paciente no encontrado.")
        if patient["source"] != "OFFICIAL" and actor.get("role") != "doctor":
            raise PermissionError("Los registros históricos solo pueden ser actualizados por medicina.")
        allowed = {
            "document_number", "first_names", "last_names", "gender", "birth_date",
            "phone", "department", "province", "district", "city", "frame",
            "height_cm", "weight_kg", "notes", "active",
        }
        row = {key: _as_iso(value) for key, value in payload.items() if key in allowed}
        if not row:
            raise ValueError("No se recibieron campos válidos para actualizar.")
        text_rules = {
            "first_names": ("Nombres", True, 2, 80),
            "last_names": ("Apellidos", True, 2, 100),
            "document_number": ("Documento", False, 0, 25),
            "phone": ("Teléfono", False, 0, 25),
            "department": ("Departamento", True, 2, 80),
            "province": ("Provincia", True, 2, 80),
            "district": ("Distrito", True, 2, 80),
            "city": ("Ciudad", True, 2, 80),
        }
        for key, (label, required, minimum, maximum) in text_rules.items():
            if key in row:
                cleaned = _bounded_text(
                    row[key], label, required=required, min_length=minimum, max_length=maximum
                )
                row[key] = (cleaned or None) if key == "document_number" else cleaned
        if "notes" in row:
            row["notes"] = _bounded_text(
                row["notes"], "Observaciones", max_length=1500, collapse_spaces=False
            )
        if "birth_date" in row and row["birth_date"]:
            try:
                birth = date.fromisoformat(str(row["birth_date"]))
            except ValueError as exc:
                raise ValueError("La fecha de nacimiento no es válida.") from exc
            if birth > date.today():
                raise ValueError("La fecha de nacimiento no puede estar en el futuro.")
        row["updated_at"] = utc_now()
        assignments = ",".join(f"{key}=?" for key in row)
        with self._connect() as connection:
            try:
                connection.execute(
                    f"UPDATE patients SET {assignments} WHERE id=?",
                    [*row.values(), patient_id],
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("El documento o código ya pertenece a otro paciente.") from exc
        self.audit(actor, "UPDATE", "patient", patient_id, {"fields": sorted(row)})

    def list_patients(
        self, *, search: str = "", include_inactive: bool = False,
        source: str | None = None, limit: int = 500, offset: int = 0
    ) -> list[dict[str, Any]]:
        query = """
        SELECT p.*,
               u.username AS created_by_username,
               (SELECT COUNT(*) FROM evaluations e WHERE e.patient_id=p.id) AS evaluation_count,
               (SELECT MAX(e.created_at) FROM evaluations e WHERE e.patient_id=p.id) AS last_evaluation,
               (SELECT e.alert_level FROM evaluations e WHERE e.patient_id=p.id ORDER BY e.created_at DESC LIMIT 1) AS last_alert
        FROM patients p
        LEFT JOIN users u ON u.id=p.created_by
        WHERE 1=1
        """
        params: list[Any] = []
        if not include_inactive:
            query += " AND p.active=1"
        if source:
            query += " AND p.source=?"
            params.append(source)
        if search.strip():
            token = f"%{search.strip()}%"
            query += " AND (p.code LIKE ? OR p.document_number LIKE ? OR p.first_names LIKE ? OR p.last_names LIKE ? OR (p.first_names || ' ' || p.last_names) LIKE ?)"
            params.extend([token, token, token, token, token])
        query += " ORDER BY p.created_at DESC, p.code ASC LIMIT ? OFFSET ?"
        params.extend([max(1, min(int(limit), 100000)), max(0, int(offset))])
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def get_patient(self, patient_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
            return dict(row) if row else None

    def count_patients(self, *, search: str = "", source: str | None = None, include_inactive: bool = False) -> int:
        query = "SELECT COUNT(*) FROM patients WHERE 1=1"
        params: list[Any] = []
        if not include_inactive:
            query += " AND active=1"
        if source:
            query += " AND source=?"
            params.append(source)
        if search.strip():
            token = f"%{search.strip()}%"
            query += " AND (code LIKE ? OR document_number LIKE ? OR first_names LIKE ? OR last_names LIKE ? OR (first_names || ' ' || last_names) LIKE ?)"
            params.extend([token, token, token, token, token])
        with self._connect() as connection:
            return int(connection.execute(query, params).fetchone()[0])

    # ------------------------------------------------------------------
    # Evaluations and reviews
    # ------------------------------------------------------------------
    def create_evaluation(self, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        if actor.get("role") != "nurse":
            raise PermissionError("Solo enfermería puede registrar evaluaciones oficiales.")
        row = clean_payload(payload)
        numeric_fields = [
            "age", "height_cm", "weight_kg", "chol", "stab_glu", "hdl", "ratio",
            "glyhb", "bp1s", "bp1d", "bp2s", "bp2d", "waist_cm", "hip_cm",
            "time_ppn", "rule_score",
        ]
        for field in numeric_fields:
            try:
                number = float(row[field])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"El campo {field} debe ser numérico.") from exc
            if not math.isfinite(number):
                raise ValueError(f"El campo {field} contiene un valor no válido.")
        if row.get("ml_probability") is not None:
            probability = float(row["ml_probability"])
            if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
                raise ValueError("La probabilidad del modelo debe estar entre 0 y 1.")
        row["nursing_notes"] = _bounded_text(
            row.get("nursing_notes"), "Observación de enfermería", max_length=2000, collapse_spaces=False
        )
        row["location_text"] = _bounded_text(
            row.get("location_text"), "Ubicación", required=True, min_length=2, max_length=250
        )
        with self._connect() as connection:
            patient = connection.execute(
                "SELECT source, active FROM patients WHERE id=?", (row.get("patient_id"),)
            ).fetchone()
        if not patient:
            raise ValueError("Paciente no encontrado.")
        if patient["source"] != "OFFICIAL":
            raise PermissionError("No se pueden crear evaluaciones oficiales sobre registros históricos.")
        if not int(patient["active"]):
            raise ValueError("El paciente está desactivado.")
        now = utc_now()
        row.update({
            "id": str(uuid.uuid4()),
            "nurse_user_id": actor["id"],
            "status": "PENDING" if str(row.get("alert_level")) in {"MEDIO", "ALTO"} else "NO_REVIEW",
            "source": "OFFICIAL",
            "data_quality": "COMPLETE",
            "created_at": now,
            "updated_at": now,
        })
        row["request_key"] = str(row.get("request_key") or "").strip() or None
        columns = [
            "id", "patient_id", "nurse_user_id", "location_text", "age", "gender",
            "height_cm", "weight_kg", "frame", "chol", "stab_glu", "hdl", "ratio",
            "glyhb", "bp1s", "bp1d", "bp2s", "bp2d", "waist_cm", "hip_cm",
            "time_ppn", "alert_level", "rule_score", "ml_probability", "model_name",
            "model_version", "rules_json", "explanation", "nursing_notes", "source",
            "data_quality", "request_key", "status", "created_at", "updated_at",
        ]
        missing = [column for column in columns if column not in row]
        if missing:
            raise ValueError("Faltan campos de evaluación: " + ", ".join(missing))
        with self._connect() as connection:
            if row.get("request_key"):
                previous = connection.execute(
                    "SELECT * FROM evaluations WHERE request_key=?", (row["request_key"],)
                ).fetchone()
                if previous:
                    return dict(previous)
            try:
                connection.execute(
                    f"INSERT INTO evaluations ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                    [row[column] for column in columns],
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("La evaluación ya fue registrada o contiene datos inválidos.") from exc
        self.audit(actor, "CREATE", "evaluation", row["id"], {
            "patient_id": row["patient_id"],
            "alert": row["alert_level"],
            "status": row["status"],
        })
        return row

    def list_evaluations(
        self,
        *,
        status: str | None = None,
        statuses: Iterable[str] | None = None,
        patient_id: str | None = None,
        nurse_user_id: str | None = None,
        evaluation_id: str | None = None,
        search: str = "",
        source: str | None = None,
        alert_levels: Iterable[str] | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = """
        SELECT e.*,
               p.code AS patient_code,
               p.first_names,
               p.last_names,
               p.document_number,
               p.source AS patient_source,
               p.synthetic_identity,
               n.username AS nurse_username,
               n.display_name AS nurse_name,
               (SELECT mr.observation FROM medical_reviews mr WHERE mr.evaluation_id=e.id ORDER BY mr.created_at DESC LIMIT 1) AS last_medical_observation,
               (SELECT d.display_name FROM medical_reviews mr JOIN users d ON d.id=mr.doctor_user_id WHERE mr.evaluation_id=e.id ORDER BY mr.created_at DESC LIMIT 1) AS last_doctor_name,
               (SELECT mr.created_at FROM medical_reviews mr WHERE mr.evaluation_id=e.id ORDER BY mr.created_at DESC LIMIT 1) AS last_review_at,
               (SELECT mr.conclusion FROM medical_reviews mr WHERE mr.evaluation_id=e.id ORDER BY mr.created_at DESC LIMIT 1) AS last_medical_conclusion
        FROM evaluations e
        JOIN patients p ON p.id=e.patient_id
        JOIN users n ON n.id=e.nurse_user_id
        WHERE 1=1
        """
        params: list[Any] = []
        if status:
            query += " AND e.status=?"
            params.append(status)
        status_values = [str(item) for item in (statuses or []) if str(item)]
        if status_values:
            query += f" AND e.status IN ({','.join('?' for _ in status_values)})"
            params.extend(status_values)
        if patient_id:
            query += " AND e.patient_id=?"
            params.append(patient_id)
        if nurse_user_id:
            query += " AND e.nurse_user_id=?"
            params.append(nurse_user_id)
        if evaluation_id:
            query += " AND e.id=?"
            params.append(evaluation_id)
        if source:
            query += " AND e.source=?"
            params.append(source)
        alert_values = [str(item) for item in (alert_levels or []) if str(item)]
        if alert_values:
            query += f" AND e.alert_level IN ({','.join('?' for _ in alert_values)})"
            params.extend(alert_values)
        if search.strip():
            token = f"%{search.strip()}%"
            query += (
                " AND (p.code LIKE ? OR p.document_number LIKE ? OR "
                "p.first_names LIKE ? OR p.last_names LIKE ? OR "
                "(p.first_names || ' ' || p.last_names) LIKE ?)"
            )
            params.extend([token, token, token, token, token])
        query += " ORDER BY e.created_at DESC, CASE e.alert_level WHEN 'ALTO' THEN 0 WHEN 'MEDIO' THEN 1 ELSE 2 END LIMIT ? OFFSET ?"
        params.extend([max(1, min(int(limit), 100000)), max(0, int(offset))])
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def get_evaluation(self, evaluation_id: str) -> dict[str, Any] | None:
        rows = self.list_evaluations(evaluation_id=evaluation_id, limit=1)
        return rows[0] if rows else None

    def ensure_historical_model_predictions(
        self,
        predictor: Any,
        model_name: str,
        model_version: str,
    ) -> int:
        """Complete ML probabilities for the imported cohort once per model version."""
        with self._connect() as connection:
            rows = [dict(row) for row in connection.execute(
                """SELECT * FROM evaluations
                WHERE source='HISTORICAL_CSV'
                  AND (ml_probability IS NULL OR model_version<>?)""",
                (model_version,),
            ).fetchall()]
        if not rows:
            return 0
        updates: list[tuple[Any, ...]] = []
        for row in rows:
            probability = float(predictor(row))
            expert = evaluate_rules(row)
            level, message, final_probability = hybrid_decision(expert, probability, row)
            next_status = row.get("status")
            if next_status in {"HISTORICAL", "PENDING", "NO_REVIEW"}:
                next_status = "PENDING" if level in {"MEDIO", "ALTO"} else "NO_REVIEW"
            updates.append((
                level, final_probability, model_name, model_version,
                json.dumps(expert.to_dict(), ensure_ascii=False), message, next_status,
                utc_now(), row["id"],
            ))
        with self._connect() as connection:
            connection.executemany(
                """UPDATE evaluations
                SET alert_level=?, ml_probability=?, model_name=?, model_version=?,
                    rules_json=?, explanation=?, status=?, updated_at=?
                WHERE id=?""",
                updates,
            )
        return len(updates)

    def add_medical_review(
        self,
        evaluation_id: str,
        status: str,
        observation: str,
        actor: dict[str, Any],
        conclusion: str = "NO_CONCLUSION",
    ) -> dict[str, Any]:
        if actor.get("role") != "doctor":
            raise PermissionError("Solo un médico puede registrar la revisión.")
        if status not in {"REVIEWED", "CORRECTION", "FOLLOW_UP", "CLOSED"}:
            raise ValueError("Estado de revisión no válido.")
        observation = observation.strip()
        if len(observation) < 5:
            raise ValueError("Escriba una observación médica breve.")
        if len(observation) > 2000:
            raise ValueError("La observación médica no puede superar 2000 caracteres.")
        allowed_conclusions = {"NO_CONCLUSION", "RISK_DISCARDED", "REQUIRES_CONFIRMATION", "CONFIRMED_EXTERNAL", "REFERRED"}
        if conclusion not in allowed_conclusions:
            raise ValueError("Conclusión de revisión no válida.")
        row = {
            "id": str(uuid.uuid4()),
            "evaluation_id": evaluation_id,
            "doctor_user_id": actor["id"],
            "status": status,
            "observation": observation,
            "conclusion": conclusion,
            "created_at": utc_now(),
        }
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT source, alert_level FROM evaluations WHERE id=?", (evaluation_id,)
            ).fetchone()
            if not exists:
                raise ValueError("Evaluación no encontrada.")
            if exists["alert_level"] not in {"MEDIO", "ALTO"}:
                raise PermissionError("Las alertas bajas no se envían a revisión médica.")
            connection.execute(
                """INSERT INTO medical_reviews
                (id,evaluation_id,doctor_user_id,status,observation,conclusion,created_at)
                VALUES (:id,:evaluation_id,:doctor_user_id,:status,:observation,:conclusion,:created_at)""",
                row,
            )
            connection.execute(
                "UPDATE evaluations SET status=?, updated_at=? WHERE id=?",
                (status, utc_now(), evaluation_id),
            )
        self.audit(actor, "REVIEW", "evaluation", evaluation_id, {"status": status, "conclusion": conclusion})
        return row

    def list_reviews(self, evaluation_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT mr.*, u.username AS doctor_username, u.display_name AS doctor_name
                FROM medical_reviews mr JOIN users u ON u.id=mr.doctor_user_id
                WHERE mr.evaluation_id=? ORDER BY mr.created_at DESC""",
                (evaluation_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_patient_note(
        self, patient_id: str, note_type: str, observation: str, actor: dict[str, Any], referral_area: str = ""
    ) -> dict[str, Any]:
        if actor.get("role") != "doctor":
            raise PermissionError("Solo medicina puede registrar notas de seguimiento.")
        allowed = {"GENERAL", "FOLLOW_UP", "REFERRAL", "NUTRITION", "CARDIOLOGY", "LABORATORY"}
        if note_type not in allowed:
            raise ValueError("Tipo de nota no válido.")
        observation = _bounded_text(observation, "Observación", required=True, min_length=5, max_length=2000, collapse_spaces=False)
        referral_area = _bounded_text(referral_area, "Área de derivación", max_length=120)
        with self._connect() as connection:
            patient = connection.execute("SELECT id FROM patients WHERE id=?", (patient_id,)).fetchone()
            if not patient:
                raise ValueError("Paciente no encontrado.")
            row = {
                "id": str(uuid.uuid4()), "patient_id": patient_id,
                "doctor_user_id": actor["id"], "note_type": note_type,
                "referral_area": referral_area or None, "observation": observation,
                "created_at": utc_now(),
            }
            connection.execute(
                """INSERT INTO patient_notes
                (id,patient_id,doctor_user_id,note_type,referral_area,observation,created_at)
                VALUES (:id,:patient_id,:doctor_user_id,:note_type,:referral_area,:observation,:created_at)""",
                row,
            )
            connection.execute("UPDATE patients SET updated_at=? WHERE id=?", (row["created_at"], patient_id))
        self.audit(actor, "CREATE_NOTE", "patient", patient_id, {"type": note_type, "referral_area": referral_area})
        return row

    def list_patient_notes(self, patient_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT pn.*, u.username AS doctor_username, u.display_name AS doctor_name
                FROM patient_notes pn JOIN users u ON u.id=pn.doctor_user_id
                WHERE pn.patient_id=? ORDER BY pn.created_at DESC""",
                (patient_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Dashboards, exports and backup
    # ------------------------------------------------------------------
    def dashboard_counts(self) -> dict[str, int]:
        with self._connect() as connection:
            return {
                "patients": int(connection.execute("SELECT COUNT(*) FROM patients WHERE active=1").fetchone()[0]),
                "official_patients": int(connection.execute("SELECT COUNT(*) FROM patients WHERE active=1 AND source='OFFICIAL'").fetchone()[0]),
                "historical_patients": int(connection.execute("SELECT COUNT(*) FROM patients WHERE active=1 AND source='HISTORICAL_CSV'").fetchone()[0]),
                "evaluations": int(connection.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]),
                "official_evaluations": int(connection.execute("SELECT COUNT(*) FROM evaluations WHERE source='OFFICIAL'").fetchone()[0]),
                "historical_evaluations": int(connection.execute("SELECT COUNT(*) FROM evaluations WHERE source='HISTORICAL_CSV'").fetchone()[0]),
                "pending": int(connection.execute("SELECT COUNT(*) FROM evaluations WHERE status='PENDING' AND alert_level IN ('MEDIO','ALTO')").fetchone()[0]),
                "high": int(connection.execute("SELECT COUNT(*) FROM evaluations WHERE alert_level='ALTO'").fetchone()[0]),
                "users": int(connection.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0]),
            }

    def list_audit_logs(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (int(limit),)
            ).fetchall()]

    def dataframe(self, table: str) -> pd.DataFrame:
        allowed = {"users", "patients", "evaluations", "medical_reviews", "patient_notes", "audit_logs"}
        if table not in allowed:
            raise ValueError("Tabla no permitida.")
        with self._connect() as connection:
            if table == "users":
                query = "SELECT id,username,role,display_name,active,last_login,created_at FROM users"
            else:
                query = f"SELECT * FROM {table}"
            return pd.read_sql_query(query, connection)

    def anonymized_evaluations_dataframe(self) -> pd.DataFrame:
        query = """
        SELECT e.id AS evaluation_id, p.code AS patient_code, e.created_at, e.age,
               e.gender, e.height_cm, e.weight_kg, e.frame, e.chol, e.stab_glu,
               e.hdl, e.ratio, e.glyhb, e.bp1s, e.bp1d, e.bp2s, e.bp2d,
               e.waist_cm, e.hip_cm, e.time_ppn, e.alert_level, e.rule_score,
               e.ml_probability, e.model_name, e.model_version, e.status,
               p.department, p.province, p.district, p.city
        FROM evaluations e JOIN patients p ON p.id=e.patient_id
        ORDER BY e.created_at DESC
        """
        with self._connect() as connection:
            return pd.read_sql_query(query, connection)

    def backup_bytes(self) -> bytes:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp:
            temp_path = Path(temp.name)
        try:
            source = self._connect()
            destination = sqlite3.connect(temp_path)
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()
            return temp_path.read_bytes()
        finally:
            temp_path.unlink(missing_ok=True)

    def restore_backup_bytes(self, data: bytes, actor: dict[str, Any]) -> None:
        """Validate and restore a SQLite backup uploaded by an administrator."""
        if actor.get("role") != "admin":
            raise PermissionError("Solo administración puede restaurar respaldos.")
        if not data.startswith(b"SQLite format 3\x00"):
            raise ValueError("El archivo no corresponde a una base SQLite válida.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp:
            temp_path = Path(temp.name)
            temp.write(data)
        required = {"users", "patients", "evaluations", "medical_reviews", "patient_notes", "audit_logs"}
        try:
            connection = sqlite3.connect(temp_path)
            try:
                result = connection.execute("PRAGMA integrity_check").fetchone()
                if not result or str(result[0]).lower() != "ok":
                    raise ValueError("La copia no supera la verificación de integridad.")
                tables = {
                    str(row[0]) for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                missing = sorted(required - tables)
                if missing:
                    raise ValueError("La copia no contiene las tablas requeridas: " + ", ".join(missing))
            finally:
                connection.close()
            self.path.write_bytes(data)
        finally:
            temp_path.unlink(missing_ok=True)
        self.audit(actor, "RESTORE", "backup", detail={"size_bytes": len(data)})


def create_repository(path: Path = LOCAL_DB) -> SQLiteRepository:
    return SQLiteRepository(path)


def rows_to_dataframe(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows))
    for column in frame.columns:
        if column.endswith("_at"):
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame
