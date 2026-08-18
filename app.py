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
st.set_page_config(page_title="ISH - Clínica San Rafael", page_icon="🏥", layout="wide")

# --- BÚSQUEDA INTELIGENTE DE IMÁGENES Y CARGA EN BYTES ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_CLINICA = None
LOGO_VIGILADO = None

def cargar_imagen_segura(ruta_relativa):
    ruta_absoluta = os.path.join(BASE_DIR, ruta_relativa)
    if os.path.exists(ruta_absoluta):
        try:
            with open(ruta_absoluta, "rb") as img_file:
                return img_file.read()
        except:
            return None
    return None

# Buscamos en las carpetas posibles: assets, asset, o raíz
for folder in ["assets", "asset", "."]:
    logo_temp = cargar_imagen_segura(os.path.join(folder, "logo_clinica.png"))
    vigilado_temp = cargar_imagen_segura(os.path.join(folder, "vigilado.png"))
    if logo_temp and not LOGO_CLINICA:
        LOGO_CLINICA = logo_temp
    if vigilado_temp and not LOGO_VIGILADO:
        LOGO_VIGILADO = vigilado_temp

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
        st.error("Archivo preguntas_ish.json no encontrado.")
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

def get_evaluaciones_df():
    try:
        res = supabase.table("evaluaciones_ish").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            df['fecha_evaluacion'] = pd.to_datetime(df['fecha_evaluacion'])
            df = df.sort_values(by='fecha_evaluacion', ascending=False).reset_index(drop=True)
        return df
    except:
        return pd.DataFrame()

# --- FUNCIÓN IA PRO (JSON Y RENDER NATIVO) ---
def generar_informe_ia(latest_data):
    prompt = f"""
    Actúa como un experto en Gestión del Riesgo y Hospitales Seguros de la OMS/OPS.
    Analiza los siguientes resultados del Índice de Seguridad Hospitalaria (ISH) para la 
    Clínica San Rafael Alta Complejidad SAS (Nivel III y IV, 365 trabajadores, Sabanalarga, Atlántico).
    Amenazas identificadas: {latest_data['nivel_riesgo']}.
    Índice Estructural: {latest_data['indice_estructural']}.
    Índice No Estructural: {latest_data['indice_no_estructural']}.
    Índice Funcional: {latest_data['indice_funcional']}.
    Índice Total: {latest_data['indice_total']} (Clasificación: {latest_data['clasificacion']}).
    
    Devuelve la respuesta ESTRICTAMENTE en formato JSON con esta estructura exacta:
    {{
        "diagnostico_general": "Un párrafo claro y conciso sobre el estado del hospital.",
        "hallazgos_criticos": ["Hallazgo 1", "Hallazgo 2", "Hallazgo 3"],
        "acciones_mejora": ["Acción 1", "Acción 2", "Acción 3"],
        "recomendacion_autonomia": "Recomendación específica para mantener o mejorar la autonomía de 72 horas."
    }}
    No incluyas texto fuera del JSON.
    """
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def renderizar_informe_ia(data):
    """Dibuja el informe JSON usando componentes nativos de Streamlit para un look PRO."""
    st.markdown("## 🤖 Informe de Inteligencia Artificial y Plan de Acción")
    st.caption("Análisis generado automáticamente basado en lineamientos OMS/OPS para auditorías CRUED.")
    
    st.subheader("📋 1. Diagnóstico General")
    st.info(data.get("diagnostico_general", "No disponible"), icon="🏥")
    
    col_h, col_a = st.columns(2)
    
    with col_h:
        st.subheader("⚠️ 2. Hallazgos Críticos")
        hallazgos = data.get("hallazgos_criticos", [])
        for i, hallazgo in enumerate(hallazgos, 1):
            with st.container(border=True):
                st.markdown(f"**🔍 Hallazgo {i}:**")
                st.write(hallazgo)
                
    with col_a:
        st.subheader("🚀 3. Acciones de Mejora (Corto Plazo)")
        acciones = data.get("acciones_mejora", [])
        for i, accion in enumerate(acciones, 1):
            with st.container(border=True):
                st.markdown(f"**✅ Acción {i}:**")
                st.write(accion)
                
    st.subheader("⏱️ 4. Recomendación de Autonomía (72 Horas)")
    st.warning(data.get("recomendacion_autonomia", "No disponible"), icon="⚡")

# --- FUNCIONES CORREO ---
def enviar_correo_2fa(destinatario, codigo):
    remitente = st.secrets["EMAIL_USER"]
    clave = st.secrets["EMAIL_PASSWORD"]
    host = st.secrets["EMAIL_HOST"]
    port = int(st.secrets["EMAIL_PORT"])
    nombre_remitente = st.secrets["EMAIL_FROM_NAME"]
    
    msg = MIMEMultipart()
    msg['From'] = f"{nombre_remitente} <{remitente}>"
    msg['To'] = destinatario
    msg['Subject'] = "Código de Verificación 2FA - Sistema ISH"
    cuerpo = f"<html><body><h2>Verificación 2FA</h2><p>Tu código es:</p><h1 style='color:#dc3545;'>{codigo}</h1><p>Expira en 5 minutos.</p></body></html>"
    msg.attach(MIMEText(cuerpo, 'html'))
    try:
        server = smtplib.SMTP(host, port)
        server.starttls()
        server.login(remitente, clave)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Error correo 2FA: {e}")
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
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_email' not in st.session_state: st.session_state.user_email = ""
if 'user_name' not in st.session_state: st.session_state.user_name = ""
if 'is_admin' not in st.session_state: st.session_state.is_admin = False
if 'tfa_timestamp' not in st.session_state: st.session_state.tfa_timestamp = None
if 'codigo_2fa_generado' not in st.session_state: st.session_state.codigo_2fa_generado = None
if 'correo_verificado' not in st.session_state: st.session_state.correo_verificado = False
if 'correo_destino' not in st.session_state: st.session_state.correo_destino = ""
if 'ai_analysis_cache' not in st.session_state: st.session_state.ai_analysis_cache = None

# --- LOGIN ---
if not st.session_state.logged_in:
    col_l, col_r = st.columns([1, 1])
    with col_l:
        if LOGO_CLINICA: st.image(LOGO_CLINICA, width=150)
        else: st.error("Sube 'logo_clinica.png' a tu repo")
    with col_r:
        if LOGO_VIGILADO: st.image(LOGO_VIGILADO, width=120)
        else: st.error("Sube 'vigilado.png' a tu repo")

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
                                if not user['aprobado']: st.warning("Cuenta pendiente de aprobación.")
                                elif user['fecha_expiracion'] and date.fromisoformat(user['fecha_expiracion']) < date.today(): st.error("Acceso expirado.")
                                else:
                                    st.session_state.logged_in = True
                                    st.session_state.user_email = email_input
                                    st.session_state.user_name = user['nombre']
                                    st.session_state.is_admin = False
                                    supabase.table("usuarios_app").update({"contador_ingresos": user['contador_ingresos'] + 1}).eq("email", email_input).execute()
                                    log_action(email_input, "Login Usuario")
                                    st.rerun()
                            else: st.error("Contraseña incorrecta.")
                        else: st.error("Usuario no encontrado.")
                    except Exception as e: st.error(f"Error: {e}")
    with tab2:
        with st.form("register_form"):
            reg_name = st.text_input("Nombre Completo")
            reg_email = st.text_input("Correo Electrónico Corporativo")
            reg_pass = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Solicitar Acceso"):
                try:
                    supabase.table("usuarios_app").insert({"email": reg_email, "password": hash_password(reg_pass), "nombre": reg_name, "aprobado": False}).execute()
                    st.success("Solicitud enviada.")
                except: st.error("Error al registrar.")
    st.stop()

# --- LOGOUT ---
if st.session_state.logged_in:
    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.session_state.logged_in = False
        st.session_state.is_admin = False
        st.session_state.user_email = ""
        st.session_state.user_name = ""
        st.session_state.ai_analysis_cache = None
        st.rerun()

# --- HEADER ---
col1, col2, col3 = st.columns([1, 3, 1])
with col1:
    if LOGO_CLINICA: st.image(LOGO_CLINICA, width=120)
    else: st.warning("Logo no encontrado")
with col2:
    st.markdown("<h1 style='text-align: center; margin-top: 20px;'>Índice de Seguridad Hospitalaria (ISH v2)</h1>", unsafe_allow_html=True)
    st.markdown(f"<h4 style='text-align: center; color: #6c757d;'>Bienvenido: <b>{st.session_state.user_name}</b></h4>", unsafe_allow_html=True)
with col3:
    if LOGO_VIGILADO: st.image(LOGO_VIGILADO, width=100)
    else: st.warning("Vigilado no encontrado")
st.markdown("<hr>", unsafe_allow_html=True)

# --- MENÚ ---
opciones_menu = ["📊 Dashboard", "📋 Nueva Evaluación", "📥 Exportar & Envío 2FA", "🤖 Análisis IA"]
if st.session_state.is_admin: opciones_menu.append("🛡️ Panel Administrador")
menu = st.sidebar.selectbox("Menú", opciones_menu)

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    df_eval = get_evaluaciones_df()

    if df_eval.empty:
        st.warning("No hay evaluaciones registradas aún.")
    else:
        latest = df_eval.iloc[0] # Siempre tomamos la primera fila (que ya ordenamos como la más reciente)
        
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

        # --- TABLA HISTÓRICA PRO ---
        st.markdown("---")
        st.markdown("### 📜 Historial de Evaluaciones Anteriores")
        df_hist = df_eval[['fecha_evaluacion', 'evaluador', 'nivel_riesgo', 'indice_total', 'clasificacion']].copy()
        df_hist['indice_total'] = df_hist['indice_total'].apply(lambda x: f"{x:.2f}")
        df_hist.columns = ['Fecha y Hora', 'Evaluador', 'Amenazas', 'Índice Total', 'Clasificación']
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

        st.markdown("---")
        if st.session_state.ai_analysis_cache:
            renderizar_informe_ia(st.session_state.ai_analysis_cache)
            if st.button("🔄 Regenerar Análisis IA"):
                st.session_state.ai_analysis_cache = None
                st.rerun()
        else:
            if st.button("⚡ Generar Diagnóstico y Plan de Acción con IA"):
                with st.spinner("La IA está analizando los resultados..."):
                    try:
                        st.session_state.ai_analysis_cache = generar_informe_ia(latest)
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
            fecha = st.date_input("Fecha de Evaluación", datetime.now())
        with col2:
            amenazas = st.multiselect("Amenazas Identificadas", amenazas_bd)
        
        respuestas = {}
        for modulo, preguntas in preguntas_data.items():
            st.markdown(f"### Módulo: {modulo}")
            for p in preguntas:
                respuestas[f"{modulo}_{p['id']}"] = st.slider(f"{p['id']}. {p['pregunta']}", 0.0, 1.0, 0.5, 0.1, key=f"{modulo}_{p['id']}")
        
        if st.form_submit_button("Calcular Índice y Guardar"):
            est_vals = [v for k, v in respuestas.items() if k.startswith("Estructural")]
            no_est_vals = [v for k, v in respuestas.items() if k.startswith("No Estructural")]
            func_vals = [v for k, v in respuestas.items() if k.startswith("Funcional")]
            est = sum(est_vals)/len(est_vals) if est_vals else 0
            no_est = sum(no_est_vals)/len(no_est_vals) if no_est_vals else 0
            func = sum(func_vals)/len(func_vals) if func_vals else 0
            total, clase, msg = calcular_indice(est, no_est, func)
            
            # Guardamos con fecha y hora exacta (datetime.now()) para que el orden cronológico funcione perfecto
            data = {
                "fecha_evaluacion": str(datetime.now()), 
                "evaluador": evaluador, 
                "nivel_riesgo": ", ".join(amenazas),
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

# --- EXPORTAR ---
elif menu == "📥 Exportar & Envío 2FA":
    st.markdown("## Exportación y Envío Seguro (2FA)")
    df_eval = get_evaluaciones_df()

    if not df_eval.empty:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_eval.to_excel(writer, index=False, sheet_name='Reporte_CRUED')
        excel_bytes = output.getvalue()
        st.download_button("📥 Descargar Excel Localmente", excel_bytes, file_name=f'Reporte_ISH_{datetime.now().strftime("%Y%m%d")}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        st.markdown("---")
        st.markdown("### 📧 Enviar Reporte por Correo (Requiere 2FA)")
        if not st.session_state.correo_verificado:
            correo_input = st.text_input("Correo del destinatario")
            if st.button("Enviar Código 2FA"):
                if correo_input:
                    codigo = random.randint(100000, 999999)
                    st.session_state.codigo_2fa_generado = codigo
                    st.session_state.correo_destino = correo_input
                    st.session_state.tfa_timestamp = time.time()
                    if enviar_correo_2fa(correo_input, codigo): st.success("Código enviado.")
                else: st.warning("Ingresa un correo.")
        elif st.session_state.codigo_2fa_generado and not st.session_state.correo_verificado:
            tiempo_transcurrido = time.time() - st.session_state.tfa_timestamp
            tiempo_limite = int(st.secrets["TWO_FACTOR_EXPIRY_SECONDS"])
            if tiempo_transcurrido > tiempo_limite:
                st.error("Código expirado.")
                st.session_state.codigo_2fa_generado = None
                st.rerun()
            else:
                st.info(f"Expira en {int(tiempo_limite - tiempo_transcurrido)} seg")
                codigo_ingresado = st.text_input("Código de 6 dígitos:")
                if st.button("Verificar"):
                    if int(codigo_ingresado) == st.session_state.codigo_2fa_generado:
                        st.session_state.correo_verificado = True
                        st.rerun()
                    else: st.error("Código incorrecto.")
        if st.session_state.correo_verificado:
            asunto = st.text_input("Asunto", "Reporte ISH - Clínica San Rafael")
            mensaje = st.text_area("Mensaje", "Adjunto reporte.")
            if st.button("📤 Enviar"):
                cuerpo = f"<html><body><p>{mensaje}</p><br><p><strong>Coordinación SST</strong></p></body></html>"
                if enviar_reporte_por_correo(st.session_state.correo_destino, asunto, cuerpo, excel_bytes, f'Reporte_ISH_{datetime.now().strftime("%Y%m%d")}.xlsx'):
                    st.success("Correo enviado!")
                    st.session_state.correo_verificado = False
                    st.session_state.codigo_2fa_generado = None
                    st.rerun()
    else: st.warning("Sin datos.")

# --- IA ---
elif menu == "🤖 Análisis IA":
    st.markdown("## 🤖 Análisis con Inteligencia Artificial")
    if st.button("⚡ Generar Diagnóstico"):
        with st.spinner("Analizando..."):
            df_eval = get_evaluaciones_df()
            if not df_eval.empty:
                try:
                    st.session_state.ai_analysis_cache = generar_informe_ia(df_eval.iloc[0])
                    log_action(st.session_state.user_email, "Uso de IA para Análisis")
                    st.rerun()
                except Exception as e: st.error(f"Error: {e}")

# --- ADMIN ---
elif menu == "🛡️ Panel Administrador" and st.session_state.is_admin:
    st.markdown("# 🛡️ Panel de Administración PRO")
    tab_a, tab_b, tab_c, tab_d = st.tabs(["👥 Usuarios", "📊 Logs", "⚠️ Amenazas", "📝 Editar Evaluaciones"])
    
    # Editar Usuarios
    with tab_a:
        try:
            res = supabase.table("usuarios_app").select("*").execute()
            df_users = pd.DataFrame(res.data)
            if not df_users.empty:
                for index, row in df_users.iterrows():
                    with st.expander(f"👤 {row['nombre']} ({row['email']}) - Aprobado: {row['aprobado']}"):
                        c1, c2, c3 = st.columns([1, 1, 2])
                        with c1: nuevo_estado = st.checkbox("Aprobado", value=row['aprobado'], key=f"apr_{row['id']}")
                        with c2: expira = st.date_input("Expira", value=date.today(), key=f"exp_{row['id']}")
                        with c3: st.metric("Ingresos", row['contador_ingresos'])
                        if st.button("Guardar", key=f"btn_{row['id']}"):
                            supabase.table("usuarios_app").update({"aprobado": nuevo_estado, "fecha_expiracion": str(expira)}).eq("id", row['id']).execute()
                            st.success("Actualizado.")
                            st.rerun()
            else: st.info("Sin usuarios.")
        except Exception as e: st.error(e)
        
    # Logs
    with tab_b:
        try:
            res = supabase.table("logs_usuarios").select("*").order("fecha", desc=True).execute()
            df_logs = pd.DataFrame(res.data)
            if not df_logs.empty:
                c1, c2, c3 = st.columns(3)
                c1.metric("Logins", len(df_logs[df_logs['accion'].str.contains("Login")]))
                c2.metric("Evaluaciones", len(df_logs[df_logs['accion'] == "Nueva Evaluación Creada"]))
                c3.metric("IA Generada", len(df_logs[df_logs['accion'] == "Uso de IA para Análisis"]))
                df_logs['fecha'] = pd.to_datetime(df_logs['fecha'])
                df_logs['fecha_dia'] = df_logs['fecha'].dt.date
                cg1, cg2 = st.columns(2)
                with cg1:
                    act = df_logs.groupby('fecha_dia').size().reset_index(name='cantidad')
                    st.plotly_chart(px.bar(act, x='fecha_dia', y='cantidad', title="Actividad/Día", color='cantidad', color_continuous_scale='Blues'), use_container_width=True)
                with cg2:
                    acc = df_logs['accion'].value_counts().reset_index()
                    acc.columns = ['accion', 'cantidad']
                    st.plotly_chart(px.bar(acc, x='accion', y='cantidad', title="Acciones", color='accion'), use_container_width=True)
                st.dataframe(df_logs[['usuario_email', 'accion', 'fecha']], use_container_width=True)
            else: st.info("Sin actividad.")
        except Exception as e: st.error(e)
        
    # Amenazas
    with tab_c:
        nueva = st.text_input("Adicionar Nueva Amenaza")
        if st.button("➕ Agregar"):
            if nueva:
                try:
                    supabase.table("amenazas").insert({"nombre": nueva.upper()}).execute()
                    st.success("Agregada.")
                    st.rerun()
                except: st.error("Ya existe.")
        st.markdown("---")
        st.dataframe(pd.DataFrame(get_amenazas(), columns=["Amenazas Configuradas"]), use_container_width=True, height=400)

    # Editar Evaluaciones
    with tab_d:
        st.markdown("### 📝 Editar Registros de Evaluaciones")
        st.warning("Modifique los campos necesarios y guarde los cambios. Se actualizará en la base de datos en tiempo real.")
        
        df_eval = get_evaluaciones_df()
        if not df_eval.empty:
            for index, row in df_eval.iterrows():
                with st.expander(f"Evaluación del {row['fecha_evaluacion'].strftime('%Y-%m-%d %H:%M')} - Índice: {row['indice_total']:.2f}"):
                    e_c1, e_c2 = st.columns(2)
                    with e_c1:
                        e_eval = st.text_input("Evaluador", row['evaluador'], key=f"e_eval_{row['id']}")
                        e_riesgo = st.text_input("Amenazas", row['nivel_riesgo'], key=f"e_riesgo_{row['id']}")
                        e_total = st.number_input("Índice Total", 0.0, 1.0, float(row['indice_total']), 0.01, key=f"e_total_{row['id']}")
                    with e_c2:
                        e_clase = st.selectbox("Clasificación", ["A", "B", "C"], index=["A", "B", "C"].index(row['clasificacion']), key=f"e_clase_{row['id']}")
                        e_est = st.number_input("Índice Estructural", 0.0, 1.0, float(row['indice_estructural']), 0.01, key=f"e_est_{row['id']}")
                        e_noest = st.number_input("Índice No Estructural", 0.0, 1.0, float(row['indice_no_estructural']), 0.01, key=f"e_noest_{row['id']}")
                        e_func = st.number_input("Índice Funcional", 0.0, 1.0, float(row['indice_funcional']), 0.01, key=f"e_func_{row['id']}")
                        e_auto = st.number_input("Autonomía (Horas)", 0, 72, int(row['autonomia_horas']), key=f"e_auto_{row['id']}")

                    if st.button("💾 Guardar Cambios en esta Evaluación", key=f"e_btn_{row['id']}"):
                        update_data = {
                            "evaluador": e_eval, "nivel_riesgo": e_riesgo, "indice_total": e_total,
                            "clasificacion": e_clase, "indice_estructural": e_est, "indice_no_estructural": e_noest,
                            "indice_funcional": e_func, "autonomia_horas": e_auto
                        }
                        try:
                            supabase.table("evaluaciones_ish").update(update_data).eq("id", row['id']).execute()
                            st.success("Evaluación actualizada en la base de datos.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al actualizar: {e}")
        else:
            st.info("No hay evaluaciones registradas para editar.")
