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
from pathlib import Path  # Librería clave para que las imágenes siempre se vean
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from openai import OpenAI

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="ISH - Clínica San Rafael", page_icon="🏥", layout="wide")

# --- DEFINIR RUTAS ABSOLUTAS PARA LAS IMÁGENES ---
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
LOGO_CLINICA = ASSETS_DIR / "logo_clinica.png"
LOGO_VIGILADO = ASSETS_DIR / "vigilado.png"

# --- CONEXIÓN A SERVICIOS ---
@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

@st.cache_resource
def init_openai():
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

supabase = init_supabase()
openai_client = init_openai()

# --- CARGAR PREGUNTAS ---
@st.cache_data
def load_questions():
    try:
        with open("preguntas_ish.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        st.error("Archivo preguntas_ish.json no encontrado en el repositorio.")
        return {}

preguntas_data = load_questions()

# --- FUNCIONES DE SEGURIDAD Y BD ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def log_action(email, action):
    try:
        supabase.table("logs_usuarios").insert({"usuario_email": email, "accion": action}).execute()
    except:
        pass

def get_amenazas():
    try:
        res = supabase.table("amenazas").select("nombre").order("nombre").execute()
        return [a['nombre'] for a in res.data]
    except:
        return []

def calcular_indice(estructural, no_estructural, funcional):
    total = (estructural + no_estructural + funcional) / 3
    if total >= 0.66:
        clase, msg = "A", "Alta probabilidad de funcionar. Continuar con medidas de mejora."
    elif total >= 0.36:
        clase, msg = "B", "Probablemente funcione. Intervenciones a corto plazo."
    else:
        clase, msg = "C", "Baja probabilidad. Intervenciones urgentes requeridas."
    return total, clase, msg

def enviar_correo_2fa(destinatario, codigo):
    remitente = st.secrets["EMAIL_USER"]
    clave = st.secrets["EMAIL_PASSWORD"]
    host = st.secrets["EMAIL_HOST"]
    port = int(st.secrets["EMAIL_PORT"])
    nombre_remitente = st.secrets["EMAIL_FROM_NAME"]
    
    msg = MIMEMultipart()
    msg['From'] = f"{nombre_remitente} <{remitente}>"
    msg['To'] = destinatario
    msg['Subject'] = "Código de Verificación 2FA - Sistema ISH Clínica San Rafael"
    
    cuerpo = f"""
    <html><body style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #0056b3;">Verificación de Seguridad (2FA)</h2>
        <p>Hola, has solicitado enviar el reporte del Índice de Seguridad Hospitalaria.</p>
        <p>Tu código de verificación es:</p>
        <h1 style="font-size: 40px; color: #dc3545; text-align: center;">{codigo}</h1>
        <p>Este código expirará en {st.secrets["TWO_FACTOR_EXPIRY_SECONDS"]} segundos (5 minutos).</p>
        <hr><small>Clínica San Rafael Alta Complejidad SAS | Sabanalarga, Atlántico</small>
    </body></html>
    """
    msg.attach(MIMEText(cuerpo, 'html'))
    try:
        server = smtplib.SMTP(host, port)
        server.starttls()
        server.login(remitente, clave)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Error enviando correo 2FA: {e}")
        return False

def enviar_reporte_por_correo(destinatario, asunto, mensaje, archivo_adjunto_bytes, nombre_archivo):
    remitente = st.secrets["EMAIL_USER"]
    clave = st.secrets["EMAIL_PASSWORD"]
    host = st.secrets["EMAIL_HOST"]
    port = int(st.secrets["EMAIL_PORT"])
    nombre_remitente = st.secrets["EMAIL_FROM_NAME"]
    
    msg = MIMEMultipart()
    msg['From'] = f"{nombre_remitente} <{remitente}>"
    msg['To'] = destinatario
    msg['Subject'] = asunto
    msg.attach(MIMEText(mensaje, 'html'))
    
    part = MIMEBase('application', 'octet-stream')
    part.set_payload(archivo_adjunto_bytes)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="{nombre_archivo}"')
    msg.attach(part)
    
    try:
        server = smtplib.SMTP(host, port)
        server.starttls()
        server.login(remitente, clave)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Error enviando reporte: {e}")
        return False

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { border: 1px solid #e6e6e6; background: white; padding: 15px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    h1, h2, h3 { color: #0056b3; }
    </style>
""", unsafe_allow_html=True)

# --- INICIALIZAR SESSION STATE ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_email' not in st.session_state: st.session_state.user_email = ""
if 'user_name' not in st.session_state: st.session_state.user_name = ""
if 'is_admin' not in st.session_state: st.session_state.is_admin = False
if 'tfa_timestamp' not in st.session_state: st.session_state.tfa_timestamp = None
if 'codigo_2fa_generado' not in st.session_state: st.session_state.codigo_2fa_generado = None
if 'correo_verificado' not in st.session_state: st.session_state.correo_verificado = False
if 'correo_destino' not in st.session_state: st.session_state.correo_destino = ""
if 'ai_analysis_cache' not in st.session_state: st.session_state.ai_analysis_cache = None

# --- PANTALLA DE LOGIN / REGISTRO ---
if not st.session_state.logged_in:
    col_l, col_r = st.columns([1, 1])
    with col_l:
        if LOGO_CLINICA.exists(): st.image(str(LOGO_CLINICA), width=150)
        else: st.error(f"Falta: {LOGO_CLINICA}")
    with col_r:
        if LOGO_VIGILADO.exists(): st.image(str(LOGO_VIGILADO), width=120)
        else: st.error(f"Falta: {LOGO_VIGILADO}")

    st.markdown("<h1 style='text-align: center; color: #0056b3;'>Acceso al Sistema</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Índice de Seguridad Hospitalario - CSR AC 2026 By EESC</p><br>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["🔑 Iniciar Sesión", "📝 Registrar Nuevo Usuario"])
    
    with tab1:
        with st.form("login_form"):
            email_input = st.text_input("Correo Electrónico")
            pass_input = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Ingresar")
            
            if submit:
                if email_input == st.secrets["ADMIN_EMAIL"] and pass_input == st.secrets["ADMIN_PASSWORD"]:
                    st.session_state.logged_in = True
                    st.session_state.user_email = email_input
                    st.session_state.user_name = "Efrain Sarmiento Crespo"
                    st.session_state.is_admin = True
                    log_action(email_input, "Login Admin")
                    st.rerun()
                else:
                    try:
                        res = supabase.table("usuarios_app").select("*").eq("email", email_input).execute()
                        if len(res.data) > 0:
                            user = res.data[0]
                            if user['password'] == hash_password(pass_input):
                                if not user['aprobado']:
                                    st.warning("Tu cuenta está pendiente de aprobación.")
                                elif user['fecha_expiracion'] and date.fromisoformat(user['fecha_expiracion']) < date.today():
                                    st.error("Tu acceso ha expirado.")
                                else:
                                    st.session_state.logged_in = True
                                    st.session_state.user_email = email_input
                                    st.session_state.user_name = user['nombre']
                                    st.session_state.is_admin = False
                                    supabase.table("usuarios_app").update({"contador_ingresos": user['contador_ingresos'] + 1}).eq("email", email_input).execute()
                                    log_action(email_input, "Login Usuario")
                                    st.rerun()
                            else:
                                st.error("Contraseña incorrecta.")
                        else:
                            st.error("Usuario no encontrado.")
                    except Exception as e:
                        st.error(f"Error: {e}")

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
                    st.error(f"Error: {e}")
    st.stop()

# --- LOGOUT ---
if st.session_state.logged_in:
    if st.sidebar.button("🚪 Cerrar Sesión"):
        for key in ['logged_in', 'is_admin', 'user_email', 'user_name', 'ai_analysis_cache']:
            st.session_state[key] = False if key in ['logged_in', 'is_admin'] else ""
        st.rerun()

# --- HEADER CON LOGOS ---
col1, col2, col3 = st.columns([1, 3, 1])
with col1:
    if LOGO_CLINICA.exists(): st.image(str(LOGO_CLINICA), use_container_width=True)
    else: st.error("Falta logo_clinica.png")
with col2:
    st.markdown("<h1 style='text-align: center; margin-top: 20px;'>Índice de Seguridad Hospitalaria (ISH v2)</h1>", unsafe_allow_html=True)
    st.markdown(f"<h4 style='text-align: center; color: #6c757d;'>Bienvenido: <b>{st.session_state.user_name}</b></h4>", unsafe_allow_html=True)
with col3:
    if LOGO_VIGILADO.exists(): st.image(str(LOGO_VIGILADO), use_container_width=True)
    else: st.error("Falta vigilado.png")
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

        st.markdown("---")
        st.markdown("### 🤖 Comentarios y Plan de Acción Automático (IA)")
        
        if st.session_state.ai_analysis_cache:
            st.markdown(st.session_state.ai_analysis_cache, unsafe_allow_html=True)
            if st.button("🔄 Regenerar Análisis IA"):
                st.session_state.ai_analysis_cache = None
                st.rerun()
        else:
            if st.button("⚡ Generar Diagnóstico y Plan de Acción con IA"):
                with st.spinner("La IA está analizando los resultados..."):
                    prompt = f"""
                    Actúa como un experto en Gestión del Riesgo y Hospitales Seguros de la OMS/OPS.
                    Analiza los siguientes resultados del Índice de Seguridad Hospitalaria (ISH) para la 
                    Clínica San Rafael Alta Complejidad SAS (Nivel III y IV, 365 trabajadores, Sabanalarga, Atlántico).
                    Amenazas identificadas: {latest['nivel_riesgo']}.
                    Índice Estructural: {latest['indice_estructural']}.
                    Índice No Estructural: {latest['indice_no_estructural']}.
                    Índice Funcional: {latest['indice_funcional']}.
                    Índice Total: {latest['indice_total']} (Clasificación: {latest['clasificacion']}).
                    
                    Genera un informe estructurado en HTML con:
                    1. Diagnóstico general.
                    2. Hallazgos críticos por módulo.
                    3. Tres acciones de mejora prioritarias a corto plazo (para auditorías del CRUED).
                    4. Recomendación para mantener o mejorar la autonomía de 72 horas.
                    """
                    try:
                        response = openai_client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[{"role": "user", "content": prompt}]
                        )
                        st.session_state.ai_analysis_cache = response.choices[0].message.content
                        log_action(st.session_state.user_email, "Uso de IA para Análisis")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error llamando a OpenAI: {e}")

# --- NUEVA EVALUACIÓN ---
elif menu == "📋 Nueva Evaluación":
    st.markdown("## Formulario ISH-APP 2022")
    st.info("Diligencie cada pregunta. Al finalizar, presione 'Calcular y Guardar'.")
    
    amenazas_bd = get_amenazas()
    
    with st.form("eval_form"):
        col1, col2 = st.columns(2)
        with col1:
            evaluador = st.text_input("Evaluador", st.session_state.user_name)
            fecha = st.date_input("Fecha", datetime.now())
        with col2:
            amenazas = st.multiselect("Amenazas Identificadas", amenazas_bd)
        
        respuestas = {}
        for modulo, preguntas in preguntas_data.items():
            st.markdown(f"### Módulo: {modulo}")
            for p in preguntas:
                respuestas[f"{modulo}_{p['id']}"] = st.slider(
                    f"{p['id']}. {p['pregunta']}", 0.0, 1.0, 0.5, 0.1, key=f"{modulo}_{p['id']}"
                )
        
        submitted = st.form_submit_button("Calcular Índice y Guardar")
        if submitted:
            est_vals = [v for k, v in respuestas.items() if k.startswith("Estructural")]
            no_est_vals = [v for k, v in respuestas.items() if k.startswith("No Estructural")]
            func_vals = [v for k, v in respuestas.items() if k.startswith("Funcional")]
            
            est = sum(est_vals)/len(est_vals) if est_vals else 0
            no_est = sum(no_est_vals)/len(no_est_vals) if no_est_vals else 0
            func = sum(func_vals)/len(func_vals) if func_vals else 0
            
            total, clase, msg = calcular_indice(est, no_est, func)
            
            data = {
                "fecha_evaluacion": str(fecha), "evaluador": evaluador, "nivel_riesgo": ", ".join(amenazas),
                "indice_estructural": est, "indice_no_estructural": no_est, "indice_funcional": func,
                "indice_total": total, "clasificacion": clase, "autonomia_horas": 72 if clase == 'A' else (24 if clase == 'B' else 0)
            }
            try:
                supabase.table("evaluaciones_ish").insert(data).execute()
                log_action(st.session_state.user_email, "Nueva Evaluación Creada")
                st.session_state.ai_analysis_cache = None
                st.balloons()
                st.success(f"**Evaluación Guardada. Índice: {total:.2f} (Clase {clase})**. Ve al Dashboard para ver el análisis IA.")
            except Exception as e:
                st.error(f"Error: {e}")

# --- EXPORTAR Y CORREO 2FA ---
elif menu == "📥 Exportar & Envío 2FA (CRUED)":
    st.markdown("## Exportación y Envío Seguro (2FA)")
    
    try:
        res = supabase.table("evaluaciones_ish").select("*").execute()
        df_eval = pd.DataFrame(res.data)
    except:
        df_eval = pd.DataFrame()

    if not df_eval.empty:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_eval.to_excel(writer, index=False, sheet_name='Reporte_CRUED')
        excel_bytes = output.getvalue()
        
        st.download_button("📥 Descargar Excel Localmente", excel_bytes, 
                           file_name=f'Reporte_ISH_SanRafael_{datetime.now().strftime("%Y%m%d")}.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        st.markdown("---")
        st.markdown("### 📧 Enviar Reporte por Correo (Requiere 2FA)")
        
        if not st.session_state.correo_verificado:
            correo_input = st.text_input("Correo del destinatario (Auditor CRUED, etc.)")
            if st.button("Enviar Código 2FA"):
                if correo_input:
                    codigo = random.randint(100000, 999999)
                    st.session_state.codigo_2fa_generado = codigo
                    st.session_state.correo_destino = correo_input
                    st.session_state.tfa_timestamp = time.time()
                    if enviar_correo_2fa(correo_input, codigo):
                        st.success("Código 2FA enviado. Revisa tu correo.")
                else:
                    st.warning("Ingresa un correo.")
        
        elif st.session_state.codigo_2fa_generado and not st.session_state.correo_verificado:
            tiempo_transcurrido = time.time() - st.session_state.tfa_timestamp
            tiempo_limite = int(st.secrets["TWO_FACTOR_EXPIRY_SECONDS"])
            
            if tiempo_transcurrido > tiempo_limite:
                st.error("El código 2FA ha expirado. Solicita uno nuevo.")
                st.session_state.codigo_2fa_generado = None
                st.rerun()
            else:
                st.info(f"Se envió código a: {st.session_state.correo_destino} (Expira en {int(tiempo_limite - tiempo_transcurrido)} seg)")
                codigo_ingresado = st.text_input("Ingresa el código de 6 dígitos:")
                if st.button("Verificar Código"):
                    if int(codigo_ingresado) == st.session_state.codigo_2fa_generado:
                        st.session_state.correo_verificado = True
                        st.success("¡Correo verificado! Ya puedes enviar el reporte.")
                        st.rerun()
                    else:
                        st.error("Código incorrecto.")
        
        if st.session_state.correo_verificado:
            st.markdown(f"#### Correo Verificado: {st.session_state.correo_destino}")
            asunto = st.text_input("Asunto", "Reporte Índice de Seguridad Hospitalaria - Clínica San Rafael")
            mensaje = st.text_area("Mensaje", "Adjunto encontrará el reporte de evaluación ISH.")
            
            if st.button("📤 Enviar Reporte por Correo"):
                cuerpo_html = f"<html><body><p>{mensaje}</p><br><p>Atentamente,</p><p><strong>Coordinación SST</strong><br>Clínica San Rafael</p></body></html>"
                nombre_arch = f'Reporte_ISH_SanRafael_{datetime.now().strftime("%Y%m%d")}.xlsx'
                if enviar_reporte_por_correo(st.session_state.correo_destino, asunto, cuerpo_html, excel_bytes, nombre_arch):
                    st.success("¡Correo enviado exitosamente con el Excel adjunto!")
                    st.session_state.correo_verificado = False
                    st.session_state.codigo_2fa_generado = None
                    st.rerun()
                else:
                    st.error("Falló el envío.")
    else:
        st.warning("Sin datos para exportar.")

# --- ANÁLISIS IA ---
elif menu == "🤖 Análisis IA":
    st.markdown("## 🤖 Análisis con Inteligencia Artificial")
    st.info("Genera el plan de acción basado en la última evaluación registrada.")
    if st.button("⚡ Generar Diagnóstico IA"):
        with st.spinner("Analizando..."):
            try:
                res = supabase.table("evaluaciones_ish").select("*").order("fecha_evaluacion", desc=True).limit(1).execute()
                if res.data:
                    latest = res.data[0]
                    prompt = f"""
                    Actúa como experto OMS/OPS. ISH Clínica San Rafael Sabanalarga (III-IV).
                    Índice Total: {latest['indice_total']} (Clase {latest['clasificacion']}).
                    Estructural: {latest['indice_estructural']}, No Estructural: {latest['indice_no_estructural']}, Funcional: {latest['indice_funcional']}.
                    Genera en HTML: Diagnóstico, Hallazgos críticos, 3 acciones de mejora corto plazo, Recomendación autonomía 72h.
                    """
                    response = openai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                    st.session_state.ai_analysis_cache = response.choices[0].message.content
                    log_action(st.session_state.user_email, "Uso de IA para Análisis")
                    st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

# --- PANEL ADMINISTRADOR ---
elif menu == "🛡️ Panel Administrador" and st.session_state.is_admin:
    st.markdown("# 🛡️ Panel de Administración PRO")
    
    tab_a, tab_b, tab_c = st.tabs(["👥 Gestión Usuarios", "📊 Trazabilidad & Logs", "⚠️ Gestión Amenazas"])
    
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
                            supabase.table("usuarios_app").update({"aprobado": nuevo_estado, "fecha_expiracion": str(expira)}).eq("id", row['id']).execute()
                            st.success("Usuario actualizado.")
                            st.rerun()
            else:
                st.info("No hay usuarios registrados.")
        except Exception as e:
            st.error(e)

    with tab_b:
        st.markdown("### Indicadores de Uso y Trazabilidad")
        try:
            res = supabase.table("logs_usuarios").select("*").order("fecha", desc=True).execute()
            df_logs = pd.DataFrame(res.data)
            if not df_logs.empty:
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Logins", len(df_logs[df_logs['accion'].str.contains("Login")]))
                c2.metric("Evaluaciones Creadas", len(df_logs[df_logs['accion'] == "Nueva Evaluación Creada"]))
                c3.metric("Análisis IA Generados", len(df_logs[df_logs['accion'] == "Uso de IA para Análisis"]))
                
                df_logs['fecha'] = pd.to_datetime(df_logs['fecha'])
                df_logs['fecha_dia'] = df_logs['fecha'].dt.date

                c_graph1, c_graph2 = st.columns(2)
                with c_graph1:
                    actividad_diaria = df_logs.groupby('fecha_dia').size().reset_index(name='cantidad')
                    fig_hist = px.bar(actividad_diaria, x='fecha_dia', y='cantidad', title="📊 Actividad por Día", color='cantidad', color_continuous_scale='Blues')
                    st.plotly_chart(fig_hist, use_container_width=True)
                
                with c_graph2:
                    acciones_count = df_logs['accion'].value_counts().reset_index()
                    acciones_count.columns = ['accion', 'cantidad']
                    fig_actions = px.bar(acciones_count, x='accion', y='cantidad', title="⚙️ Acciones Realizadas", color='accion')
                    st.plotly_chart(fig_actions, use_container_width=True)

                st.markdown("#### Historial Detallado")
                st.dataframe(df_logs[['usuario_email', 'accion', 'fecha']], use_container_width=True)
            else:
                st.info("Sin actividad.")
        except Exception as e:
            st.error(e)

    with tab_c:
        st.markdown("### Administrar Amenazas y Vulnerabilidades")
        nueva_amenaza = st.text_input("Adicionar Nueva Amenaza Manualmente")
        if st.button("➕ Agregar Amenaza"):
            if nueva_amenaza:
                try:
                    supabase.table("amenazas").insert({"nombre": nueva_amenaza.upper()}).execute()
                    st.success("Amenaza agregada.")
                    st.rerun()
                except:
                    st.error("Posiblemente ya existe.")
        st.markdown("---")
        st.markdown("#### Listado Actual en Base de Datos")
        amenazas_actuales = get_amenazas()
        df_amenazas = pd.DataFrame(amenazas_actuales, columns=["Amenazas Configuradas"])
        st.dataframe(df_amenazas, use_container_width=True, height=400)
