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
MQTT_PORT = int(os.getenv("MQTT_PORT", 8883)) # Upewnij się, że to 8883 dla SSL
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
# Kolejka powinna być zainicjalizowana poza st.session_state, jako zasób globalny
# zarządzany przez @st.cache_resource, lub w funkcji @st.cache_resource
# Upewnij się, że jest to ten sam obiekt kolejki, do którego dodają callbacki MQTT
@st.cache_resource
def get_mqtt_queue():
    return queue.Queue()

mqtt_data_queue = get_mqtt_queue() # Inicjalizacja kolejki

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
        print(f"Odebrano MQTT i dodaję do kolejki: {data}")
        
        # Włóż odebrane dane do kolejki
        mqtt_data_queue.put(data) # Używamy globalnego obiektu kolejki
        
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
    client.on_message = on_message # Ustaw callback dla odebranych wiadomości
    
    client.tls_set() # Użyj domyślnych certyfikatów systemowych
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start() # Uruchom pętlę w tle do nasłuchiwania
        print("MQTT client started in background loop.")
        st.session_state.mqtt_error = None # Zresetuj błąd, jeśli połączenie się powiodło
    except Exception as e:
        st.session_state.mqtt_error = f"Nie udało się połączyć z brokerem MQTT: {e}. Sprawdź konfigurację."
        print(f"Błąd połączenia MQTT w get_mqtt_client: {e}")
    return client

mqtt_client = get_mqtt_client() # Inicjalizacja klienta MQTT


# --- 5. Funkcja do aktualizacji danych z kolejki (wywoływana w głównym wątku Streamlit) ---
# Ta funkcja nie będzie wywoływać st.rerun() bezpośrednio!
def process_mqtt_queue_for_ui():
    updated = False
    while not mqtt_data_queue.empty():
        try:
            data = mqtt_data_queue.get_nowait() # Użyj get_nowait() aby nie blokować
            print(f"Pobrano z kolejki i aktualizuję st.session_state: {data}")
            st.session_state.latest_data["temp"] = data.get("temp", st.session_state.latest_data["temp"])
            st.session_state.latest_data["hum"] = data.get("hum", st.session_state.latest_data["hum"])
            st.session_state.latest_data["alarm"] = data.get("alarm", st.session_state.latest_data["alarm"])
            st.session_state.last_update_time = time.strftime("%H:%M:%S")
            updated = True
        except queue.Empty:
            break # Kolejka jest pusta
        except Exception as e:
            print(f"Błąd podczas przetwarzania kolejki MQTT: {e}")
            break # Przestań przetwarzać w przypadku błędu
    return updated # Zwróć, czy coś zostało zaktualizowane


# --- 6. Interfejs Streamlit ---
st.title("🏡 Inteligentny Monitoring Temperatury w Domu")

# Spróbuj przetworzyć dane z kolejki na początku uruchomienia Streamlit
# Jeśli są nowe dane, Streamlit odświeży się automatycznie (ponownie uruchamiając skrypt)
if process_mqtt_queue_for_ui():
    pass # Dane zostały zaktualizowane, Streamlit odświeży się sam

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

# Przycisk "Odśwież stronę" jest teraz kluczowy dla ręcznego odświeżania UI
if st.button("Odśwież stronę (Wymuś aktualizację)"):
    # Gdy użytkownik naciśnie przycisk, skrypt uruchomi się ponownie.
    # Wtedy process_mqtt_queue_for_ui() zostanie wywołane ponownie.
    st.rerun()

# Automatyczne odświeżanie (opcjonalne, może zużywać więcej zasobów)
# Możesz dodać to, jeśli Streamlit nie odświeża się wystarczająco szybko sam.
# Np. odświeżaj co 5 sekund, jeśli są nowe dane w kolejce.
# if mqtt_data_queue.qsize() > 0:
#     time.sleep(1) # Daj czas na zebranie danych w kolejce
#     st.rerun()

