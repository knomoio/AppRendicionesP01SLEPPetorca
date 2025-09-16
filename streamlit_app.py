# streamlit_app.py  — versión completa
import io, os, json
from datetime import date, datetime
from typing import List
import streamlit as st
import pandas as pd
from fpdf import FPDF
import matplotlib.pyplot as plt

st.set_page_config(page_title="Rendición de Cuentas – SLEP Petorca", layout="wide")

# ---------------------------- Helpers & State ----------------------------
def init_state():
    if "data" not in st.session_state:
        st.session_state.data = {"fondo_inicial": 0.0, "gastos": []}
    if "logo_bytes" not in st.session_state:
        st.session_state.logo_bytes = None
        st.session_state.logo_name = None

def money(x: float) -> str:
    try:
        return f"${x:,.0f}".replace(",", ".")
    except Exception:
        return f"${x}"

def load_data_from_json(file) -> None:
    try:
        obj = json.load(file)
        fi = float(obj.get("fondo_inicial", 0))
        gastos = obj.get("gastos", [])
        fixed = []
        for g in gastos:
            fixed.append({
                "fecha": g.get("fecha"),
                "monto": float(g.get("monto", 0)),
                "detalle": g.get("detalle") or g.get("descripcion") or "",
                "nombre_doc": g.get("nombre_doc"),
                "bytes_doc": None,
            })
        st.session_state.data = {"fondo_inicial": fi, "gastos": fixed}
        st.success("Datos cargados desde JSON.")
    except Exception as e:
        st.error(f"Error al leer JSON: {e}")

def export_data_json() -> bytes:
    data = {
        "fondo_inicial": st.session_state.data["fondo_inicial"],
        "gastos": [
            {"fecha": g["fecha"], "monto": g["monto"], "detalle": g["detalle"], "nombre_doc": g.get("nombre_doc")}
            for g in st.session_state.data["gastos"]
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

def gastos_df() -> pd.DataFrame:
    df = pd.DataFrame(st.session_state.data["gastos"])
    if not df.empty:
        df = df.assign(
            Fecha=pd.to_datetime(df["fecha"]).dt.date,
            Detalle=df["detalle"],
            Monto=pd.to_numeric(df["monto"], errors="coerce").fillna(0.0),
            Documento=df["nombre_doc"].fillna("—"),
        )[["Fecha", "Detalle", "Monto", "Documento"]]
    return df

def totals():
    df = gastos_df()
    if df.empty:
        total = 0.0; cantidad = 0
    else:
        total = float(pd.to_numeric(df["Monto"], errors="coerce").fillna(0).sum())
        cantidad = int(df.shape[0])
    fondo = float(st.session_state.data.get("fondo_inicial") or 0.0)
    saldo = fondo - total
    return fondo, total, saldo, cantidad

def add_gasto(fecha: date, detalle: str, monto: float, doc_file):
    nombre_doc = None; bytes_doc = None
    if doc_file is not None:
        nombre_doc = doc_file.name
        bytes_doc = doc_file.read()
    st.session_state.data["gastos"].append({
        "fecha": fecha.strftime("%Y-%m-%d"),
        "monto": float(monto), "detalle": detalle,
        "nombre_doc": nombre_doc, "bytes_doc": bytes_doc
    })

def remove_gastos(indices: List[int]):
    for idx in sorted(indices, reverse=True):
        if 0 <= idx < len(st.session_state.data["gastos"]):
            st.session_state.data["gastos"].pop(idx)

# ---------- PDF helpers (Unicode) ----------
def set_unicode_font(pdf: FPDF) -> bool:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/local/share/fonts/DejaVuSans.ttf",
        "fonts/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            pdf.add_font("DejaVu", "", path, uni=True)
            pdf.add_font("DejaVu", "B", path, uni=True)
            pdf.set_font("DejaVu", size=12)
            return True
    pdf.set_font("Helvetica", size=12)  # fallback sin Unicode
    return False

def safe_text(txt: str, unicode_ok: bool) -> str:
    return txt if unicode_ok else txt.replace("–", "-").encode("latin-1","ignore").decode("latin-1")

def export_pdf() -> bytes:
    df = gastos_df()
    fondo, total, saldo, cantidad = totals()
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    unicode_ok = set_unicode_font(pdf)

    # Logo opcional
    if st.session_state.logo_bytes:
        try:
            bio_logo = io.BytesIO(st.session_state.logo_bytes)
            pdf.image(bio_logo, x=10, y=8, w=30)
        except Exception:
            pass

    pdf.cell(0, 10, safe_text("Rendición de Cuentas – SLEP Petorca", unicode_ok), ln=True, align="C")
    pdf.ln(5)
    pdf.set_font(pdf.font_family, size=10)
    pdf.cell(0, 6, safe_text(f"Fecha de emisión: {datetime.now():%Y-%m-%d %H:%M}", unicode_ok), ln=True)
    pdf.ln(2)

    # Resumen
    pdf.set_font(pdf.font_family, "B", 11)
    pdf.cell(0, 7, safe_text("Resumen", unicode_ok), ln=True)
    pdf.set_font(pdf.font_family, size=10)
    pdf.cell(0, 6, safe_text(f"Fondo inicial: {money(fondo)}", unicode_ok), ln=True)
    pdf.cell(0, 6, safe_text(f"Total gastos: {money(total)}", unicode_ok), ln=True)
    pdf.cell(0, 6, safe_text(f"Saldo: {money(saldo)}", unicode_ok), ln=True)
    pdf.cell(0, 6, safe_text(f"Cantidad de gastos: {cantidad}", unicode_ok), ln=True)
    pdf.ln(4)

    # Tabla
    pdf.set_font(pdf.font_family, "B", 10)
    for w, h in [(30,7),(100,7),(30,7),(30,7)]:
        pass
    pdf.cell(30, 7, safe_text("Fecha", unicode_ok), 1, align="C")
    pdf.cell(100,7, safe_text("Detalle", unicode_ok), 1, align="C")
    pdf.cell(30, 7, safe_text("Monto", unicode_ok), 1, align="C")
    pdf.cell(30, 7, safe_text("Documento", unicode_ok), 1, align="C")
    pdf.ln()

    pdf.set_font(pdf.font_family, size=9)
    if df.empty:
        pdf.cell(190, 7, safe_text("Sin registros", unicode_ok), border=1, align="C")
        pdf.ln()
    else:
        for _, row in df.iterrows():
            pdf.cell(30, 7, row["Fecha"].strftime("%Y-%m-%d"), 1)
            detalle = safe_text(str(row["Detalle"]), unicode_ok)[:60]
            pdf.cell(100, 7, detalle, 1)
            pdf.cell(30, 7, money(float(row["Monto"])), 1, align="R")
            pdf.cell(30, 7, safe_text(str(row["Documento"])[:14], unicode_ok), 1)
            pdf.ln()

    out = io.BytesIO()
    pdf.output(out)
    return out.getvalue()

def export_excel() -> bytes:
    df = gastos_df()
    from openpyxl import Workbook
    from openpyxl.utils.dataframe import dataframe_to_rows
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.table import Table, TableStyleInfo
    wb = Workbook(); ws = wb.active; ws.title = "Gastos"

    ws["A1"] = "Rendición de Cuentas - SLEP Petorca"
    ws["A1"].font = Font(bold=True, size=14)
    ws.merge_cells("A1:D1")
    ws["A1"].alignment = Alignment(horizontal="center")

    if df.empty:
        df = pd.DataFrame(columns=["Fecha","Detalle","Monto","Documento"])
    else:
        df.columns = ["Fecha","Detalle","Monto","Documento"]

    start_row = 3
    for i, row in enumerate(dataframe_to_rows(df, index=False, header=True)):
        for j, val in enumerate(row, start=1):
            ws.cell(row=start_row + i, column=j, value=val)
    last_row = start_row + len(df)
    table = Table(displayName="TablaGastos", ref=f"A{start_row}:D{last_row}
