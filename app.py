import streamlit as st
import paho.mqtt.client as mqtt
import os
import json
import time
import queue

# To musi być pierwsza instrukcja Streamlit w całym skrypcie!
st.set_page_config(page_title="Inteligentny Monitoring Temperatury", layout="centered")

# --- 1. Konfiguracja MQTT z zmiennych środowiskowych ---
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", 8883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_TOPIC = "home/monitor/data" # Temat, na który ESP32 wysyła JSON

# --- 2. Zmienne do przechowywania danych z MQTT (używamy st.session_state do persystencji w Streamlit) ---
if 'latest_data' not in st.session_state:
    st.session_state.latest_data = {
        "temp": "Łączę...",
        "hum": "Łączę...",
        "alarm": "Łączę..."
    }
    st.session_state.last_update_time = "N/A"
    st.session_state.mqtt_error = None

# --- Inicjalizacja kolejki i klienta MQTT jako zasoby cache'owane ---
# Kolejka do przekazywania danych z wątku MQTT do głównego wątku Streamlit
@st.cache_resource
def get_mqtt_queue():
    return queue.Queue()

mqtt_data_queue = get_mqtt_queue()

# Klient MQTT
@st.cache_resource
def get_mqtt_client_and_connect(broker, port, username, password, topic, data_queue):
    client = mqtt.Client()
    
    # Sprawdź, czy zmienne środowiskowe są dostępne przed próbą ich użycia
    if not all([username, password, broker, port]):
        st.session_state.mqtt_error = "Brak wszystkich danych uwierzytelniających MQTT. Upewnij się, że są ustawione w Streamlit Secrets."
        return None

    client.username_pw_set(username, password)
    client.tls_set() # Konfiguracja SSL/TLS
    
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
            # Włóż odebrane dane do kolejki
            data_queue.put(data)
            print(f"Odebrano MQTT i dodaję do kolejki: {data}")
        except json.JSONDecodeError:
            print(f"Błąd parsowania JSON z MQTT: {msg.payload}")
        except Exception as e:
            print(f"Inny błąd w on_message (poza aktualizacją session_state): {e}")

    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(broker, port, 60)
        client.loop_start() # Uruchom pętlę w tle do nasłuchiwania
        print("MQTT client started in background loop.")
        st.session_state.mqtt_error = None # Zresetuj błąd, jeśli połączenie się powiodło
    except Exception as e:
        st.session_state.mqtt_error = f"Nie udało się połączyć z brokerem MQTT: {e}. Sprawdź konfigurację."
        print(f"Błąd połączenia MQTT w get_mqtt_client: {e}")
    return client

mqtt_client = get_mqtt_client_and_connect(
    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_TOPIC, mqtt_data_queue
)

# --- 3. Funkcja do aktualizacji danych z kolejki (wywoływana w głównym wątku Streamlit) ---
def update_ui_from_mqtt_queue():
    while not mqtt_data_queue.empty():
        try:
            data = mqtt_data_queue.get_nowait()
            # Tutaj bezpiecznie aktualizujemy st.session_state
            st.session_state.latest_data["temp"] = data.get("temp", st.session_state.latest_data["temp"])
            st.session_state.latest_data["hum"] = data.get("hum", st.session_state.latest_data["hum"])
            st.session_state.latest_data["alarm"] = data.get("alarm", st.session_state.latest_data["alarm"])
            st.session_state.last_update_time = time.strftime("%H:%M:%S")
        except queue.Empty:
            break
        except Exception as e:
            print(f"Błąd podczas przetwarzania kolejki MQTT dla UI: {e}")
            break


# --- 4. Interfejs Streamlit ---
st.title("🏡 Inteligentny Monitoring Temperatury w Domu")

# Wywołujemy funkcję aktualizacji danych z kolejki
# Używamy pustego kontenera, który będziemy dynamicznie odświeżać
# (ten jest do prostszych layoutów, ale dla metrics możemy użyć też set_page_config)
placeholder = st.empty()

with placeholder.container():
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

# Wyświetlanie błędu MQTT (jeśli wystąpił podczas łączenia)
if 'mqtt_error' in st.session_state and st.session_state.mqtt_error:
    st.error(st.session_state.mqtt_error)

st.write("---")
st.subheader("Informacje")
st.markdown("""
    Ten system monitoruje temperaturę i wilgotność w domu.
    Wykrywa, czy temperatura znajduje się poza bezpiecznym zakresem (18°C - 25°C).
    Wszelkie dane są przesyłane bezpiecznie za pomocą protokołu MQTT z uwierzytelnieniem.
    """)

st.subheader("Sterowanie symulacją (Wokwi)")
st.write("Zmień temperaturę w symulacji Wokwi (DHT22), aby zobaczyć aktualizacje tutaj.")

# Automatyczne odświeżanie UI Streamlit
# Co X sekund Streamlit będzie uruchamiał skrypt od nowa
# i wtedy update_ui_from_mqtt_queue() sprawdzi kolejkę.
time.sleep(1) # Odświeżanie co 1 sekundę
st.rerun() # Wymusza ponowne uruchomienie skryptu
