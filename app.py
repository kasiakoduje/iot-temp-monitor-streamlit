import streamlit as st
import paho.mqtt.client as mqtt
import os
import json
import time

# Zmienne do przechowywania danych z MQTT
if 'latest_data' not in st.session_state:
    st.session_state.latest_data = {
        "temp": "Łączę...",
        "hum": "Łączę...",
        "alarm": "Łączę..."
    }
    st.session_state.last_update_time = "N/A"


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Połączono z brokerem MQTT!")
        client.subscribe(MQTT_TOPIC)
        
    else:
        print(f"Błąd połączenia z MQTT: {rc}. Spróbuję ponownie...")
        

def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode('utf-8')
        data = json.loads(payload_str)
        print(f"Odebrano MQTT: {data}")
        
        # Aktualizuj stan sesji Streamlit
        st.session_state.latest_data["temp"] = data.get("temp", st.session_state.latest_data["temp"])
        st.session_state.latest_data["hum"] = data.get("hum", st.session_state.latest_data["hum"])
        st.session_state.latest_data["alarm"] = data.get("alarm", st.session_state.latest_data["alarm"])
        st.session_state.last_update_time = time.strftime("%H:%M:%S")

        
        st.rerun() # Wymusza ponowne uruchomienie skryptu i odświeżenie UI

    except json.JSONDecodeError:
        print(f"Błąd parsowania JSON z MQTT: {msg.payload}")
    except Exception as e:
        print(f"Inny błąd w on_message: {e}")

# --- 4. Inicjalizacja Klienta MQTT (z użyciem st.experimental_singleton) ---
@st.experimental_singleton
def get_mqtt_client():
    client = mqtt.Client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    
    # Konfiguracja SSL/TLS
    client.tls_set() # Użyj domyślnych certyfikatów systemowych
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start() # Uruchom pętlę w tle do nasłuchiwania
        print("MQTT client started in background loop.")
    except Exception as e:
        st.error(f"Nie udało się połączyć z brokerem MQTT: {e}. Sprawdź konfigurację.")
    return client

mqtt_client = get_mqtt_client()


st.set_page_config(page_title="Inteligentny Monitoring Temperatury", layout="centered", icon="🌡️")

st.title("🏡 Inteligentny Monitoring Temperatury w Domu")


col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="Temperatura", value=f"{st.session_state.latest_data['temp']} °C")

with col2:
    st.metric(label="Wilgotność", value=f"{st.session_state.latest_data['hum']} %")

with col3:
    alarm_status = st.session_state.latest_data['alarm']
    if alarm_status == True:
        st.error("🔴 ALARM! Temperatura poza zakresem!")
    elif alarm_status == False:
        st.success("🟢 Temperatura w normie.")
    else:
        st.info(f"⚪ Status: {alarm_status}") 

st.markdown(f"Ostatnia aktualizacja: **{st.session_state.last_update_time}**")

st.write("---")
st.subheader("Informacje")
st.markdown("""
    Ten system monitoruje temperaturę i wilgotność w domu.
    Wykrywa, czy temperatura znajduje się poza bezpiecznym zakresem (18°C - 25°C).
    Wszelkie dane są przesyłane bezpiecznie za pomocą protokołu MQTT z uwierzytelnieniem.
    """)

st.subheader("Sterowanie symulacją (Wokwi)")
st.write("Zmień temperaturę w symulacji Wokwi (DHT22), aby zobaczyć aktualizacje tutaj.")

st.button("Odśwież stronę") 