import json
import os
from bottle import Bottle, request, run
import paho.mqtt.client as mqtt

# MQTT broker configuration
BROKER = os.getenv("BROKER", "broker")  # Service name in docker-compose.yml
PORT = int(os.getenv("PORT", 1883))
MQTT_TOPIC = "/consumer/activation"

# Bottle app
app = Bottle()

# Helper function to determine activable consumers
def choose_consumers(data):
    """
    Decide which consumers to activate based on battery level and constraints.
    :param data: JSON data from the request
    :return: Dictionary of activable consumers grouped by member
    """
    battery_level = data['battery']  # Battery level in kWh
    members = data['members']
    activable = {}

    for member in members:
        for member_id, consumers in member.items():
            # Sort consumers by (delta - tau), tight deadlines first
            consumers.sort(key=lambda c: c['delta'] - c['tau'])
            
            activable[member_id] = []  # Initialize list for this member
            for consumer in consumers:
                if consumer['cons_required'] <= battery_level:
                    # If battery is sufficient, activate the consumer
                    activable[member_id].append(consumer['consumer_id'])
                    battery_level -= consumer['cons_required']  # Deduct battery usage
                else:
                    break  # Stop processing if battery is insufficient

    return activable

# Route to handle activable consumers
@app.post('/activable_consumers')
def activable_consumers():
    """
    Receive a list of consumers that can be activated and determine which ones to activate.
    """
    try:
        # Parse the input JSON
        data = request.json
        if not data or 'members' not in data or 'battery' not in data:
            return {'error': 'Invalid input data'}, 400

        # Decide which consumers to activate
        activable = choose_consumers(data)

        # If there are activable consumers, send them to the Executor
        if any(activable.values()):
            send_to_executor(activable)
            return {'status': 'success', 'activable': activable}, 200
        else:
            return {'status': 'no consumers activated'}, 200
    except Exception as e:
        return {'error': str(e)}, 500

# Function to send activable consumers to the executor
def send_to_executor(activable_consumers):
    """
    Send the activable consumers to the executor via MQTT.
    :param activable_consumers: Dictionary of activable consumers grouped by member
    """
    client = mqtt.Client()
    client.connect(BROKER, PORT)

    for member_id, consumers in activable_consumers.items():
        if consumers:  # Only send if there are consumers to activate
            payload = json.dumps({member_id: {'consumers': consumers}})
            client.publish(MQTT_TOPIC, payload)
            print(f"Published to {MQTT_TOPIC}: {payload}")

    client.disconnect()

# Start the Bottle server
if __name__ == "__main__":
    run(app, host="0.0.0.0", port=8080)
