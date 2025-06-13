import streamlit as st
import paho.mqtt.client as mqtt
import os
import json
import time

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
    st.session_state.mqtt_error = None # Dodaj tę linię

# --- 3. Funkcje MQTT Callback ---
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Połączono z brokerem MQTT!")
        client.subscribe(MQTT_TOPIC)
        # st.success("Połączono z brokerem MQTT!") # Komentujemy, aby uniknąć błędów UI w callbacku
    else:
        print(f"Błąd połączenia z MQTT: {rc}. Spróbuję ponownie...")
        # st.error(f"Błąd połączenia z MQTT: {rc}. Spróbuję ponownie...") # Komentujemy

def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode('utf-8')
        data = json.loads(payload_str)
        print(f"Odebrano MQTT: {data}")
        
        # Aktualizuj stan sesji Streamlit - BEZ st.rerun() TUTAJ
        st.session_state.latest_data["temp"] = data.get("temp", st.session_state.latest_data["temp"])
        st.session_state.latest_data["hum"] = data.get("hum", st.session_state.latest_data["hum"])
        st.session_state.latest_data["alarm"] = data.get("alarm", st.session_state.latest_data["alarm"])
        st.session_state.last_update_time = time.strftime("%H:%M:%S")

        # WAŻNE: Nie wywołujemy st.rerun() bezpośrednio z callbacku MQTT.
        # Streamlit sam odświeży UI, gdy st.session_state się zmieni,
        # lub użytkownik naciśnie przycisk "Odśwież stronę".
        
    except json.JSONDecodeError:
        print(f"Błąd parsowania JSON z MQTT: {msg.payload}")
    except Exception as e:
        print(f"Inny błąd w on_message: {e}")

# --- 4. Inicjalizacja Klienta MQTT (z użyciem st.cache_resource) ---
@st.cache_resource
def get_mqtt_client():
    client = mqtt.Client()
    # Sprawdź, czy zmienne środowiskowe są dostępne przed próbą ich użycia
    if not all([MQTT_USERNAME, MQTT_PASSWORD, MQTT_BROKER, MQTT_PORT]):
        st.session_state.mqtt_error = "Brak wszystkich danych uwierzytelniających MQTT. Upewnij się, że są ustawione w Streamlit Secrets."
        return None # Zwróć None, jeśli brakuje danych
        
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    
    # Konfiguracja SSL/TLS
    client.tls_set() # Użyj domyślnych certyfikatów systemowych
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start() # Uruchom pętlę w tle do nasłuchiwania
        print("MQTT client started in background loop.")
        st.session_state.mqtt_error = None # Zresetuj błąd, jeśli połączenie się powiodło
    except Exception as e:
        # Zapisz błąd w session_state, żeby wyświetlić go w UI
        st.session_state.mqtt_error = f"Nie udało się połączyć z brokerem MQTT: {e}. Sprawdź konfigurację."
        print(f"Błąd połączenia MQTT w get_mqtt_client: {e}")
    return client

mqtt_client = get_mqtt_client()

# --- 5. Interfejs Streamlit ---
st.title("🏡 Inteligentny Monitoring Temperatury w Domu")

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

# DODAJ WYŚWIETLANIE BŁĘDU MQTT W GŁÓWNYM UI
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

# Przycisk "Odśwież stronę" jest teraz ważniejszy, ponieważ nie ma automatycznego st.rerun() z callbacku
if st.button("Odśwież stronę"):
    st.rerun() # Ten rerun jest bezpieczny, bo wywołuje go użytkownik
