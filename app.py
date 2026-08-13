import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from supabase import create_client, Client
from datetime import datetime
import io
import json
import random
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from openai import OpenAI

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="ISH - Clínica San Rafael", page_icon="🏥", layout="wide")

# --- CONEXIÓN A SERVICIOS (LEYENDO TUS SECRETS EXACTOS) ---
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

@st.cache_resource
def init_openai():
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

supabase = init_supabase()
openai_client = init_openai()

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

# --- FUNCIONES AUXILIARES ---
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
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #0056b3;">Verificación de Seguridad (2FA)</h2>
        <p>Hola, has solicitado enviar el reporte del Índice de Seguridad Hospitalaria.</p>
        <p>Tu código de verificación es:</p>
        <h1 style="font-size: 40px; color: #dc3545; text-align: center;">{codigo}</h1>
        <p>Este código expirará en {st.secrets["TWO_FACTOR_EXPIRY_SECONDS"]} segundos (5 minutos).</p>
        <p>Si no solicitaste esto, ignora este correo.</p>
        <hr>
        <small>Clínica San Rafael Alta Complejidad SAS | Sabanalarga, Atlántico</small>
    </body>
    </html>
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

# --- INICIALIZAR SESSION STATE ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'codigo_2fa_generado' not in st.session_state:
    st.session_state.codigo_2fa_generado = None
if 'tfa_timestamp' not in st.session_state:  # <--- CORREGIDO AQUÍ
    st.session_state.tfa_timestamp = None
if 'correo_verificado' not in st.session_state:
    st.session_state.correo_verificado = False
if 'correo_destino' not in st.session_state:
    st.session_state.correo_destino = ""

# --- PANTALLA DE LOGIN (USANDO ADMIN_EMAIL Y ADMIN_PASSWORD) ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #0056b3;'>Acceso al Sistema</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Índice de Seguridad Hospitalario - CSR AC 2026 By EESC</p><br>", unsafe_allow_html=True)
    
    with st.form("login_form"):
        email_input = st.text_input("Correo Administrativo")
        pass_input = st.text_input("Contraseña", type="password")
        submit = st.form_submit_button("Ingresar")
        
        if submit:
            if email_input == st.secrets["ADMIN_EMAIL"] and pass_input == st.secrets["ADMIN_PASSWORD"]:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Credenciales incorrectas. Acceso denegado.")
    st.stop()

# --- HEADER CON LOGOS ---
col1, col2, col3 = st.columns([1, 3, 1])
with col1:
    try: st.image("assets/logo_clinica.png", use_container_width=True)
    except: st.warning("Falta logo_clinica.png en /assets")
with col2:
    st.markdown("<h1 style='text-align: center; margin-top: 20px;'>Índice de Seguridad Hospitalaria (ISH v2)</h1>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center; color: #6c757d;'>Clínica San Rafael Alta Complejidad SAS | Sabanalarga, Atlántico</h4>", unsafe_allow_html=True)
with col3:
    try: st.image("assets/vigilado.png", use_container_width=True)
    except: st.warning("Falta vigilado.png en /assets")

st.markdown("<p style='text-align: center; color: #6c757d;'>Niveles III y IV | 365 Trabajadores | Cobertura: Sabanalarga, Baranoa, Luruaco y Corregimientos</p><hr>", unsafe_allow_html=True)

# --- MENÚ ---
menu = st.sidebar.selectbox("Menú", ["📊 Dashboard", "📋 Nueva Evaluación", "📥 Exportar & Envío 2FA (CRUED)", "🤖 Análisis IA"])

# --- DASHBOARD ---
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
                respuestas[f"{modulo}_{p['id']}"] = st.slider(f"{p['id']}. {p['pregunta']}", 0.0, 1.0, 0.5, 0.1, key=f"{modulo}_{p['id']}")
        
        submitted = st.form_submit_button("Calcular Índice y Guardar")
        if submitted:
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

# --- EXPORTAR Y CORREO 2FA ---
elif menu == "📥 Exportar & Envío 2FA (CRUED)":
    st.markdown("## Exportación y Envío Seguro (2FA)")
    
    df_eval = get_evaluaciones()
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
        
        # Paso 1: Solicitar Correo
        if not st.session_state.correo_verificado:
            correo_input = st.text_input("Ingresa el correo electrónico del destinatario (Auditor CRUED, Secretaría, etc.)")
            if st.button("Enviar Código 2FA"):
                if correo_input:
                    codigo = random.randint(100000, 999999)
                    st.session_state.codigo_2fa_generado = codigo
                    st.session_state.correo_destino = correo_input
                    st.session_state.tfa_timestamp = time.time() # <--- CORREGIDO AQUÍ
                    if enviar_correo_2fa(correo_input, codigo):
                        st.success("Código 2FA enviado al correo. Revisa tu bandeja de entrada (o spam).")
                else:
                    st.warning("Por favor ingresa un correo.")
        
        # Paso 2: Verificar 2FA
        elif st.session_state.codigo_2fa_generado and not st.session_state.correo_verificado:
            tiempo_transcurrido = time.time() - st.session_state.tfa_timestamp  # <--- CORREGIDO AQUÍ
            tiempo_limite = int(st.secrets["TWO_FACTOR_EXPIRY_SECONDS"])
            
            if tiempo_transcurrido > tiempo_limite:
                st.error("El código 2FA ha expirado. Por favor, solicita uno nuevo.")
                st.session_state.codigo_2fa_generado = None
                st.rerun()
            else:
                st.info(f"Se envió código a: {st.session_state.correo_destino} (Expira en {int(tiempo_limite - tiempo_transcurrido)} seg)")
                codigo_ingresado = st.text_input("Ingresa el código de 6 dígitos:")
                if st.button("Verificar Código"):
                    if int(codigo_ingresado) == st.session_state.codigo_2fa_generado:
                        st.session_state.correo_verificado = True
                        st.success("¡Correo verificado con éxito! Ya puedes enviar el reporte.")
                        st.rerun()
                    else:
                        st.error("Código incorrecto.")
        
        # Paso 3: Enviar Correo con Archivo
        if st.session_state.correo_verificado:
            st.markdown(f"#### Correo Destino Verificado: {st.session_state.correo_destino}")
            asunto = st.text_input("Asunto del Correo", "Reporte Índice de Seguridad Hospitalaria - Clínica San Rafael")
            mensaje = st.text_area("Mensaje del Correo", "Adjunto encontrará el reporte de evaluación ISH para la auditoría correspondiente.")
            
            if st.button("📤 Enviar Reporte por Correo"):
                cuerpo_html = f"""
                <html><body style="font-family: Arial; color: #333;">
                <p>{mensaje}</p><br>
                <p>Atentamente,</p>
                <p><strong>Coordinación SST</strong><br>Clínica San Rafael Alta Complejidad SAS</p>
                </body></html>
                """
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

# --- ANÁLISIS CON OPENAI ---
elif menu == "🤖 Análisis IA":
    st.markdown("## 🤖 Análisis Automático con Inteligencia Artificial")
    st.info("La IA analizará los últimos resultados del ISH y generará recomendaciones de mejora basadas en los lineamientos de la OMS.")
    
    df_eval = get_evaluaciones()
    if not df_eval.empty:
        latest = df_eval.iloc[0]
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("Índice Global", f"{latest['indice_total']:.2f} ({latest['clasificacion']})")
            st.metric("Estructural", f"{latest['indice_estructural']:.2f}")
            st.metric("No Estructural", f"{latest['indice_no_estructural']:.2f}")
            st.metric("Funcional", f"{latest['indice_funcional']:.2f}")
            
        with col2:
            if st.button("Generar Plan de Mejora y Análisis con GPT-4"):
                with st.spinner('La IA está analizando la seguridad hospitalaria...'):
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
                        analisis_ia = response.choices[0].message.content
                        st.markdown("### 📝 Informe Generado por IA")
                        st.markdown(analisis_ia, unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"Error con OpenAI API: {e}")
    else:
        st.warning("No hay evaluaciones para analizar.")
