import json
import os
from bottle import Bottle, request, run
import paho.mqtt.client as mqtt

# MQTT broker configuration
BROKER = os.getenv("BROKER", "broker")  # Service name in docker-compose.yml
PORT = int(os.getenv("PORT", 1883))
MQTT_TOPIC = "/consumer/activation"  # Topic for publishing activation commands

# Initialize the Bottle app
app = Bottle()

# Initialize the MQTT client
mqtt_client = mqtt.Client()

# Connect to the MQTT broker
def connect_mqtt():
    print(f"Connecting to MQTT broker at {PORT}...")
    mqtt_client.connect(PORT)
    print("Connected to MQTT broker successfully!")

# API endpoint to receive activation commands from the Planner
@app.post('/execute')
def execute():
    """
    API endpoint to receive activation decisions from the Planner.
    Expects JSON data with the format:
    {
        "m1": { "consumers": ["c3", "c4"] },
        "m2": { "consumers": ["c5"] }
    }
    """
    try:
        # Parse the JSON payload from the request
        data = request.json
        if not data:
            return {"error": "Invalid or missing JSON payload"}, 400

        print(f"Received activation data: {json.dumps(data, indent=2)}")

        # Publish activation messages to the MQTT broker
        for member_id, details in data.items():
            consumers = details.get("consumers", [])
            if consumers:
                payload = json.dumps({member_id: {"consumers": consumers}})
                mqtt_client.publish(MQTT_TOPIC, payload)
                print(f"Published to {MQTT_TOPIC}: {payload}")

        return {"status": "success", "message": "Activation commands published"}, 200

    except Exception as e:
        print(f"Error in execute endpoint: {str(e)}")
        return {"error": str(e)}, 500

# Main function to start the Executor
def main():
    # Connect to MQTT broker
    connect_mqtt()

    # Start the Bottle server
    print("Starting Executor API server on port 8081...")
    run(app, host="0.0.0.0", port=8081)

if __name__ == "__main__":
    main()
