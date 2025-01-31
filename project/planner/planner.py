import json
import os
from bottle import Bottle, request, run, HTTPResponse
import paho.mqtt.client as mqtt
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# MQTT broker configuration
BROKER = os.getenv("BROKER", "broker")  # Service name in docker-compose.yml
PORT = int(os.getenv("PORT", 1883))
MQTT_TOPIC = "commands/{member_id}/{consumer_id}"  # Dynamic topic structure

# Bottle app
app = Bottle()

# Helper function to determine activable consumers
def choose_consumers(data):
    """
    Decide which consumers to activate based on battery level, urgency, and constraints.
    :param data: JSON data from the request
    :return: Dictionary of activable consumers grouped by member
    """
    battery_level = data['battery']  # Battery level in kWh
    members:dict = data['members']
    activable = {}

    for member_id, consumers in members.items():
        # Separate urgent and non-urgent consumers
        urgent_consumers = [
            consumer for consumer in consumers if consumer['isUrgent']
        ]
        non_urgent_consumers = [
            consumer for consumer in consumers if not consumer['isUrgent']
        ]

        # Sort urgent consumers by (delta - tau), tight deadlines first
        urgent_consumers.sort(key=lambda c: c['delta'] - c['tau'])
        
        # Sort non-urgent consumers by (delta - tau), tight deadlines first
        non_urgent_consumers.sort(key=lambda c: c['delta'] - c['tau'])

        activable[member_id] = []  # Initialize list for this member

        # First, process urgent consumers (regardless of battery level)
        for consumer in urgent_consumers:
            activable[member_id].append({
                "consumer_id": consumer["consumer_id"],
                "action": "activate"
            })
            battery_level -= consumer['cons_required']  # Deduct battery usage

        # Then, process non-urgent consumers (if battery is sufficient)
        for consumer in non_urgent_consumers:
            if consumer['cons_required'] <= battery_level:
                activable[member_id].append({
                    "consumer_id": consumer["consumer_id"],
                    "action": "activate"
                })
                battery_level -= consumer['cons_required']  # Deduct battery usage
            else:
                activable[member_id].append({
                    "consumer_id": consumer["consumer_id"],
                    "action": "deactivate"
                })

    return activable

# Function to send activable consumers to the executor via MQTT
def send_to_executor(activable_consumers):
    """
    Send the activable consumers to the executor via MQTT.
    :param activable_consumers: Dictionary of activable consumers grouped by member
    """
    client = mqtt.Client()
    try:
        client.connect(BROKER, PORT)
        for member_id, consumers in activable_consumers.items():
            for consumer in consumers:
                topic = MQTT_TOPIC.format(
                    member_id=member_id,
                    consumer_id=consumer["consumer_id"]
                )
                payload = json.dumps(consumer)
                client.publish(topic, payload)
                logging.info(f"Published to {topic}: {payload}")
    except Exception as e:
        logging.error(f"Failed to send MQTT message: {e}")
    finally:
        client.disconnect()

# Route to handle activable consumers
@app.post('/activable_consumers')
def activable_consumers():
    """
    Receive a list of consumers that can be activated and determine which ones to activate.
    """
    try:
        data = request.json
        logging.info(f"Received activable consumers: {data}")

        # Validate input data
        if not data or 'members' not in data or 'battery' not in data:
            return HTTPResponse(
                body=json.dumps({"error": "Invalid input data"}),
                status=400,
                headers={"Content-Type": "application/json"}
            )

        # Decide which consumers to activate
        activable = choose_consumers(data)
        
        print(type(activable), activable, flush=True)

        # If there are activable consumers, send them to the Executor
        if any(activable.values()):
            send_to_executor(activable)
            return HTTPResponse(
                body=json.dumps({"status": "success", "activable": activable}),
                status=200,
                headers={"Content-Type": "application/json"}
            )
        else:
            return HTTPResponse(
                body=json.dumps({"status": "no consumers activated"}),
                status=200,
                headers={"Content-Type": "application/json"}
            )
    except Exception as e:
        print(f"Error processing request: {e}", flush=True)
        return HTTPResponse(
            body=json.dumps({"error": str(e)}),
            status=500,
            headers={"Content-Type": "application/json"}
        )

# Start the Bottle server
if __name__ == "__main__":
    run(app, host="0.0.0.0", port=8080)