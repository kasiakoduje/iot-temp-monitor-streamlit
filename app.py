import streamlit as st
import paho.mqtt.client as mqtt
import os
import json
import time
import queue

st.set_page_config(page_title="Inteligentny Monitoring Temperatury", layout="centered")

# Konfiguracja MQTT z zmiennych środowiskowych
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_TOPIC = os.getenv("MQTT_TOPIC")

# Zmienne do przechowywania danych z MQTT
if 'latest_data' not in st.session_state:
    st.session_state.latest_data = {
        "temp": "Łączę...",
        "hum": "Łączę...",
        "alarm": "Łączę..."
    }
    st.session_state.last_update_time = "N/A"
    st.session_state.mqtt_error = None

# Kolejka do przekazywania danych z wątku MQTT do głównego wątku Streamlit
@st.cache_resource
def get_mqtt_queue():
    return queue.Queue()

mqtt_data_queue = get_mqtt_queue() # Inicjalizacja kolejki - będzie to ten sam obiekt

# Klient MQTT 
@st.cache_resource
def get_mqtt_client_and_connect(broker, port, username, password, topic): # USUNIĘTO 'data_queue' Z ARGUMENTÓW
    client = mqtt.Client()
    
    if not all([username, password, broker, port]):
        st.session_state.mqtt_error = "Brak wszystkich danych uwierzytelniających MQTT."
        return None

    client.username_pw_set(username, password)
    client.tls_set()
    
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Połączono z brokerem MQTT!")
            client.subscribe(topic)
        else:
            print(f"Błąd połączenia z MQTT: {rc}. Spróbuję ponownie...")

    def on_message(client, userdata, msg):
        try:
            payload_str = msg.payload.decode('utf-8')
            data = json.loads(payload_str)
            
            mqtt_data_queue.put(data) 
            print(f"Odebrano MQTT i dodaję do kolejki: {data}")
        except json.JSONDecodeError:
            print(f"Błąd parsowania JSON z MQTT: {msg.payload}")
        except Exception as e:
            print(f"Inny błąd w on_message: {e}")

    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(broker, port, 60)
        client.loop_start()
        print("MQTT client started in background loop.")
        st.session_state.mqtt_error = None
    except Exception as e:
        st.session_state.mqtt_error = f"Nie udało się połączyć z brokerem MQTT: {e}. Sprawdź konfigurację."
        print(f"Błąd połączenia MQTT w get_mqtt_client: {e}")
    return client

# Wywołujemy klienta MQTT 
mqtt_client = get_mqtt_client_and_connect(
    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_TOPIC
)

# Funkcja do aktualizacji danych z kolejki
def update_ui_from_mqtt_queue():
    while not mqtt_data_queue.empty():
        try:
            data = mqtt_data_queue.get_nowait()
            st.session_state.latest_data["temp"] = data.get("temp", st.session_state.latest_data["temp"])
            st.session_state.latest_data["hum"] = data.get("hum", st.session_state.latest_data["hum"])
            st.session_state.latest_data["alarm"] = data.get("alarm", st.session_state.latest_data["alarm"])
            st.session_state.last_update_time = time.strftime("%H:%M:%S")
        except queue.Empty:
            break
        except Exception as e:
            print(f"Błąd podczas przetwarzania kolejki MQTT dla UI: {e}")
            break


st.title("🏡 Inteligentny Monitoring Temperatury w Domu")


update_ui_from_mqtt_queue()

# Wyświetlanie danych w kolumnach
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


if 'mqtt_error' in st.session_state and st.session_state.mqtt_error:
    st.error(st.session_state.mqtt_error)

st.write("---")
st.subheader("Informacje")
st.markdown("""
    Ten system monitoruje temperaturę i wilgotność w domu.
    Wykrywa, czy temperatura znajduje się poza bezpiecznym zakresem (18°C - 25°C).
    Wszelkie dane są przesyłane bezpiecznie za pomocą protokołu MQTT z uwierzytelnieniem.
    """)



time.sleep(1) # Odświeżanie co 1 sekundę
st.rerun() 
