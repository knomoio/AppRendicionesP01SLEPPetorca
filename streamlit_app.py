# streamlit_app.py — versión oficial SLEP Petorca (fix merges Excel)
import io, os, json
from datetime import date, datetime
from typing import List
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from fpdf import FPDF

st.set_page_config(page_title="Rendición de Fondos Fijos P01 – SLEP Petorca", layout="wide")

# ============================ Helpers & State ============================

def init_state():
    if "data" not in st.session_state:
        st.session_state.data = {
            "fondo_inicial": 0.0,
            "gastos": [],  # fecha, detalle, monto, tipo_doc, nro_doc, proveedor, nombre_doc, bytes_doc
            "meta": {
                "tipo_fondo": "",
                "responsable": "",
                "rut": "",
                "institucion": "",
                "n_rendicion": "",
                "fecha_rendicion": "",
                "cargo": "",
                "mes_que_rinde": "",
                "n_rex": "",
                "fecha_rex": "",
                "observaciones": "",
                "n_egreso_inicial": "",
                "fecha_egreso_inicial": "",
            },
            "resumen": {
                "saldo_inicial_mes_ant": 0.0,
                "monto_recibido_mes_ant": 0.0,
                "monto_gasto_transporte": 0.0,
            },
            "firmas": {
                "encargado": "Encargado/a del Fondo",
                "directora": "Director/a Ejecutiva",
                "revisor1": "Nombre/Firma Revisor/a 1",
                "revisor2": "Nombre/Firma Revisor/a 2",
                "vobo_jefe_unidad": "V°B° JEFE UNIDAD",
                "vobo_finanzas": "V°B° UNIDAD DE FINANZAS",
                "contab_finanzas": "CONTABILIDAD Y FINANZAS",
                "vobo_admin_finanzas": "V°B° JEFE/(A) ADMINISTRACIÓN Y FINANZAS",
            },
        }
    if "logo_bytes" not in st.session_state:
        st.session_state.logo_bytes = None
        st.session_state.logo_name = None

def money(x: float) -> str:
    try:
        return f"${x:,.0f}".replace(",", ".")
    except Exception:
        return f"${x}"

def get_repo_logo_bytes() -> bytes | None:
    for p in ["assets/logo_petorca.png", "assets/logo_petorca.jpg", "assets/logo_petorca.jpeg"]:
        if os.path.exists(p):
            with open(p, "rb") as f:
                return f.read()
    return None

def current_logo_bytes() -> bytes | None:
    return st.session_state.logo_bytes or get_repo_logo_bytes()

def load_data_from_json(file) -> None:
    try:
        obj = json.load(file)
        d = st.session_state.data
        d["fondo_inicial"] = float(obj.get("fondo_inicial", 0))
        gastos = obj.get("gastos", [])
        fixed = []
        for g in gastos:
            fixed.append({
                "fecha": g.get("fecha"),
                "monto": float(g.get("monto", 0)),
                "detalle": g.get("detalle") or g.get("descripcion") or "",
                "tipo_doc": g.get("tipo_doc", ""),
                "nro_doc": g.get("nro_doc", ""),
                "proveedor": g.get("proveedor", ""),
                "nombre_doc": g.get("nombre_doc"),
                "bytes_doc": None,
            })
        d["gastos"] = fixed
        d["meta"] = obj.get("meta", d["meta"])
        d["resumen"] = obj.get("resumen", d["resumen"])
        d["firmas"] = obj.get("firmas", d["firmas"])
        st.success("Datos cargados desde JSON.")
    except Exception as e:
        st.error(f"Error al leer JSON: {e}")

def export_data_json() -> bytes:
    d = st.session_state.data
    data = {
        "fondo_inicial": d["fondo_inicial"],
        "meta": d["meta"],
        "resumen": d["resumen"],
        "firmas": d["firmas"],
        "gastos": [
            {
                "fecha": g["fecha"], "monto": g["monto"], "detalle": g["detalle"],
                "tipo_doc": g.get("tipo_doc",""), "nro_doc": g.get("nro_doc",""),
                "proveedor": g.get("proveedor",""), "nombre_doc": g.get("nombre_doc")
            } for g in d["gastos"]
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

def gastos_df() -> pd.DataFrame:
    df = pd.DataFrame(st.session_state.data["gastos"])
    if not df.empty:
        df = df.assign(
            Fecha=pd.to_datetime(df["fecha"]).dt.date,
            TipoDoc=df.get("tipo_doc", ""),
            NroDoc=df.get("nro_doc", ""),
            Detalle=df["detalle"],
            Proveedor=df.get("proveedor", ""),
            Monto=pd.to_numeric(df["monto"], errors="coerce").fillna(0.0),
            Documento=df["nombre_doc"].fillna("—"),
        )[["Fecha","TipoDoc","NroDoc","Detalle","Proveedor","Monto","Documento"]]
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

def add_gasto(fecha: date, detalle: str, monto: float, doc_file, tipo_doc: str, nro_doc: str, proveedor: str):
    nombre_doc = None; bytes_doc = None
    if doc_file is not None:
        nombre_doc = doc_file.name
        bytes_doc = doc_file.read()
    st.session_state.data["gastos"].append({
        "fecha": fecha.strftime("%Y-%m-%d"),
        "monto": float(monto), "detalle": detalle,
        "tipo_doc": tipo_doc, "nro_doc": nro_doc, "proveedor": proveedor,
        "nombre_doc": nombre_doc, "bytes_doc": bytes_doc
    })

def remove_gastos(indices: List[int]):
    for idx in sorted(indices, reverse=True):
        if 0 <= idx < len(st.session_state.data["gastos"]):
            st.session_state.data["gastos"].pop(idx)

# ============================ PDF helpers (Unicode) ============================

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

# ============================ Exports ============================

def export_pdf() -> bytes:
    df = gastos_df()
    fondo, total, saldo, cantidad = totals()
    meta = st.session_state.data["meta"]
    res  = st.session_state.data["resumen"]
    firmas = st.session_state.data["firmas"]

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    unicode_ok = set_unicode_font(pdf)

    # Logo (subido o del repo)
    logo_b = current_logo_bytes()
    if logo_b:
        try:
            bio_logo = io.BytesIO(logo_b)
            pdf.image(bio_logo, x=10, y=8, w=30)
        except Exception:
            pass

    # ---- Cabecera (planilla 1) ----
    pdf.set_font(pdf.font_family, "B", 10)
    hdr1 = ["Tipo de Fondo","Responsable del fondo","Institución","Fecha Rendición","N° Rendición"]
    w1   = [40, 50, 35, 35, 30]
    for h, w in zip(hdr1, w1):
        pdf.cell(w, 7, safe_text(h, unicode_ok), 1, 0, "C")
    pdf.ln(7)
    pdf.set_font(pdf.font_family, "", 10)
    vals1 = [
        meta.get("tipo_fondo",""), meta.get("responsable",""), meta.get("institucion",""),
        meta.get("fecha_rendicion",""), meta.get("n_rendicion","")
    ]
    for v, w in zip(vals1, w1):
        pdf.cell(w, 8, safe_text(v or "", unicode_ok), 1, 0, "L")
    pdf.ln(10)

    # REX fila
    pdf.set_font(pdf.font_family, "B", 10)
    for h, w in zip(["N° REX","Fecha REX"], [95,95]):
        pdf.cell(w, 7, safe_text(h, unicode_ok), 1, 0, "C")
    pdf.ln(7)
    pdf.set_font(pdf.font_family, "", 10)
    for v, w in zip([meta.get("n_rex",""), meta.get("fecha_rex","")], [95,95]):
        pdf.cell(w, 8, safe_text(v or "", unicode_ok), 1, 0, "L")
    pdf.ln(10)

    # ---- Tabla detalle (20 filas) ----
    col_headers = ["N°","Fecha del gasto","Tipo documento","N° Documento","Detalle del gasto","Nombre Proveedor","Monto"]
    col_widths  = [10,20,20,20,75,30,15]
    pdf.set_font(pdf.font_family, "B", 9)
    for h, w in zip(col_headers, col_widths):
        pdf.cell(w, 7, safe_text(h, unicode_ok), 1, 0, "C")
    pdf.ln(7)

    pdf.set_font(pdf.font_family, "", 9)
    rows = df.to_dict("records") if not df.empty else []
    for i in range(20):
        row = rows[i] if i < len(rows) else None
        pdf.cell(col_widths[0], 7, str(i+1), 1, 0, "C")
        if row:
            pdf.cell(col_widths[1], 7, row["Fecha"].strftime("%Y-%m-%d"), 1)
            pdf.cell(col_widths[2], 7, safe_text(str(row["TipoDoc"]), unicode_ok), 1)
            pdf.cell(col_widths[3], 7, safe_text(str(row["NroDoc"]), unicode_ok), 1)
            pdf.cell(col_widths[4], 7, safe_text(str(row["Detalle"])[:60], unicode_ok), 1)
            pdf.cell(col_widths[5], 7, safe_text(str(row["Proveedor"])[:24], unicode_ok), 1)
            pdf.cell(col_widths[6], 7, money(float(row["Monto"])), 1, 0, "R")
        else:
            for w in col_widths[1:]:
                pdf.cell(w, 7, "", 1)
        pdf.ln(7)

    pdf.set_font(pdf.font_family, "B", 9)
    pdf.cell(sum(col_widths[:-1]), 7, safe_text("Monto Total del Gasto", unicode_ok), 1, 0, "R")
    pdf.cell(col_widths[-1], 7, money(total), 1, 0, "R")

    # ---- Página 2: Resumen + Firmas ----
    pdf.add_page()
    unicode_ok = set_unicode_font(pdf)
    if logo_b:
        try:
            bio_logo = io.BytesIO(logo_b)
            pdf.image(bio_logo, x=10, y=8, w=30)
        except Exception:
            pass

    pdf.set_font(pdf.font_family, "B", 10)
    top_labels = ["Tipo de Fondo","Nombre Responsable del Fondo","N° RUT","Institución","N° Rendición"]
    top_w      = [35,75,25,35,20]
    for h,w in zip(top_labels, top_w): pdf.cell(w, 7, safe_text(h, unicode_ok), 1, 0, "C")
    pdf.ln(7)
    pdf.set_font(pdf.font_family, "", 10)
    top_vals = [meta.get("tipo_fondo",""), meta.get("responsable",""), meta.get("rut",""),
                meta.get("institucion",""), meta.get("n_rendicion","")]
    for v,w in zip(top_vals, top_w): pdf.cell(w, 8, safe_text(v or "", unicode_ok), 1, 0, "L")
    pdf.ln(8)

    pdf.set_font(pdf.font_family, "B", 10)
    sec_labels = ["Cargo","Mes que Rinde","N° REX","Fecha REX","Observaciones"]
    sec_w      = [35,35,20,25,75]
    for h,w in zip(sec_labels, sec_w): pdf.cell(w, 7, safe_text(h, unicode_ok), 1, 0, "C")
    pdf.ln(7)
    pdf.set_font(pdf.font_family, "", 10)
    sec_vals = [meta.get("cargo",""), meta.get("mes_que_rinde",""), meta.get("n_rex",""),
                meta.get("fecha_rex",""), meta.get("observaciones","")]
    for v,w in zip(sec_vals, sec_w): pdf.cell(w, 10, safe_text(v or "", unicode_ok), 1, 0, "L")
    pdf.ln(12)

    pdf.set_font(pdf.font_family, "B", 10)
    pdf.cell(95, 7, safe_text("N° Egreso Contable Inicial del Fondo", unicode_ok), 1, 0, "L")
    pdf.cell(95, 7, safe_text("Fecha de Egreso Inicial del Fondo", unicode_ok), 1, 0, "L")
    pdf.ln(7)
    pdf.set_font(pdf.font_family, "", 10)
    pdf.cell(95, 8, safe_text(meta.get("n_egreso_inicial",""), unicode_ok), 1, 0, "L")
    pdf.cell(95, 8, safe_text(meta.get("fecha_egreso_inicial",""), unicode_ok), 1, 0, "L")
    pdf.ln(10)

    pdf.set_font(pdf.font_family, "B", 10)
    pdf.cell(190, 7, safe_text("CUADRO RESUMEN RENDICION", unicode_ok), 1, 0, "C"); pdf.ln(7)
    pdf.set_font(pdf.font_family, "", 10)
    filas = [
        ("Saldo Inicial/Rendición Mes Anterior", st.session_state.data["resumen"]["saldo_inicial_mes_ant"]),
        ("Monto Recibido Mes anterior",          st.session_state.data["resumen"]["monto_recibido_mes_ant"]),
        ("Monto Gasto del mes",                   total),
        ("Monto del gasto del mes Transporte",    st.session_state.data["resumen"]["monto_gasto_transporte"]),
    ]
    for label, val in filas:
        pdf.cell(150, 8, safe_text(label, unicode_ok), 1, 0, "L")
        pdf.cell(40, 8, money(float(val)), 1, 0, "R")
        pdf.ln(8)
    saldo_final = float(st.session_state.data["resumen"]["saldo_inicial_mes_ant"]) + float(st.session_state.data["resumen"]["monto_recibido_mes_ant"]) - float(total) - float(st.session_state.data["resumen"]["monto_gasto_transporte"])
    pdf.set_font(pdf.font_family, "B", 10)
    pdf.cell(150, 8, safe_text("Saldo Final", unicode_ok), 1, 0, "L")
    pdf.cell(40, 8, money(saldo_final), 1, 0, "R")
    pdf.ln(16)

    # Firmas
    pdf.set_font(pdf.font_family, "", 10)
    def firma_block(titulo: str, ancho=90):
        pdf.cell(ancho, 8, "_"*30, 0, 0, "C"); pdf.ln(5)
        x = pdf.get_x() - ancho
        y = pdf.get_y()
        pdf.set_xy(x, y)
        pdf.cell(ancho, 6, safe_text(titulo, unicode_ok), 0, 0, "C")

    x0 = pdf.get_x(); y0 = pdf.get_y()
    firma_block(firmas.get("encargado","Encargado/a del Fondo"))
    pdf.set_xy(x0+100, y0)
    firma_block(firmas.get("directora","Director/a Ejecutiva"))
    pdf.ln(15)

    pdf.set_font(pdf.font_family, "B", 9)
    pdf.cell(190, 7, safe_text("USO EXCLUSIVO SERVICIO LOCAL DE EDUCACIÓN PÚBLICA DE PETORCA", unicode_ok), 1, 0, "C")
    pdf.ln(9)
    pdf.set_font(pdf.font_family, "", 9)
    blocks = [
        (firmas.get("revisor1","Nombre/Firma Revisor/a 1"), firmas.get("vobo_jefe_unidad","V°B° JEFE UNIDAD")),
        (firmas.get("vobo_finanzas","V°B° UNIDAD DE FINANZAS"), firmas.get("contab_finanzas","CONTABILIDAD Y FINANZAS")),
        ("", firmas.get("vobo_admin_finanzas","V°B° JEFE/(A) ADMINISTRACIÓN Y FINANZAS")),
    ]
    for left, right in blocks:
        pdf.cell(95, 8, "_"*30, 0, 0, "C")
        pdf.cell(95, 8, "_"*30, 0, 0, "C"); pdf.ln(5)
        pdf.cell(95, 6, safe_text(left, unicode_ok), 0, 0, "C")
        pdf.cell(95, 6, safe_text(right, unicode_ok), 0, 0, "C"); pdf.ln(10)

    out = io.BytesIO()
    pdf.output(out)
    return out.getvalue()

def export_excel() -> bytes:
    # Dos hojas: Detalle y Resumen, con logo y bordes/merges
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.drawing.image import Image as XLImage
    # Pillow es opcional; si no está, omitimos logo en Excel
    try:
        from PIL import Image as PILImage
        has_pil = True
    except Exception:
        has_pil = False

    df = gastos_df()
    d  = st.session_state.data
    meta, res = d["meta"], d["resumen"]
    fondo, total, saldo, _ = totals()

    thin = Side(style="thin", color="000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    wb = Workbook()

    # ---------- Hoja 1: Detalle ----------
    ws = wb.active
    ws.title = "Detalle"
    for i,width in enumerate([5,14,16,16,40,24,12], start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    logo_b = current_logo_bytes()
    if logo_b and has_pil:
        try:
            img = XLImage(PILImage.open(io.BytesIO(logo_b)))
            img.width, img.height = 110, 55
            ws.add_image(img, "A1")
        except Exception:
            pass

    r = 1
    # Cabecera
    headers = ["Tipo de Fondo","Responsable del fondo","Institución","Fecha Rendición","N° Rendición"]
    for i,h in enumerate(headers, start=1):
        c = ws.cell(row=r, column=i, value=h); c.font = Font(bold=True); c.alignment = Alignment(horizontal="center"); c.border = border
    r += 1
    vals = [meta.get("tipo_fondo",""), meta.get("responsable",""), meta.get("institucion",""),
            meta.get("fecha_rendicion",""), meta.get("n_rendicion","")]
    for i,v in enumerate(vals, start=1):
        c = ws.cell(row=r, column=i, value=v); c.border = border
    r += 2

    # REX fila (merge 1-3 y 4-5)
    for i,h in enumerate(["N° REX","Fecha REX"], start=1):
        c = ws.cell(row=r, column=(1 if i==1 else 4), value=h); c.font = Font(bold=True); c.alignment = Alignment(horizontal="center"); c.border = border
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=5)
    r += 1
    c = ws.cell(row=r, column=1, value=meta.get("n_rex","")); c.border = border
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    c = ws.cell(row=r, column=4, value=meta.get("fecha_rex","")); c.border = border
    ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=5)
    r += 2

    # Encabezado tabla
    cols = ["N°","Fecha del gasto","Tipo documento","N° Documento","Detalle del gasto","Nombre Proveedor","Monto"]
    for i,h in enumerate(cols, start=1):
        c = ws.cell(row=r, column=i, value=h); c.font = Font(bold=True); c.alignment = Alignment(horizontal="center"); c.border = border
    r += 1

    # 20 filas
    rows = df.to_dict("records") if not df.empty else []
    for i in range(20):
        c = ws.cell(row=r+i, column=1, value=i+1); c.border = border; c.alignment = Alignment(horizontal="center")
        if i < len(rows):
            row = rows[i]
            data_row = [
                row["Fecha"].strftime("%Y-%m-%d"), row["TipoDoc"], row["NroDoc"],
                row["Detalle"], row["Proveedor"], float(row["Monto"])
            ]
        else:
            data_row = ["","","","","", None]
        for j,val in enumerate(data_row, start=2):
            c = ws.cell(row=r+i, column=j, value=val); c.border = border
            if j == 7:  # monto
                c.number_format = '#,##0'

    r_tot = r + 20
    for j in range(1,7):
        c = ws.cell(row=r_tot, column=j, value=("" if j<6 else "Monto Total del Gasto")); c.border = border
        if j==6:
            c.font = Font(bold=True); c.alignment = Alignment(horizontal="right")
    c = ws.cell(row=r_tot, column=7, value=total); c.border = border; c.font = Font(bold=True); c.number_format = '#,##0'

    # ---------- Hoja 2: Resumen ----------
    ws2 = wb.create_sheet("Resumen")
    for i,width in enumerate([20,35,15,25,15], start=1):
        ws2.column_dimensions[get_column_letter(i)].width = width

    if logo_b and has_pil:
        try:
            img2 = XLImage(PILImage.open(io.BytesIO(logo_b)))
            img2.width, img2.height = 110, 55
            ws2.add_image(img2, "A1")
        except Exception:
            pass

    def hdr(row, labels):
        for i,h in enumerate(labels, start=1):
            c = ws2.cell(row=row, column=i, value=h); c.font = Font(bold=True); c.alignment = Alignment(horizontal="center"); c.border = border

    def row_vals(row, vals):
        for i,v in enumerate(vals, start=1):
            c = ws2.cell(row=row, column=i, value=v); c.border = border

    def merge_write(row, c1, c2, value, align="left"):
        ws2.merge_cells(start_row=row, start_column=c1, end_row=row, end_column=c2)
        cell = ws2.cell(row=row, column=c1, value=value)
        cell.border = border
        cell.alignment = Alignment(horizontal=("center" if align=="center" else "left"))
        # bordes a todo el rango
        for col in range(c1, c2+1):
            ws2.cell(row=row, column=col).border = border

    r = 1
    hdr(r, ["Tipo de Fondo","Nombre Responsable del Fondo","N° RUT","Institución","N° Rendición"]); r+=1
    row_vals(r, [meta.get("tipo_fondo",""), meta.get("responsable",""), meta.get("rut",""), meta.get("institucion",""), meta.get("n_rendicion","")]); r+=2

    hdr(r, ["Cargo","Mes que Rinde","N° REX","Fecha REX","Observaciones"]); r+=1
    row_vals(r, [meta.get("cargo",""), meta.get("mes_que_rinde",""), meta.get("n_rex",""), meta.get("fecha_rex",""), meta.get("observaciones","")]); r+=2

    # Egreso inicial (usando merges seguros)
    merge_write(r, 1, 3, "N° Egreso Contable Inicial del Fondo", align="center")
    merge_write(r, 4, 5, "Fecha de Egreso Inicial del Fondo", align="center")
    r += 1
    merge_write(r, 1, 3, meta.get("n_egreso_inicial",""))
    merge_write(r, 4, 5, meta.get("fecha_egreso_inicial",""))
    r += 2

    # Cuadro Resumen
    merge_write(r, 1, 5, "CUADRO RESUMEN RENDICION", align="center"); r+=1
    resumen_rows = [
        ("Saldo Inicial/Rendición Mes Anterior", res["saldo_inicial_mes_ant"]),
        ("Monto Recibido Mes anterior",          res["monto_recibido_mes_ant"]),
        ("Monto Gasto del mes",                   total),
        ("Monto del gasto del mes Transporte",    res["monto_gasto_transporte"]),
    ]
    for etiqueta, val in resumen_rows:
        merge_write(r, 1, 4, etiqueta)
        c2 = ws2.cell(row=r, column=5, value=float(val)); c2.border = border; c2.number_format = '#,##0'
        r+=1
    saldo_final = float(res["saldo_inicial_mes_ant"]) + float(res["monto_recibido_mes_ant"]) - float(total) - float(res["monto_gasto_transporte"])
    merge_write(r, 1, 4, "Saldo Final")
    c2 = ws2.cell(row=r, column=5, value=saldo_final); c2.border = border; c2.number_format = '#,##0'; c2.font = Font(bold=True)
    r += 3

    # Firmas
    f = st.session_state.data["firmas"]
    firma_rows = [
        (f.get("encargado","Encargado/a del Fondo"), f.get("directora","Director/a Ejecutiva")),
        (f.get("revisor1","Nombre/Firma Revisor/a 1"), f.get("vobo_jefe_unidad","V°B° JEFE UNIDAD")),
        (f.get("vobo_finanzas","V°B° UNIDAD DE FINANZAS"), f.get("contab_finanzas","CONTABILIDAD Y FINANZAS")),
        ("", f.get("vobo_admin_finanzas","V°B° JEFE/(A) ADMINISTRACIÓN Y FINANZAS")),
    ]
    for left, right in firma_rows:
        merge_write(r, 1, 2, "____________________________", align="center")
        merge_write(r, 4, 5, "____________________________", align="center")
        r += 1
        merge_write(r, 1, 2, left, align="center")
        merge_write(r, 4, 5, right, align="center")
        r += 2

    bio = io.BytesIO(); wb.save(bio); return bio.getvalue()

# ============================ UI ============================

init_state()
st.title("Rendición de Fondos Fijos P01 – SLEP Petorca")

with st.sidebar:
    st.header("Configuración")
    d = st.session_state.data

    fondo_inicial = st.number_input("Fondo inicial", min_value=0.0, step=1000.0,
                                    value=float(d["fondo_inicial"]))
    if st.button("Guardar fondo"):
        d["fondo_inicial"] = float(fondo_inicial)
        st.success("Fondo inicial actualizado.")

    st.divider()
    st.subheader("Cabecera")
    meta = d["meta"]
    meta["tipo_fondo"]     = st.text_input("Tipo de Fondo", meta["tipo_fondo"])
    meta["responsable"]    = st.text_input("Responsable del fondo", meta["responsable"])
    meta["rut"]            = st.text_input("N° RUT", meta["rut"])
    meta["institucion"]    = st.text_input("Institución", meta["institucion"])
    meta["n_rendicion"]    = st.text_input("N° Rendición", meta["n_rendicion"])
    meta["fecha_rendicion"]= st.text_input("Fecha Rendición (YYYY-MM-DD)", meta["fecha_rendicion"])
    meta["cargo"]          = st.text_input("Cargo", meta["cargo"])
    meta["mes_que_rinde"]  = st.text_input("Mes que Rinde", meta["mes_que_rinde"])
    meta["n_rex"]          = st.text_input("N° REX", meta["n_rex"])
    meta["fecha_rex"]      = st.text_input("Fecha REX (YYYY-MM-DD)", meta["fecha_rex"])
    meta["observaciones"]  = st.text_area("Observaciones", meta["observaciones"])
    meta["n_egreso_inicial"] = st.text_input("N° Egreso contable inicial", meta["n_egreso_inicial"])
    meta["fecha_egreso_inicial"] = st.text_input("Fecha egreso inicial (YYYY-MM-DD)", meta["fecha_egreso_inicial"])

    st.divider()
    st.subheader("Cuadro Resumen")
    res = d["resumen"]
    res["saldo_inicial_mes_ant"]   = st.number_input("Saldo Inicial/Rendición Mes Anterior", value=float(res["saldo_inicial_mes_ant"]))
    res["monto_recibido_mes_ant"]  = st.number_input("Monto Recibido Mes Anterior", value=float(res["monto_recibido_mes_ant"]))
    res["monto_gasto_transporte"]  = st.number_input("Monto gasto del mes Transporte", value=float(res["monto_gasto_transporte"]))

    st.divider()
    st.subheader("Firmas (PDF/Excel)")
    f = d["firmas"]
    f["encargado"] = st.text_input("Encargado/a del Fondo", f["encargado"])
    f["directora"] = st.text_input("Director/a Ejecutiva", f["directora"])
    f["revisor1"] = st.text_input("Nombre/Firma Revisor/a 1", f["revisor1"])
    f["revisor2"] = st.text_input("Nombre/Firma Revisor/a 2", f["revisor2"])
    f["vobo_jefe_unidad"] = st.text_input("V°B° JEFE UNIDAD", f["vobo_jefe_unidad"])
    f["vobo_finanzas"] = st.text_input("V°B° UNIDAD DE FINANZAS", f["vobo_finanzas"])
    f["contab_finanzas"] = st.text_input("CONTABILIDAD Y FINANZAS", f["contab_finanzas"])
    f["vobo_admin_finanzas"] = st.text_input("V°B° JEFE/(A) ADMINISTRACIÓN Y FINANZAS", f["vobo_admin_finanzas"])

    st.divider()
    st.caption("Logo para PDF/Excel (si no subes, se usa assets/logo_petorca.* si existe)")
    logo_file = st.file_uploader("Logo (PNG/JPG)", type=["png","jpg","jpeg"], key="logo_up")
    if logo_file is not None:
        st.session_state.logo_bytes = logo_file.read()
        st.session_state.logo_name = logo_file.name
        st.success(f"Logo cargado: {st.session_state.logo_name}")

    st.divider()
    st.caption("Importar / Exportar datos")
    up = st.file_uploader("Importar datos JSON", type=["json"], key="json_up")
    if up is not None and st.button("Cargar JSON"):
        load_data_from_json(up)
    st.download_button("Exportar datos a JSON", data=export_data_json(),
                       file_name="rendicion_datos.json", mime="application/json")

# ---------------------------- Registro de gastos ----------------------------
st.subheader("Registrar gasto")
with st.form("form_gasto", clear_on_submit=True):
    c1,c2,c3,c4,c5,c6 = st.columns([1.1,1.3,1.3,2.2,1.8,1.3])
    with c1: fch = st.date_input("Fecha", value=date.today())
    with c2: tipo = st.selectbox("Tipo documento", ["Boleta","Factura","Transferencia","Otro"], index=0)
    with c3: nro  = st.text_input("N° Documento")
    with c4: det  = st.text_input("Detalle del gasto")
    with c5: prov = st.text_input("Nombre Proveedor")
    with c6: mto  = st.number_input("Monto", min_value=0.0, step=1000.0)
    doc = st.file_uploader("Adjunto (opcional)")
    if st.form_submit_button("Agregar"):
        if det.strip() == "":
            st.error("El detalle es obligatorio.")
        else:
            add_gasto(fch, det, mto, doc, tipo, nro, prov); st.success("Gasto agregado.")

# ---------------------------- Tabla ----------------------------
st.subheader("Gastos registrados")
df = gastos_df()
if df.empty:
    st.info("Aún no hay gastos.")
else:
    showing = df.copy(); showing["Seleccionar"] = False
    edited = st.data_editor(
        showing,
        column_order=["Fecha","TipoDoc","NroDoc","Detalle","Proveedor","Monto","Documento","Seleccionar"],
        hide_index=False, use_container_width=True, num_rows="static"
    )
    selected_indices = edited.index[edited["Seleccionar"] == True].tolist()
    if st.button("Eliminar seleccionados"):
        remove_gastos(selected_indices); st.rerun()

# ---------------------------- Resumen + Gráfico ----------------------------
st.subheader("Resumen")
fondo, total, saldo, cantidad = totals()
c1,c2,c3,c4 = st.columns(4)
c1.metric("Fondo inicial", money(fondo))
c2.metric("Total gastos", money(total))
c3.metric("Saldo", money(saldo))
c4.metric("Cantidad", f"{cantidad}")

st.subheader("Distribución")
labels = ["Gastos", "Saldo"]
vals = [max(total,0.0), max(saldo,0.0)]
if sum(vals) <= 0:
    st.info("Aún no hay datos para graficar. Configura el fondo inicial o registra gastos.")
else:
    fig, ax = plt.subplots()
    ax.pie(vals, labels=labels, autopct="%1.1f%%"); ax.axis("equal")
    st.pyplot(fig)

# ---------------------------- Exportaciones ----------------------------
st.subheader("Exportaciones")
colx, colp = st.columns(2)
with colx:
    st.download_button("Descargar Excel", data=export_excel(),
        file_name="rendicion_gastos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
with colp:
    st.download_button("Descargar PDF", data=export_pdf(),
        file_name="rendicion_gastos.pdf", mime="application/pdf")

# ---------------------------- Adjuntos ----------------------------
st.subheader("Documentos adjuntos")
if len(st.session_state.data["gastos"]) == 0:
    st.caption("No hay documentos adjuntos aún.")
else:
    for i, g in enumerate(st.session_state.data["gastos"]):
        if g.get("bytes_doc"):
            st.download_button(f"Descargar '{g.get('nombre_doc','documento')}'",
                               data=g["bytes_doc"], file_name=g.get("nombre_doc","documento"))
        else:
            if g.get("nombre_doc"):
                st.caption(f"{i+1}. {g.get('nombre_doc')} (no embebido)")
st.caption("⚠️ Nota: Los archivos subidos viven en la sesión. Usa Exportar/Importar JSON para cargar los datos.")
