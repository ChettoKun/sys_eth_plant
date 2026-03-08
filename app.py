import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import os
import google.generativeai as genai

# ==========================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Simulador BioSTEAM - Calentamiento de Mosto", 
    layout="wide"
)

# ==========================================
# 2. LÓGICA DE SIMULACIÓN (ENCAPSULADA)
# ==========================================
def ejecutar_simulacion(flujo_mosto, temp_mosto, temp_salida_w210):
    """
    Encapsula la simulación de BioSTEAM. 
    Limpia el entorno antes de cada corrida para evitar IDs duplicados.
    """
    # Limpieza obligatoria del flowsheet
    bst.main_flowsheet.clear()
    
    # Configuración Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)
    
    # Definición de Corrientes dinámicas
    mosto = bst.Stream("1-MOSTO",
                       Water=flujo_mosto * 0.9, 
                       Ethanol=flujo_mosto * 0.1, 
                       units="kg/hr",
                       T=temp_mosto + 273.15,
                       P=101325)
                       
    vinazas_retorno = bst.Stream("Vinazas-Retorno",
                                 Water=200, Ethanol=0, units="kg/hr",
                                 T=95 + 273.15, P=300000)
                                 
    # Selección de Equipos
    P100 = bst.Pump("P-100", ins=mosto, P=4*101325)
    
    W210 = bst.HXprocess("W-210",
                         ins=(P100-0, vinazas_retorno),
                         outs=("3-Mosto-Pre", "Drenaje"),
                         phase0="l", phase1="l")
                         
    # Especificación de diseño (Goal)
    W210.outs[0].T = temp_salida_w210 + 273.15
    
    # Crear y resolver el sistema
    sys = bst.System("sys", path=(P100, W210))
    sys.simulate()
    
    return sys, P100, W210

# ==========================================
# 3. INTERFAZ DE USUARIO (UI)
# ==========================================
st.title("⚙️ Simulación de Calentamiento de Mosto con Vinazas")
st.markdown("Ajusta los parámetros operativos en el panel lateral para evaluar el comportamiento del intercambiador de calor W-210.")

# Panel lateral para inputs
st.sidebar.header("Parámetros Operativos")
flujo_m = st.sidebar.slider("Flujo de Mosto (kg/hr)", min_value=500.0, max_value=1500.0, value=1000.0, step=50.0)
temp_m = st.sidebar.slider("Temperatura de Entrada (°C)", min_value=15.0, max_value=40.0, value=25.0, step=1.0)
temp_salida = st.sidebar.slider("Temp. Objetivo Salida W-210 (°C)", min_value=70.0, max_value=95.0, value=85.0, step=1.0)

# Botón de ejecución
if st.button("Ejecutar Simulación", type="primary"):
    with st.spinner("Resolviendo balances de materia y energía..."):
        # Llamar a la función de simulación
        sistema, bomba, intercambiador = ejecutar_simulacion(flujo_m, temp_m, temp_salida)
        
        st.success("Simulación completada con éxito.")
        
        # --- Mostrar Resultados ---
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Resultados del Equipo")
            # Extraer resultados manejando posibles errores de equipos sin duty
            potencia_bomba = bomba.power_utility.rate if bomba.power_utility else 0.0
            
            resultados_df = pd.DataFrame({
                "Variable": [
                    "Carga Térmica W-210 (kW)", 
                    "Temp. Real Salida Mosto (°C)",
                    "Potencia Bomba P-100 (kW)"
                ],
                "Valor": [
                    round(intercambiador.duty / 3600, 2), # Convertir kJ/hr a kW
                    round(intercambiador.outs[0].T - 273.15, 2),
                    round(potencia_bomba, 2)
                ]
            })
            st.table(resultados_df)
            
            # Guardar en memoria de Streamlit para la IA
            st.session_state['datos_simulacion'] = resultados_df.to_markdown()

        with col2:
            st.subheader("Diagrama de Flujo (PFD)")
            
            # Generar y mostrar el diagrama de forma segura
            try:
                # BioSTEAM usa graphviz, exportamos a png
                sistema.diagram(kind='surface', format='png', file='pfd_temporal')
                if os.path.exists('pfd_temporal.png'):
                    st.image('pfd_temporal.png', use_container_width=True)
            except Exception as e:
                st.warning(f"No se pudo renderizar el diagrama visual. Verifica que Graphviz esté instalado en el entorno. Error: {e}")

# ==========================================
# 4. INTEGRACIÓN DE IA (TUTOR VIRTUAL)
# ==========================================
st.divider()
st.header("🧠 Tutor de Ingeniería Química (IA)")

if 'datos_simulacion' in st.session_state:
    if st.button("Analizar resultados con el Tutor IA"):
        try:
            # Obtener la API Key de los secretos de Streamlit
            api_key = st.secrets["GEMINI_API_KEY"]
            genai.configure(api_key=api_key)
            modelo = genai.GenerativeModel('gemini-1.5-pro')
            
            prompt = f"""
            Actúa como un profesor experto en Ingeniería Química. 
            A continuación, te presento los resultados de una simulación de calentamiento de mosto con vinazas:
            
            {st.session_state['datos_simulacion']}
            
            Analiza estos datos de forma concisa. Explica brevemente si la transferencia de calor tiene sentido termodinámico 
            y dale al estudiante un consejo práctico sobre cómo optimizar este intercambiador de calor en una planta real.
            """
            
            with st.spinner("El tutor está analizando los datos termodinámicos..."):
                respuesta = modelo.generate_content(prompt)
                st.info(respuesta.text)
                
        except KeyError:
            st.error("Error: No se encontró la GEMINI_API_KEY en st.secrets. Asegúrate de configurarla en Streamlit Cloud.")
        except Exception as e:
            st.error(f"Error al conectar con la IA: {e}")
else:
    st.caption("Ejecuta la simulación primero para que la IA tenga datos que analizar.")
