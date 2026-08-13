import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from supabase import create_client, Client
from datetime import datetime
import io
import json
import os

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="ISH - Clínica San Rafael", page_icon="🏥", layout="wide")

# --- CONEXIÓN SUPABASE ---
@st.cache_resource
def init_supabase():
    url = "https://TU_PROYECTO.supabase.co"
    key = "TU_API_KEY"
    return create_client(url, key)

supabase = init_supabase()

# --- CARGAR PREGUNTAS ---
@st.cache_data
def load_questions():
    with open("preguntas_ish.json", "r", encoding="utf-8") as f:
        return json.load(f)

preguntas_data = load_questions()

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { border: 1px solid #e6e6e6; background: white; padding: 15px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    h1, h2, h3 { color: #0056b3; }
    .css-1d391kg { padding-top: 2rem; }
    </style>
""", unsafe_allow_html=True)

# --- FUNCIONES ---
def calcular_indice(estructural, no_estructural, funcional):
    total = (estructural + no_estructural + funcional) / 3
    if total >= 0.66:
        clase, msg = "A", "Alta probabilidad de funcionar. Continuar con medidas de mejora."
    elif total >= 0.36:
        clase, msg = "B", "Probablemente funcione. Intervenciones a corto plazo."
    else:
        clase, msg = "C", "Baja probabilidad. Intervenciones urgentes requeridas."
    return total, clase, msg

def get_evaluaciones():
    try:
        response = supabase.table("evaluaciones_ish").select("*").order("fecha_evaluacion", desc=True).execute()
        return pd.DataFrame(response.data)
    except:
        return pd.DataFrame()

# --- HEADER CON LOGOS ---
col1, col2, col3 = st.columns([1, 3, 1])

with col1:
    st.image("assets/logo_clinica.png", use_container_width=True)

with col2:
    st.markdown("<h1 style='text-align: center; margin-top: 20px;'>Índice de Seguridad Hospitalaria (ISH v2)</h1>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center; color: #6c757d;'>Clínica San Rafael Alta Complejidad SAS | Sabanalarga, Atlántico</h4>", unsafe_allow_html=True)

with col3:
    st.image("assets/vigilado.png", use_container_width=True)

st.markdown("<p style='text-align: center; color: #6c757d;'>Niveles III y IV | 365 Trabajadores | Cobertura: Sabanalarga, Baranoa, Luruaco y Corregimientos</p><hr>", unsafe_allow_html=True)

# --- MENÚ ---
menu = st.sidebar.selectbox("Menú", ["📊 Dashboard", "📋 Nueva Evaluación", "📥 Exportar (CRUED)"])

if menu == "📊 Dashboard":
    df_eval = get_evaluaciones()
    if df_eval.empty:
        st.warning("No hay evaluaciones registradas aún.")
    else:
        latest = df_eval.iloc[0]
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Índice Total", f"{latest['indice_total']:.2f}", delta=latest['clasificacion'])
        col2.metric("Clasificación OMS", latest['clasificacion'])
        col3.metric("Autonomía Post-Evento", f"{latest['autonomia_horas']} Horas")
        col4.metric("Talento Humano", "365 Trabajadores")
        
        c1, c2 = st.columns([1, 2])
        with c1:
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number", value=latest['indice_total'],
                gauge={'axis': {'range': [0, 1]},
                       'bar': {'color': "#0056b3"},
                       'steps': [{'range': [0, 0.35], 'color': '#dc3545'}, {'range': [0.35, 0.66], 'color': '#ffc107'}, {'range': [0.66, 1], 'color': '#28a745'}]}
            ))
            fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=0, b=0))
            st.plotly_chart(fig_gauge, use_container_width=True)
            
        with c2:
            modulos = ['Estructural', 'No Estructural', 'Funcional']
            valores = [latest['indice_estructural'], latest['indice_no_estructural'], latest['indice_funcional']]
            fig_radar = go.Figure(data=go.Scatterpolar(r=valores+[valores[0]], theta=modulos+[modulos[0]], fill='toself', line_color='#0056b3'))
            fig_radar.update_layout(polar=dict(radialaxis=dict(range=[0, 1], visible=True)), height=300, showlegend=False)
            st.plotly_chart(fig_radar, use_container_width=True)
            
        st.markdown("#### 🗺️ Área de Influencia (Atlántico)")
        data_mapa = pd.DataFrame({
            'Municipio': ['Sabanalarga (Sede)', 'Baranoa', 'Luruaco'],
            'Lat': [10.6316, 10.7990, 10.5940], 'Lon': [-74.9150, -74.9180, -75.1410],
            'Tipo': ['Principal III-IV', 'Referencia', 'Referencia']
        })
        fig_map = px.scatter_mapbox(data_mapa, lat="Lat", lon="Lon", hover_name="Municipio", color="Tipo", zoom=9, height=400)
        fig_map.update_layout(mapbox_style="carto-positron", margin={"r":0,"t":0,"l":0,"b":0})
        st.plotly_chart(fig_map, use_container_width=True)

elif menu == "📋 Nueva Evaluación":
    st.markdown("## Formulario ISH-APP 2022 (Estandarizado OMS/OPS)")
    with st.form("eval_form"):
        col1, col2 = st.columns(2)
        with col1:
            evaluador = st.text_input("Evaluador", "Coordinador SST Clínica San Rafael")
            fecha = st.date_input("Fecha", datetime.now())
        with col2:
            amenazas = st.multiselect("Amenazas", ["Sismo", "Incendio", "Inundación", "Materiales Peligrosos"])
        
        respuestas = {}
        for modulo, preguntas in preguntas_data.items():
            st.markdown(f"### Módulo: {modulo}")
            for p in preguntas:
                # Slider por pregunta: 0.0 (Nulo) a 1.0 (Presente)
                respuestas[f"{modulo}_{p['id']}"] = st.slider(
                    f"{p['id']}. {p['pregunta']}", 0.0, 1.0, 0.5, 0.1, key=f"{modulo}_{p['id']}"
                )
        
        submitted = st.form_submit_button("Calcular Índice y Guardar")
        if submitted:
            # Calcular promedios por módulo
            est_vals = [v for k, v in respuestas.items() if k.startswith("Estructural")]
            no_est_vals = [v for k, v in respuestas.items() if k.startswith("No Estructural")]
            func_vals = [v for k, v in respuestas.items() if k.startswith("Funcional")]
            
            est = sum(est_vals)/len(est_vals)
            no_est = sum(no_est_vals)/len(no_est_vals)
            func = sum(func_vals)/len(func_vals)
            
            total, clase, msg = calcular_indice(est, no_est, func)
            st.success(f"**Índice Calculado: {total:.2f} - Clase {clase}**\n\n{msg}")
            
            data = {
                "fecha_evaluacion": str(fecha), "evaluador": evaluador, "nivel_riesgo": ", ".join(amenazas),
                "indice_estructural": est, "indice_no_estructural": no_est, "indice_funcional": func,
                "indice_total": total, "clasificacion": clase,
                "autonomia_horas": 72 if clase == 'A' else (24 if clase == 'B' else 0)
            }
            try:
                supabase.table("evaluaciones_ish").insert(data).execute()
                st.balloons()
            except Exception as e:
                st.error(f"Error guardando en BD: {e}")

elif menu == "📥 Exportar (CRUED)":
    st.markdown("## Exportación para Auditorías")
    df_eval = get_evaluaciones()
    if not df_eval.empty:
        st.dataframe(df_eval, use_container_width=True)
        
        def to_excel(df):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Reporte_CRUED')
            return output.getvalue()
            
        st.download_button("📥 Descargar Excel (CRUED)", to_excel(df_eval), 
                           file_name=f'Reporte_ISH_SanRafael_{datetime.now().strftime("%Y%m%d")}.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        st.warning("Sin datos para exportar.")
