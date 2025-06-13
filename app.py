import streamlit as st
import paho.mqtt.client as mqtt
import os
import json
import time
import queue # DODAJ IMPORT KOLEJKI

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

# Utwórz kolejkę do przekazywania danych z wątku MQTT do głównego wątku Streamlit
if 'mqtt_queue' not in st.session_state:
    st.session_state.mqtt_queue = queue.Queue() # DODAJ KOLEJKĘ DO SESSION_STATE

# --- 3. Funkcje MQTT Callback ---
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
        
        # Włóż odebrane dane do kolejki
        # Sprawdzamy, czy kolejka istnieje, zanim do niej dodamy (dla bezpieczeństwa wątków)
        if 'mqtt_queue' in st.session_state:
            st.session_state.mqtt_queue.put(data) # Wstaw dane do kolejki
        else:
            print("Kolejka MQTT nie zainicjalizowana w session_state. Nie mogę dodać danych.")
        
    except json.JSONDecodeError:
        print(f"Błąd parsowania JSON z MQTT: {msg.payload}")
    except Exception as e:
        print(f"Inny błąd w on_message (poza aktualizacją session_state): {e}")

# --- 4. Inicjalizacja Klienta MQTT (z użyciem st.cache_resource) ---
@st.cache_resource
def get_mqtt_client():
    client = mqtt.Client()
    if not all([MQTT_USERNAME, MQTT_PASSWORD, MQTT_BROKER, MQTT_PORT]):
        st.session_state.mqtt_error = "Brak wszystkich danych uwierzytelniających MQTT. Upewnij się, że są ustawione w Streamlit Secrets."
        return None
        
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    
    client.tls_set()
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        print("MQTT client started in background loop.")
        st.session_state.mqtt_error = None
    except Exception as e:
        st.session_state.mqtt_error = f"Nie udało się połączyć z brokerem MQTT: {e}. Sprawdź konfigurację."
        print(f"Błąd połączenia MQTT w get_mqtt_client: {e}")
    return client

mqtt_client = get_mqtt_client()

# --- 5. Funkcja do aktualizacji danych z kolejki (wywoływana w głównym wątku Streamlit) ---
def update_data_from_mqtt_queue():
    while not st.session_state.mqtt_queue.empty():
        data = st.session_state.mqtt_queue.get()
        print(f"Pobrano z kolejki i aktualizuję UI: {data}")
        st.session_state.latest_data["temp"] = data.get("temp", st.session_state.latest_data["temp"])
        st.session_state.latest_data["hum"] = data.get("hum", st.session_state.latest_data["hum"])
        st.session_state.latest_data["alarm"] = data.get("alarm", st.session_state.latest_data["alarm"])
        st.session_state.last_update_time = time.strftime("%H:%M:%S")
    
    # Po przetworzeniu wszystkich elementów z kolejki, wymuś rerun, aby zaktualizować UI.
    # Upewnij się, że nie wywołujesz tego zbyt często.
    # Streamlit może odświeżać się automatycznie, ale dla pewności możemy wymusić.
    # Ważne: to st.rerun() jest w głównym wątku, więc jest bezpieczne.
    # Warto dodać opóźnienie lub mechanizm, aby nie odświeżało się co ms.
    # Na razie zostawimy tak, aby upewnić się, że dane są widoczne.
    st.rerun()


# --- 6. Interfejs Streamlit ---
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
else: # Jeśli nie ma błędu, spróbuj pobrać dane z kolejki
    # Wywołaj funkcję aktualizującą dane. Możesz tu dodać logikę, aby nie robić tego co sekundę,
    # np. tylko co X sekund, jeśli Streamlit nie odświeża się automatycznie wystarczająco szybko.
    # Na początek, po prostu wywołamy ją.
    update_data_from_mqtt_queue()

st.write("---")
st.subheader("Informacje")
st.markdown("""
    Ten system monitoruje temperaturę i wilgotność w domu.
    Wykrywa, czy temperatura znajduje się poza bezpiecznym zakresem (18°C - 25°C).
    Wszelkie dane są przesyłane bezpiecznie za pomocą protokołu MQTT z uwierzytelnieniem.
    """)

st.subheader("Sterowanie symulacją (Wokwi)")
st.write("Zmień temperaturę w symulacji Wokwi (DHT22), aby zobaczyć aktualizacje tutaj.")

if st.button("Odśwież stronę (Wymusza aktualizację)"):
    # Ten przycisk nadal będzie przydatny, aby ręcznie wymusić odświeżenie UI.
    st.rerun()

