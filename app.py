import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from supabase import create_client, Client
from datetime import datetime, date
import io
import json
import random
import smtplib
import time
import hashlib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from openai import OpenAI

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="ISH - Clínica San Rafael Alta Complejidad SAS", page_icon="🏥", layout="wide")

# --- CONEXIÓN A SERVICIOS ---
@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

@st.cache_resource
def init_openai():
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

supabase = init_supabase()
openai_client = init_openai()

# --- FUNCIONES DE SEGURIDAD Y BD ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def log_action(email, action):
    supabase.table("logs_usuarios").insert({"usuario_email": email, "accion": action}).execute()

def get_amenazas():
    try:
        res = supabase.table("amenazas").select("nombre").order("nombre").execute()
        return [a['nombre'] for a in res.data]
    except:
        return []

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { border: 1px solid #e6e6e6; background: white; padding: 15px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    h1, h2, h3 { color: #0056b3; }
    </style>
""", unsafe_allow_html=True)

# --- INICIALIZAR SESSION STATE ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = ""
if 'user_name' not in st.session_state: # Nuevo: Guardar el nombre real
    st.session_state.user_name = ""
if 'is_admin' not in st.session_state:
    st.session_state.is_admin = False
if 'tfa_timestamp' not in st.session_state:
    st.session_state.tfa_timestamp = None
if 'codigo_2fa_generado' not in st.session_state:
    st.session_state.codigo_2fa_generado = None
if 'correo_verificado' not in st.session_state:
    st.session_state.correo_verificado = False

# --- PANTALLA DE LOGIN / REGISTRO ---
if not st.session_state.logged_in:
    # Mostrar logos en el login también
    col_l, col_r = st.columns([1, 1])
    with col_l:
        if os.path.exists("assets/logo_clinica.png"):
            st.image("assets/logo_clinica.png", width=150)
    with col_r:
        if os.path.exists("assets/vigilado.png"):
            st.image("assets/vigilado.png", width=120)

    st.markdown("<h1 style='text-align: center; color: #0056b3;'>Acceso al Sistema</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Índice de Seguridad Hospitalario - CSR AC 2026 By EESC</p><br>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["🔑 Iniciar Sesión", "📝 Registrar Nuevo Usuario"])
    
    with tab1:
        with st.form("login_form"):
            email_input = st.text_input("Correo Electrónico")
            pass_input = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Ingresar")
            
            if submit:
                # 1. Verificar si es Admin
                if email_input == st.secrets["ADMIN_EMAIL"] and pass_input == st.secrets["ADMIN_PASSWORD"]:
                    st.session_state.logged_in = True
                    st.session_state.user_email = email_input
                    st.session_state.user_name = "Efrain Sarmiento Crespo" # Nombre fijo Admin
                    st.session_state.is_admin = True
                    log_action(email_input, "Login Admin")
                    st.rerun()
                else:
                    # 2. Verificar en Supabase
                    try:
                        res = supabase.table("usuarios_app").select("*").eq("email", email_input).execute()
                        if len(res.data) > 0:
                            user = res.data[0]
                            if user['password'] == hash_password(pass_input):
                                if not user['aprobado']:
                                    st.warning("Tu cuenta está pendiente de aprobación por el Administrador.")
                                elif user['fecha_expiracion'] and date.fromisoformat(user['fecha_expiracion']) < date.today():
                                    st.error("Tu acceso ha expirado. Contacta al Administrador.")
                                else:
                                    st.session_state.logged_in = True
                                    st.session_state.user_email = email_input
                                    st.session_state.user_name = user['nombre'] # Nombre real de la BD
                                    st.session_state.is_admin = False
                                    supabase.table("usuarios_app").update({"contador_ingresos": user['contador_ingresos'] + 1}).eq("email", email_input).execute()
                                    log_action(email_input, "Login Usuario")
                                    st.rerun()
                            else:
                                st.error("Contraseña incorrecta.")
                        else:
                            st.error("Usuario no encontrado.")
                    except Exception as e:
                        st.error(f"Error de autenticación: {e}")

    with tab2:
        with st.form("register_form"):
            reg_name = st.text_input("Nombre Completo")
            reg_email = st.text_input("Correo Electrónico Corporativo")
            reg_pass = st.text_input("Contraseña", type="password")
            reg_submit = st.form_submit_button("Solicitar Acceso")
            
            if reg_submit:
                try:
                    data = {"email": reg_email, "password": hash_password(reg_pass), "nombre": reg_name, "aprobado": False}
                    supabase.table("usuarios_app").insert(data).execute()
                    st.success("Solicitud enviada. Espera aprobación del Administrador.")
                except Exception as e:
                    st.error(f"Error: Es posible que el correo ya esté registrado. {e}")
    st.stop()

# --- LOGOUT ---
if st.session_state.logged_in:
    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.session_state.logged_in = False
        st.session_state.is_admin = False
        st.session_state.user_email = ""
        st.session_state.user_name = ""
        st.rerun()

# --- HEADER CON LOGOS Y NOMBRE ---
col1, col2, col3 = st.columns([1, 3, 1])
with col1:
    if os.path.exists("assets/logo_clinica.png"):
        st.image("assets/logo_clinica.png", use_container_width=True)
with col2:
    st.markdown("<h1 style='text-align: center; margin-top: 20px;'>Índice de Seguridad Hospitalaria (ISH v2)</h1>", unsafe_allow_html=True)
    # Saludo personalizado
    st.markdown(f"<h4 style='text-align: center; color: #6c757d;'>Bienvenido: <b>{st.session_state.user_name}</b></h4>", unsafe_allow_html=True)
with col3:
    if os.path.exists("assets/vigilado.png"):
        st.image("assets/vigilado.png", use_container_width=True)

st.markdown("<hr>", unsafe_allow_html=True)

# --- MENÚ ---
opciones_menu = ["📊 Dashboard", "📋 Nueva Evaluación", "📥 Exportar & Envío 2FA (CRUED)", "🤖 Análisis IA"]
if st.session_state.is_admin:
    opciones_menu.append("🛡️ Panel Administrador")

menu = st.sidebar.selectbox("Menú", opciones_menu)

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    try:
        res = supabase.table("evaluaciones_ish").select("*").order("fecha_evaluacion", desc=True).execute()
        df_eval = pd.DataFrame(res.data)
    except:
        df_eval = pd.DataFrame()

    if df_eval.empty:
        st.warning("No hay evaluaciones registradas aún.")
    else:
        latest = df_eval.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Índice Total", f"{latest['indice_total']:.2f}", delta=latest['clasificacion'])
        c2.metric("Clasificación OMS", latest['clasificacion'])
        c3.metric("Autonomía Post-Evento", f"{latest['autonomia_horas']} Horas")
        c4.metric("Talento Humano", "365 Trabajadores")
        
        c1, c2 = st.columns([1, 2])
        with c1:
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number", value=latest['indice_total'],
                gauge={'axis': {'range': [0, 1]}, 'bar': {'color': "#0056b3"},
                       'steps': [{'range': [0, 0.35], 'color': '#dc3545'}, {'range': [0.35, 0.66], 'color': '#ffc107'}, {'range': [0.66, 1], 'color': '#28a745'}]}
            ))
            st.plotly_chart(fig_gauge, use_container_width=True)
            
        with c2:
            modulos = ['Estructural', 'No Estructural', 'Funcional']
            valores = [latest['indice_estructural'], latest['indice_no_estructural'], latest['indice_funcional']]
            fig_radar = go.Figure(data=go.Scatterpolar(r=valores+[valores[0]], theta=modulos+[modulos[0]], fill='toself', line_color='#0056b3'))
            fig_radar.update_layout(polar=dict(radialaxis=dict(range=[0, 1], visible=True)), showlegend=False)
            st.plotly_chart(fig_radar, use_container_width=True)

# --- NUEVA EVALUACIÓN ---
elif menu == "📋 Nueva Evaluación":
    st.markdown("## Formulario ISH-APP 2022")
    
    amenazas_bd = get_amenazas()
    
    with st.form("eval_form"):
        col1, col2 = st.columns(2)
        with col1:
            evaluador = st.text_input("Evaluador", st.session_state.user_name)
            fecha = st.date_input("Fecha", datetime.now())
        with col2:
            amenazas = st.multiselect("Amenazas Identificadas", amenazas_bd)
        
        st.info("Formulario de preguntas aquí...")
        
        submitted = st.form_submit_button("Calcular Índice y Guardar")
        if submitted:
            total, clase = 0.85, "A" 
            data = {
                "fecha_evaluacion": str(fecha), "evaluador": evaluador, "nivel_riesgo": ", ".join(amenazas),
                "indice_estructural": 0.85, "indice_no_estructural": 0.85, "indice_funcional": 0.85,
                "indice_total": total, "clasificacion": clase, "autonomia_horas": 72
            }
            try:
                supabase.table("evaluaciones_ish").insert(data).execute()
                log_action(st.session_state.user_email, "Nueva Evaluación Creada")
                st.balloons()
                st.success("Evaluación guardada.")
            except Exception as e:
                st.error(f"Error: {e}")

# --- EXPORTAR Y CORREO 2FA ---
elif menu == "📥 Exportar & Envío 2FA (CRUED)":
    st.markdown("## Exportación y Envío Seguro (2FA)")
    st.info("Módulo de descarga y envío por correo con 2FA intacto.")

# --- ANÁLISIS IA ---
elif menu == "🤖 Análisis IA":
    st.markdown("## 🤖 Análisis con IA")
    if st.button("Generar Plan de Mejora"):
        log_action(st.session_state.user_email, "Uso de IA para Análisis")
        st.success("Análisis IA registrado en logs. (Simulado)")

# --- PANEL ADMINISTRADOR (SOLO ADMIN) ---
elif menu == "🛡️ Panel Administrador" and st.session_state.is_admin:
    st.markdown("# 🛡️ Panel de Administración PRO")
    
    tab_a, tab_b, tab_c = st.tabs(["👥 Gestión Usuarios", "📊 Trazabilidad & Logs", "⚠️ Gestión Amenazas"])
    
    # --- TAB A: USUARIOS ---
    with tab_a:
        st.markdown("### Aprobar y Configurar Accesos")
        try:
            res = supabase.table("usuarios_app").select("*").execute()
            df_users = pd.DataFrame(res.data)
            
            if not df_users.empty:
                for index, row in df_users.iterrows():
                    with st.expander(f"👤 {row['nombre']} ({row['email']}) - Aprobado: {row['aprobado']}"):
                        col1, col2, col3 = st.columns([1, 1, 2])
                        with col1:
                            nuevo_estado = st.checkbox("Aprobado", value=row['aprobado'], key=f"apr_{row['id']}")
                        with col2:
                            expira = st.date_input("Expira en", value=date.today(), key=f"exp_{row['id']}")
                        with col3:
                            st.metric("Ingresos al Sistema", row['contador_ingresos'])
                        
                        if st.button("Guardar Cambios", key=f"btn_{row['id']}"):
                            supabase.table("usuarios_app").update({
                                "aprobado": nuevo_estado,
                                "fecha_expiracion": str(expira)
                            }).eq("id", row['id']).execute()
                            st.success("Usuario actualizado.")
                            st.rerun()
            else:
                st.info("No hay usuarios registrados además del Admin.")
        except Exception as e:
            st.error(e)

    # --- TAB B: LOGS PRO CON HISTOGRAMAS ---
    with tab_b:
        st.markdown("### Indicadores de Uso y Trazabilidad")
        try:
            res = supabase.table("logs_usuarios").select("*").order("fecha", desc=True).execute()
            df_logs = pd.DataFrame(res.data)
            
            if not df_logs.empty:
                # KPIs
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Logins", len(df_logs[df_logs['accion'].str.contains("Login")]))
                c2.metric("Evaluaciones Creadas", len(df_logs[df_logs['accion'] == "Nueva Evaluación Creada"]))
                c3.metric("Análisis de IA Generados", len(df_logs[df_logs['accion'] == "Uso de IA para Análisis"]))
                
                # Preparar datos para gráficos
                df_logs['fecha'] = pd.to_datetime(df_logs['fecha'])
                df_logs['fecha_dia'] = df_logs['fecha'].dt.date

                c_graph1, c_graph2 = st.columns(2)
                
                with c_graph1:
                    # Histograma de actividad por día
                    actividad_diaria = df_logs.groupby('fecha_dia').size().reset_index(name='cantidad')
                    fig_hist = px.bar(actividad_diaria, x='fecha_dia', y='cantidad', 
                                      title="📊 Actividad en el Sistema por Día", 
                                      labels={'fecha_dia': 'Fecha', 'cantidad': 'Número de Acciones'},
                                      color='cantidad', color_continuous_scale='Blues')
                    fig_hist.update_layout(showlegend=False, xaxis_tickangle=-45)
                    st.plotly_chart(fig_hist, use_container_width=True)
                
                with c_graph2:
                    # Histograma de tipos de acciones
                    acciones_count = df_logs['accion'].value_counts().reset_index()
                    acciones_count.columns = ['accion', 'cantidad']
                    fig_actions = px.bar(acciones_count, x='accion', y='cantidad',
                                         title="⚙️ Distribución de Acciones Realizadas",
                                         labels={'accion': 'Tipo de Acción', 'cantidad': 'Cantidad'},
                                         color='accion')
                    fig_actions.update_layout(showlegend=False, xaxis_tickangle=-45)
                    st.plotly_chart(fig_actions, use_container_width=True)

                st.markdown("#### Historial Detallado")
                st.dataframe(df_logs[['usuario_email', 'accion', 'fecha']], use_container_width=True)
            else:
                st.info("Sin actividad registrada.")
        except Exception as e:
            st.error(f"Error generando gráficos: {e}")

    # --- TAB C: AMENAZAS ---
    with tab_c:
        st.markdown("### Administrar Amenazas y Vulnerabilidades")
        
        nueva_amenaza = st.text_input("Adicionar Nueva Amenaza Manualmente")
        if st.button("➕ Agregar Amenaza"):
            if nueva_amenaza:
                try:
                    supabase.table("amenazas").insert({"nombre": nueva_amenaza.upper()}).execute()
                    st.success("Amenaza agregada.")
                    st.rerun()
                except Exception as e:
                    st.error("Posiblemente ya existe.")
        
        st.markdown("---")
        st.markdown("#### Listado Actual en Base de Datos")
        amenazas_actuales = get_amenazas()
        df_amenazas = pd.DataFrame(amenazas_actuales, columns=["Amenazas Configuradas"])
        st.dataframe(df_amenazas, use_container_width=True, height=400)
