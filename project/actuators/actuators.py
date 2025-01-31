import json
import os

import requests
import paho.mqtt.client as mqtt
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Abilita il logging per Paho MQTT
mqtt.logging.basicConfig(level=mqtt.logging.DEBUG)
mqtt.logging.getLogger("mqtt").setLevel(mqtt.logging.DEBUG)

# Enable Paho MQTT logging
mqtt_logging = logging.getLogger("mqtt")
mqtt_logging.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
mqtt_logging.addHandler(handler)



# MQTT broker configuration
BROKER = os.getenv("BROKER", "broker")
PORT = int(os.getenv("PORT", 1883))
MQTT_TOPIC = "/consumer/activation"
SENSORS_API = os.getenv("SENSORS_API", None)

# Funzione di callback per il reconnect
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info(f"Connected to MQTT broker {BROKER}:{PORT}")
        client.subscribe(MQTT_TOPIC, qos=1)
    else:
        logging.error(f"Connection failed with result code {rc}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        logging.error(f"Unexpected disconnection from MQTT broker. Result code: {rc}")
    else:
        logging.info("Disconnected from MQTT broker")

# MQTT on_message callback
def on_message(client, userdata, message):
    try:
        # Convert bytes to string and parse JSON
        payload = json.loads(message.payload.decode("utf-8"))
        logging.info(f"Received message on {message.topic}: {payload}")

        # Check if payload is a dictionary
        if not isinstance(payload, dict):
            logging.error("Payload is not a dictionary")
            raise ValueError("Payload is not a dictionary")

        # Extract member_id and consumer_id from payload
        member_id = payload.get("member_id")
        consumer_id = payload.get("consumer_id")
        action = payload.get("action")

        if not all([member_id, consumer_id, action]):
            raise ValueError("Missing required fields in payload")

        # Process the command (e.g., turn on/off a device)
        process_command(member_id, consumer_id)

    except json.JSONDecodeError:
        logging.error("Received invalid JSON payload")
    except ValueError as e:
        logging.error(f"Invalid message format: {e}")
    except Exception as e:
        logging.error(f"Error processing MQTT message: {e}")

# Function to process a command
def process_command(member_id, consumer):
    logging.info(f"Activating consumer {consumer} of member {member_id}")
    if SENSORS_API:
        try:
            response = requests.get(f"{SENSORS_API}/activate", json={"consumer_id": consumer, "member_id": member_id})
            if response.status_code == 200:
                logging.info(f"Successfully sent activation to sensors api: {member_id} {consumer}")
            else:
                logging.error(f"Failed to activate consumer {consumer} for member {member_id}: {response.status_code} {response.text}")
        except requests.RequestException as e:
            logging.error(f"Error sending request to {SENSORS_API}/activate: {e}")
        except Exception as e:
            logging.error(f"Error activating consumer: {e}")
    else:
        logging.error("SENSORS_API is not configured")

# Set up MQTT client
def setup_mqtt_client():
    client = mqtt.Client(client_id=f"consumer", clean_session=False)
    client.on_message = on_message
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    try:
        client.connect(BROKER, PORT, keepalive=30)
        return client
    except Exception as e:
        logging.error(f"Failed to connect to MQTT broker: {e}")
        raise

# Run the actuator
if __name__ == "__main__":
    # Set up MQTT client
    try:
        client = setup_mqtt_client()
        client.loop_forever()
    except KeyboardInterrupt:
        logging.info("Subscriber stopped by user")
        client.disconnect()
    except Exception as e:
        logging.error(f"Subscriber failed to start: {e}")