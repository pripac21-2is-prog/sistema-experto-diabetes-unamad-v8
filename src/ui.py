from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Any

import streamlit as st

from .config import (
    APP_SHORT_TITLE,
    APP_VERSION,
    HOSPITAL_BLUE,
    HOSPITAL_CYAN,
    HOSPITAL_NAVY,
    HOSPITAL_PALE,
    HOSPITAL_SKY,
    INK,
    LINE,
    LOGO_SISTEMAS_PATH,
    LOGO_UNAMAD_PATH,
    MEDICAL_DOCTOR_PATH,
    MUTED,
    ROLE_LABELS,
    UNAMAD_GOLD,
)


def image_to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8") if path.exists() else ""


def medical_illustration_svg() -> str:
    """Ilustración vectorial original, sin depender de imágenes externas."""
    return """
    <svg viewBox="0 0 430 300" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Ilustración clínica de monitoreo de glucosa">
      <defs>
        <linearGradient id="screen" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#EAF8FD"/>
          <stop offset="1" stop-color="#C9ECF8"/>
        </linearGradient>
        <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#073B5C" flood-opacity=".17"/>
        </filter>
      </defs>
      <circle cx="333" cy="83" r="64" fill="#CDEEF8" opacity=".75"/>
      <circle cx="89" cy="224" r="42" fill="#DDF5FA"/>
      <rect x="75" y="30" width="240" height="210" rx="30" fill="#FFFFFF" filter="url(#shadow)"/>
      <rect x="100" y="58" width="190" height="72" rx="18" fill="url(#screen)"/>
      <path d="M118 108 C145 83 168 115 194 91 C220 68 239 106 272 78" fill="none" stroke="#0B78A8" stroke-width="7" stroke-linecap="round"/>
      <circle cx="118" cy="108" r="6" fill="#0A8F93"/><circle cx="194" cy="91" r="6" fill="#0A8F93"/><circle cx="272" cy="78" r="6" fill="#0A8F93"/>
      <rect x="105" y="154" width="85" height="52" rx="14" fill="#F3FAFD" stroke="#D3E7F0"/>
      <text x="147" y="178" text-anchor="middle" font-family="Arial" font-size="12" fill="#5D7584">GLUCOSA</text>
      <text x="147" y="197" text-anchor="middle" font-family="Arial" font-size="21" font-weight="700" fill="#073B5C">108</text>
      <rect x="202" y="154" width="85" height="52" rx="14" fill="#F3FAFD" stroke="#D3E7F0"/>
      <text x="244" y="178" text-anchor="middle" font-family="Arial" font-size="12" fill="#5D7584">ALERTA</text>
      <text x="244" y="197" text-anchor="middle" font-family="Arial" font-size="18" font-weight="700" fill="#0A8F93">BAJA</text>
      <rect x="335" y="119" width="56" height="110" rx="18" fill="#0B78A8" filter="url(#shadow)"/>
      <rect x="345" y="136" width="36" height="48" rx="8" fill="#EAF8FD"/>
      <path d="M363 144 C355 156 352 162 352 168 C352 177 359 183 363 183 C370 183 376 177 376 168 C376 162 372 155 363 144Z" fill="#19A7CE"/>
      <circle cx="363" cy="207" r="7" fill="#FFFFFF"/>
      <path d="M45 85 h43 M66 64 v43" stroke="#19A7CE" stroke-width="11" stroke-linecap="round"/>
      <path d="M324 248 h48" stroke="#A7DDEA" stroke-width="8" stroke-linecap="round"/>
    </svg>
    """


def apply_styles() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --navy:{HOSPITAL_NAVY}; --blue:{HOSPITAL_BLUE}; --cyan:{HOSPITAL_CYAN};
            --sky:{HOSPITAL_SKY}; --pale:{HOSPITAL_PALE}; --ink:{INK};
            --muted:{MUTED}; --line:{LINE}; --gold:{UNAMAD_GOLD};
        }}
        html, body, [class*="css"] {{ font-family: Inter, "Segoe UI", Arial, sans-serif; }}
        .stApp {{ background:linear-gradient(180deg,#DCECF5 0%,#F4F9FC 44%,#E8F2F8 100%); color:var(--ink); }}
        .block-container {{ padding-top:3.7rem; padding-bottom:3rem; max-width:1440px; }}
        header[data-testid="stHeader"] {{ background:rgba(220,236,245,.97); backdrop-filter:blur(8px); height:2.8rem; }}
        [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer {{ display:none !important; }}

        /* Sidebar clínica clara */
        [data-testid="stSidebar"] {{
            background:linear-gradient(180deg,#074D7A 0%,#073B63 58%,#052A49 100%);
            border-right:1px solid #063A60;
        }}
        [data-testid="stSidebar"] > div:first-child {{ padding-top:.8rem; }}
        [data-testid="stSidebar"] hr {{ border-color:#B9D9E6; }}
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] label {{ color:#F5FBFE !important; }}
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea {{
            color:#0B2434 !important; background:#FFFFFF !important;
            -webkit-text-fill-color:#0B2434 !important;
        }}
        [data-testid="stSidebar"] input::placeholder {{ color:#78909C !important; opacity:1; }}
        [data-testid="stSidebar"] [data-baseweb="input"] {{ background:#FFFFFF !important; border-radius:12px; }}

        /* Navegación sin bolitas */
        [data-testid="stSidebar"] div[role="radiogroup"] {{ gap:.34rem; display:flex; flex-direction:column; }}
        [data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] {{
            background:rgba(255,255,255,.10); border:1px solid rgba(255,255,255,.13);
            border-radius:12px; padding:.62rem .72rem; margin:0;
            transition:.16s ease; min-height:42px;
        }}
        [data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:hover {{
            background:rgba(255,255,255,.20); border-color:rgba(255,255,255,.35); transform:translateX(2px);
        }}
        [data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] > div:first-child,
        [data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child,
        [data-testid="stSidebar"] [data-testid="stRadio"] label svg {{ display:none !important; }}
        [data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) {{
            background:linear-gradient(135deg,#0B69A5,#168FCA); border-color:#69C4E4;
            box-shadow:0 7px 18px rgba(11,120,168,.18);
        }}
        [data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) p {{ color:white !important; font-weight:800; }}

        /* Cabecera institucional */
        .institutional-strip {{
            display:flex; align-items:center; justify-content:space-between; gap:16px;
            background:#FFFFFF; border:1px solid var(--line); border-radius:18px;
            padding:13px 16px; margin:.35rem 0 16px; box-shadow:0 5px 18px rgba(7,59,92,.05);
        }}
        .institutional-left {{ display:flex; align-items:center; gap:12px; }}
        .institutional-left img {{ width:48px; height:48px; object-fit:contain; }}
        .institutional-name {{ font-weight:900; color:var(--navy); font-size:.94rem; line-height:1.25; }}
        .institutional-sub {{ color:var(--muted); font-size:.78rem; }}
        .institutional-authors {{ text-align:right; color:var(--muted); font-size:.76rem; line-height:1.45; }}

        .brand-box {{ background:rgba(255,255,255,.96); border:1px solid rgba(255,255,255,.65); border-radius:16px; padding:12px; }}
        .brand-row {{ display:flex; gap:9px; align-items:center; }}
        .brand-row img {{ width:48px; height:48px; object-fit:contain; background:white; border-radius:11px; padding:3px; }}
        .brand-title {{ font-weight:950; font-size:.98rem; color:var(--navy); margin-top:8px; }}
        .brand-sub {{ font-size:.76rem; color:var(--muted); line-height:1.42; }}
        .brand-author {{ margin-top:7px; font-size:.7rem; color:#557180; line-height:1.4; }}

        /* Hero hospitalario */
        .hero {{
            position:relative; overflow:hidden;
            background:linear-gradient(120deg,#0A3C67 0%,#0B5D91 48%,#107FB1 100%);
            border:1px solid #1D80B0; border-radius:26px; padding:30px 34px;
            box-shadow:0 16px 42px rgba(7,59,92,.11);
        }}
        .hero:before {{ content:""; position:absolute; width:330px; height:330px; border-radius:50%; right:-120px; top:-150px; background:rgba(255,255,255,.10); }}
        .hero-grid {{ display:grid; grid-template-columns:minmax(0,1.35fr) minmax(300px,.65fr); gap:28px; align-items:center; position:relative; z-index:2; }}
        .hero-logos {{ display:flex; gap:8px; align-items:center; margin-bottom:12px; }}
        .hero-logos img {{ width:55px; height:55px; object-fit:contain; background:#FFFFFF; border:1px solid #CBE6F0; border-radius:13px; padding:4px; }}
        .eyebrow {{ color:#A9E5FF; text-transform:uppercase; letter-spacing:.12em; font-weight:900; font-size:.71rem; }}
        .hero h1 {{ margin:.35rem 0 .75rem; font-size:2.45rem; line-height:1.07; letter-spacing:-.035em; color:#FFFFFF; max-width:820px; }}
        .hero p {{ margin:0 0 1rem; font-size:1rem; line-height:1.62; max-width:820px; color:#E5F5FC; }}
        .hero-badges {{ display:flex; flex-wrap:wrap; gap:8px; }}
        .hero-badge {{ padding:7px 11px; border-radius:9px; background:rgba(255,255,255,.13); border:1px solid rgba(255,255,255,.34); color:#FFFFFF; font-size:.75rem; font-weight:800; }}
        .hero-visual {{ min-height:255px; display:flex; align-items:center; justify-content:center; }}
        .hero-visual svg {{ width:100%; max-width:430px; height:auto; }}
        .hero-photo {{ width:100%; max-width:390px; height:270px; object-fit:cover; object-position:center top; border-radius:24px; border:4px solid rgba(255,255,255,.82); box-shadow:0 18px 38px rgba(0,0,0,.24); }}

        .section-title {{ font-size:1.52rem; font-weight:950; color:var(--navy); margin:1.55rem 0 .18rem; letter-spacing:-.015em; }}
        .section-subtitle {{ color:var(--muted); margin-bottom:1rem; line-height:1.55; }}
        .section-kicker {{ color:var(--blue); font-weight:900; text-transform:uppercase; letter-spacing:.11em; font-size:.69rem; margin-top:1.3rem; }}

        /* Tarjetas compactas */
        .card-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin:14px 0; }}
        .info-card {{ background:#FFFFFF; border:1px solid var(--line); border-radius:18px; padding:17px; min-height:135px; box-shadow:0 7px 22px rgba(7,59,92,.055); }}
        .info-card .code {{ display:inline-flex; align-items:center; justify-content:center; min-width:36px; height:30px; padding:0 8px; border-radius:8px; background:#E4F5FB; color:var(--blue); font-size:.72rem; font-weight:950; letter-spacing:.05em; }}
        .info-card h3 {{ font-size:.98rem; color:var(--navy); margin:.68rem 0 .35rem; }}
        .info-card p {{ color:var(--muted); font-size:.83rem; line-height:1.5; margin:0; }}

        .status {{ background:#FFFFFF; border:1px solid var(--line); border-left:5px solid var(--cyan); border-radius:16px; padding:14px 15px; box-shadow:0 6px 18px rgba(7,59,92,.045); min-height:110px; }}
        .status .label {{ color:var(--muted); font-weight:850; font-size:.69rem; text-transform:uppercase; letter-spacing:.08em; }}
        .status .value {{ color:var(--navy); font-weight:950; font-size:1.5rem; margin:.28rem 0; }}
        .status .detail {{ color:var(--muted); font-size:.78rem; line-height:1.4; }}

        .notice {{ background:#EAF8FD; border:1px solid #B8DDEB; border-left:5px solid var(--blue); border-radius:13px; padding:13px 15px; color:#174F69; margin:.5rem 0 1rem; }}
        .warning-note {{ background:#FFF8E7; border:1px solid #E9D28E; border-radius:13px; padding:13px 15px; color:#654F14; margin:.5rem 0 1rem; }}
        .danger-note {{ background:#FFF1F1; border:1px solid #E8B9B9; border-radius:13px; padding:13px 15px; color:#762E2E; margin:.5rem 0 1rem; }}
        .source-note {{ background:#F6FAFC; border:1px solid var(--line); border-radius:13px; padding:12px 14px; color:#4E6978; font-size:.8rem; line-height:1.5; }}

        .alert-low,.alert-medium,.alert-high {{ border-radius:17px; padding:18px; margin:1rem 0; border-left:7px solid; box-shadow:0 8px 22px rgba(0,0,0,.045); }}
        .alert-low {{ background:#EAF8F5; border-color:#138A72; color:#155C4D; }}
        .alert-medium {{ background:#FFF7E4; border-color:#D28B00; color:#6A4E00; }}
        .alert-high {{ background:#FFF0F0; border-color:#C84646; color:#772E2E; }}
        .alert-title {{ font-size:1.25rem; font-weight:950; margin-bottom:5px; }}
        .alert-copy {{ line-height:1.5; margin-bottom:10px; }}
        .chip {{ display:inline-block; padding:5px 9px; border-radius:8px; font-size:.74rem; font-weight:850; margin:3px 4px 0 0; background:white; border:1px solid rgba(0,0,0,.08); }}
        .role-badge {{ display:inline-block; background:#D7F0F7; color:#0B5774; padding:5px 9px; border-radius:8px; font-size:.7rem; font-weight:900; }}

        .architecture {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin:15px 0; }}
        .arch-card {{ background:#FFFFFF; border:1px solid var(--line); border-radius:16px; padding:15px; min-height:140px; box-shadow:0 6px 20px rgba(7,59,92,.045); }}
        .arch-step {{ color:var(--blue); font-size:.72rem; font-weight:950; letter-spacing:.08em; }}
        .arch-card b {{ color:var(--navy); display:block; margin:.5rem 0 .38rem; }}
        .arch-card span {{ color:var(--muted); font-size:.8rem; line-height:1.45; }}

        .split-panel {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin:14px 0; }}
        .panel {{ background:#FFFFFF; border:1px solid var(--line); border-radius:18px; padding:18px; box-shadow:0 6px 20px rgba(7,59,92,.045); }}
        .panel h3 {{ color:var(--navy); margin-top:0; }}
        .panel p,.panel li {{ color:var(--muted); font-size:.86rem; line-height:1.55; }}

        div[data-testid="stMetric"] {{ background:#FFFFFF; border:1px solid var(--line); border-radius:16px; padding:12px 14px; box-shadow:0 5px 16px rgba(7,59,92,.04); }}
        div[data-testid="stMetric"] label {{ color:var(--muted) !important; }}
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {{ color:var(--navy); }}
        .stButton button,.stDownloadButton button {{ border-radius:11px; font-weight:850; min-height:42px; color:#062B49 !important; background:#FFFFFF; border:1px solid #AFCFDE; }}
        .stButton button p,.stDownloadButton button p {{ color:inherit !important; }}
        .stButton button[kind="primary"] {{ background:linear-gradient(135deg,#075E91,#0A8FC2); border-color:#075E91; color:#FFFFFF !important; }}
        .stButton button[kind="primary"]:hover {{ background:var(--navy); border-color:var(--navy); }}
        .stTabs [data-baseweb="tab-list"] {{ gap:6px; }}
        .stTabs [data-baseweb="tab"] {{ background:#FFFFFF; border:1px solid var(--line); border-radius:10px; padding:.45rem .75rem; }}
        .stTabs [aria-selected="true"] {{ background:#E5F5FB !important; color:var(--navy) !important; }}
        [data-testid="stForm"] {{ background:#FFFFFF; border:1px solid var(--line); border-radius:18px; padding:1rem; box-shadow:0 5px 18px rgba(7,59,92,.035); }}
        [data-testid="stDataFrame"] {{ border:1px solid var(--line); border-radius:14px; overflow:hidden; }}

        /* Login */
        .login-intro {{ background:linear-gradient(135deg,#D7EDF7,#FFFFFF); border:1px solid #B9DDEA; border-radius:18px; padding:20px; min-height:250px; }}
        .login-intro h2 {{ color:var(--navy); margin-top:0; }}
        .login-intro p {{ color:var(--muted); line-height:1.6; }}
        .login-list {{ display:grid; gap:9px; margin-top:15px; }}
        .login-item {{ background:#FFFFFF; border:1px solid var(--line); border-radius:11px; padding:9px 11px; color:#3E6172; font-size:.82rem; }}


        /* Contraste y legibilidad de formularios en local y Community Cloud */
        div[data-testid="stTextInput"] label,
        div[data-testid="stTextInput"] label p,
        div[data-testid="stTextArea"] label,
        div[data-testid="stTextArea"] label p,
        div[data-testid="stNumberInput"] label,
        div[data-testid="stNumberInput"] label p,
        div[data-testid="stSelectbox"] label,
        div[data-testid="stSelectbox"] label p {{
            color:#0A2940 !important;
            -webkit-text-fill-color:#0A2940 !important;
            opacity:1 !important;
            font-weight:750 !important;
        }}
        div[data-testid="stTextInput"] div[data-baseweb="input"],
        div[data-testid="stNumberInput"] div[data-baseweb="input"],
        div[data-testid="stTextArea"] textarea,
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
            background:#FFFFFF !important;
            border-color:#9FC8D9 !important;
            color:#071F31 !important;
            box-shadow:none !important;
        }}
        div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,
        div[data-testid="stNumberInput"] div[data-baseweb="input"]:focus-within,
        div[data-testid="stTextArea"] textarea:focus {{
            border-color:#075E91 !important;
            box-shadow:0 0 0 2px rgba(7,94,145,.16) !important;
        }}
        input, textarea, [data-baseweb="select"] input {{
            background:#FFFFFF !important;
            color:#071F31 !important;
            -webkit-text-fill-color:#071F31 !important;
            caret-color:#075E91 !important;
        }}
        input::placeholder, textarea::placeholder {{
            color:#617B8A !important;
            -webkit-text-fill-color:#617B8A !important;
            opacity:1 !important;
        }}
        div[data-testid="stToggle"] label,
        div[data-testid="stToggle"] label p {{
            color:#0A2940 !important;
            -webkit-text-fill-color:#0A2940 !important;
            opacity:1 !important;
            font-weight:800 !important;
        }}
        div[data-testid="stFormSubmitButton"] button,
        button[data-testid="stBaseButton-primaryFormSubmit"],
        button[data-testid="stBaseButton-primary"],
        button[kind="primaryFormSubmit"],
        .stButton button[kind="primary"] {{
            background:linear-gradient(135deg,#075E91,#0A8FC2) !important;
            border-color:#075E91 !important;
            color:#FFFFFF !important;
            -webkit-text-fill-color:#FFFFFF !important;
        }}
        div[data-testid="stFormSubmitButton"] button p,
        button[data-testid="stBaseButton-primaryFormSubmit"] p,
        button[data-testid="stBaseButton-primary"] p,
        button[kind="primaryFormSubmit"] p,
        .stButton button[kind="primary"] p {{
            color:#FFFFFF !important;
            -webkit-text-fill-color:#FFFFFF !important;
            opacity:1 !important;
        }}
        button[aria-label="Show password"], button[aria-label="Hide password"],
        button[aria-label="Mostrar contraseña"], button[aria-label="Ocultar contraseña"],
        div[data-testid="stTextInput"] button {{ display:none !important; }}
        [data-testid="stSidebar"] .brand-title, [data-testid="stSidebar"] .brand-sub,
        [data-testid="stSidebar"] .brand-author, [data-testid="stSidebar"] .role-badge {{ color:#0A2940 !important; }}
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{ color:#D7EBF4 !important; }}
        [data-testid="stSidebar"] .stButton button {{ background:#FFFFFF !important; color:#062B49 !important; border:1px solid #B8D5E3 !important; }}
        [data-testid="stSidebar"] .stButton button p {{ color:#062B49 !important; opacity:1 !important; }}
        [data-testid="stSidebar"] [data-testid="stToggle"] label p {{ font-size:1.15rem !important; font-weight:900 !important; }}
        .institutional-strip {{ border-top:5px solid #075E91; overflow:visible; min-height:78px; position:relative; z-index:2; }}
        .data-badge {{ display:inline-block; background:#D9EEF7; color:#064E76; border:1px solid #A9D5E7; padding:5px 9px; border-radius:999px; font-size:.72rem; font-weight:850; margin-right:5px; }}
        .arch-flow {{ background:linear-gradient(135deg,#062B49,#075E91); border-radius:24px; padding:22px; color:white; margin:1rem 0 1.4rem; box-shadow:0 14px 35px rgba(6,43,73,.20); overflow:auto; }}
        .arch-flow-grid {{ min-width:980px; display:grid; grid-template-columns:1fr 54px 1fr 54px 1fr 54px 1fr 54px 1fr; align-items:stretch; gap:4px; }}
        .arch-node {{ background:rgba(255,255,255,.97); color:#0A2940; border-radius:16px; padding:15px; min-height:145px; border:1px solid rgba(255,255,255,.65); }}
        .arch-node .icon {{ font-size:1.55rem; }} .arch-node h4 {{ margin:.4rem 0; color:#062B49; }}
        .arch-node p {{ margin:0; font-size:.78rem; line-height:1.45; color:#496879; }}
        .arch-arrow {{ display:flex; align-items:center; justify-content:center; font-size:2rem; color:#8ED6F0; font-weight:900; }}
        .arch-layers {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:15px; }}
        .arch-layer {{ background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.20); border-radius:14px; padding:12px; font-size:.78rem; line-height:1.45; }}

        @media(max-width:1050px) {{
            .hero-grid {{ grid-template-columns:1fr; }} .hero-visual {{ min-height:210px; }}
            .hero h1 {{ font-size:2rem; }} .card-grid {{ grid-template-columns:1fr 1fr; }}
            .architecture {{ grid-template-columns:1fr 1fr; }} .institutional-authors {{ display:none; }}
        }}
        @media(max-width:650px) {{
            .block-container {{ padding: 3.1rem .8rem 2rem; }}
            .hero {{ padding:20px 18px; border-radius:20px; }} .hero h1 {{ font-size:1.55rem; }}
            .hero p {{ font-size:.88rem; }} .hero-visual {{ min-height:155px; }}
            .hero-visual svg {{ max-width:300px; }}
            .card-grid,.architecture,.split-panel {{ grid-template-columns:1fr; gap:9px; }}
            .arch-flow {{ padding:14px; overflow:visible; }}
            .arch-flow-grid {{ min-width:0; grid-template-columns:1fr; gap:8px; }}
            .arch-arrow {{ transform:rotate(90deg); min-height:28px; font-size:1.45rem; }}
            .arch-layers {{ grid-template-columns:1fr; gap:8px; }}
            .arch-node {{ min-height:0; }}
            .info-card,.arch-card {{ min-height:0; padding:14px; }}
            .status {{ min-height:0; }} .institutional-strip {{ padding:9px 10px; }}
            .institutional-left img {{ width:38px; height:38px; }}
            .institutional-name {{ font-size:.78rem; }} .institutional-sub {{ font-size:.68rem; }}
            .section-title {{ font-size:1.25rem; }}
            [data-testid="stForm"] {{ padding:.65rem; border-radius:14px; }}
            [data-baseweb="input"] {{ min-height:38px !important; }}
            input, textarea {{ font-size:.88rem !important; }}
            .stNumberInput button {{ min-width:34px !important; min-height:34px !important; }}
            .hero-photo {{ height:190px; max-width:320px; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def institutional_header() -> None:
    logo1 = image_to_base64(LOGO_UNAMAD_PATH)
    logo2 = image_to_base64(LOGO_SISTEMAS_PATH)
    imgs = ""
    if logo1:
        imgs += f'<img src="data:image/png;base64,{logo1}">'
    if logo2:
        imgs += f'<img src="data:image/png;base64,{logo2}">'
    st.markdown(
        f"""
        <div class="institutional-strip">
          <div class="institutional-left">
            <div style="display:flex;gap:6px">{imgs}</div>
            <div><div class="institutional-name">Universidad Nacional Amazónica de Madre de Dios</div>
            <div class="institutional-sub">Escuela Profesional de Ingeniería de Sistemas e Informática · Sistemas Expertos</div></div>
          </div>
          <div class="institutional-authors"><b>Desarrollado por</b><br>Poldy Raúl Ripa Challco · Frank Hiobert Palomino Usca<br>Puerto Maldonado · 2026</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_brand(user: dict[str, Any] | None = None) -> None:
    logo1 = image_to_base64(LOGO_UNAMAD_PATH)
    logo2 = image_to_base64(LOGO_SISTEMAS_PATH)
    imgs = ""
    if logo1:
        imgs += f'<img src="data:image/png;base64,{logo1}">'
    if logo2:
        imgs += f'<img src="data:image/png;base64,{logo2}">'
    role_html = ""
    if user:
        display_name = html.escape(str(user.get("display_name", user.get("username", ""))))
        role_label = html.escape(str(ROLE_LABELS.get(str(user.get("role")), user.get("role", ""))))
        role_html = (
            f'<div style="margin-top:9px"><b>{display_name}</b><br>'
            f'<span class="role-badge">{role_label}</span></div>'
        )
    st.sidebar.markdown(
        f"""
        <div class="brand-box">
          <div class="brand-row">{imgs}</div>
          <div class="brand-title">Sistema de apoyo al tamizaje</div>
          <div class="brand-sub">Diabetes · UNAMAD</div>
          {role_html}
          <div class="brand-author">Poldy Raúl Ripa Challco<br>Frank Hiobert Palomino Usca</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.caption(f"{APP_SHORT_TITLE} · v{APP_VERSION}")


def hero(counts: dict[str, int] | None = None) -> None:
    counts = counts or {}
    logo1 = image_to_base64(LOGO_UNAMAD_PATH)
    logo2 = image_to_base64(LOGO_SISTEMAS_PATH)
    images = ""
    if logo1:
        images += f'<img src="data:image/png;base64,{logo1}">'
    if logo2:
        images += f'<img src="data:image/png;base64,{logo2}">'
    st.markdown(
        f"""
        <div class="hero">
          <div class="hero-grid">
            <div>
              <div class="hero-logos">{images}</div>
              <div class="eyebrow">Tecnología aplicada a la prevención y seguimiento</div>
              <h1>Sistema inteligente de apoyo al tamizaje del riesgo de diabetes</h1>
              <p>Plataforma web con consulta pública temporal y módulos privados para enfermería, medicina y administración. Combina reglas explicables con un modelo Random Forest previamente entrenado.</p>
              <div class="hero-badges">
                <span class="hero-badge">Consulta orientativa</span>
                <span class="hero-badge">Registro clínico académico</span>
                <span class="hero-badge">Revisión médica</span>
                <span class="hero-badge">PDF · CSV · Auditoría</span>
              </div>
            </div>
            <div class="hero-visual"><img class="hero-photo" src="data:image/png;base64,{image_to_base64(MEDICAL_DOCTOR_PATH)}" alt="Profesional de salud revisando una ficha clínica"></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def visitor_information_banner() -> None:
    st.markdown(
        f"""
        <div class="hero" style="padding:24px 28px;margin-bottom:18px">
          <div class="hero-grid" style="grid-template-columns:minmax(0,1.25fr) minmax(280px,.75fr)">
            <div>
              <div class="eyebrow">Información preventiva y tecnología explicable</div>
              <h1 style="font-size:2rem">Comprenda los datos antes de interpretar una alerta</h1>
              <p>La plataforma reúne conceptos sobre glucosa, HbA1c, presión, lípidos y medidas corporales. También explica qué variables usa el modelo y cuáles sirven solo como identificación o referencia.</p>
              <span class="data-badge">403 registros históricos</span>
              <span class="data-badge">19 columnas</span>
              <span class="data-badge">16 predictores</span>
              <span class="data-badge">11 reglas</span>
            </div>
            <div class="hero-visual" style="min-height:210px"><img class="hero-photo" style="height:220px" src="data:image/png;base64,{image_to_base64(MEDICAL_DOCTOR_PATH)}" alt="Profesional de salud"></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, subtitle: str = "", kicker: str = "") -> None:
    safe_title = html.escape(str(title))
    safe_subtitle = html.escape(str(subtitle))
    safe_kicker = html.escape(str(kicker))
    if kicker:
        st.markdown(f'<div class="section-kicker">{safe_kicker}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="section-title">{safe_title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="section-subtitle">{safe_subtitle}</div>', unsafe_allow_html=True)


def status_card(label: str, value: str, detail: str) -> None:
    st.markdown(
        f'<div class="status"><div class="label">{html.escape(str(label))}</div>'
        f'<div class="value">{html.escape(str(value))}</div>'
        f'<div class="detail">{html.escape(str(detail))}</div></div>',
        unsafe_allow_html=True,
    )


def alert_box(level: str, message: str, score: int, probability: float | None) -> None:
    css = {"BAJO": "alert-low", "MEDIO": "alert-medium", "ALTO": "alert-high"}.get(level, "alert-medium")
    probability_text = "Modelo no disponible" if probability is None else f"Estimación del modelo: {probability * 100:.1f} %"
    st.markdown(
        f'<div class="{css}"><div class="alert-title">Nivel de alerta: {html.escape(str(level))}</div>'
        f'<div class="alert-copy">{html.escape(str(message))}</div>'
        f'<span class="chip">Puntaje de reglas: {int(score)}</span>'
        f'<span class="chip">{html.escape(probability_text)}</span></div>',
        unsafe_allow_html=True,
    )


def info_cards(cards: list[tuple[str, str, str]]) -> None:
    markup = '<div class="card-grid">'
    for code, title, text in cards:
        markup += (
            f'<div class="info-card"><div class="code">{html.escape(str(code))}</div>'
            f'<h3>{html.escape(str(title))}</h3><p>{html.escape(str(text))}</p></div>'
        )
    markup += "</div>"
    st.markdown(markup, unsafe_allow_html=True)


def architecture_cards(cards: list[tuple[str, str, str]]) -> None:
    markup = '<div class="architecture">'
    for step, title, text in cards:
        markup += (
            f'<div class="arch-card"><div class="arch-step">{html.escape(str(step))}</div>'
            f'<b>{html.escape(str(title))}</b><span>{html.escape(str(text))}</span></div>'
        )
    markup += "</div>"
    st.markdown(markup, unsafe_allow_html=True)


def architecture_diagram() -> None:
    st.markdown(
        """
        <div class="arch-flow">
          <div class="arch-flow-grid">
            <div class="arch-node"><div class="icon">👥</div><h4>Usuarios</h4><p>Visitante sin cuenta, enfermería, médico y administrador. Cada rol ve únicamente sus funciones.</p></div>
            <div class="arch-arrow">→</div>
            <div class="arch-node"><div class="icon">🖥️</div><h4>Interfaz Streamlit</h4><p>Formularios, búsquedas, paneles, gráficas, historial y generación de reportes.</p></div>
            <div class="arch-arrow">→</div>
            <div class="arch-node"><div class="icon">🧠</div><h4>Motor híbrido</h4><p>Reglas SI–ENTONCES explicables y Random Forest previamente entrenado con diabetes.csv.</p></div>
            <div class="arch-arrow">→</div>
            <div class="arch-node"><div class="icon">🗄️</div><h4>Base de datos</h4><p>Usuarios, pacientes, evaluaciones, revisiones, auditoría y cohorte histórica de 403 registros.</p></div>
            <div class="arch-arrow">→</div>
            <div class="arch-node"><div class="icon">📄</div><h4>Resultados</h4><p>Alerta baja, media o alta; evidencia de reglas; revisión médica; PDF, CSV y respaldo.</p></div>
          </div>
          <div class="arch-layers">
            <div class="arch-layer"><b>Seguridad</b><br>Contraseñas con hash, prefijos por rol, bloqueo por intentos y validación de permisos.</div>
            <div class="arch-layer"><b>Trazabilidad</b><br>Cada acción queda asociada a usuario, fecha, entidad y versión del modelo.</div>
            <div class="arch-layer"><b>Persistencia</b><br>SQLite funciona localmente. PostgreSQL o Supabase puede incorporarse en una versión futura; no está implementado en esta entrega.</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def source_note(text: str) -> None:
    st.markdown(f'<div class="source-note">{html.escape(str(text))}</div>', unsafe_allow_html=True)
