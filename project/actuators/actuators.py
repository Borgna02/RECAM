import json
import os
import paho.mqtt.client as mqtt

# MQTT broker configuration
BROKER = os.getenv("BROKER", "broker")  # Service name in docker-compose.yml
PORT = int(os.getenv("PORT", 1883))
MQTT_TOPIC = "/consumer/activation"

# Callback for when the client connects to the MQTT broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker successfully!")
        client.subscribe(MQTT_TOPIC)  # Subscribe to the activation topic
        print(f"Subscribed to topic: {MQTT_TOPIC}")
    else:
        print(f"Failed to connect, return code {rc}")

# Callback for when a message is received on a subscribed topic
def on_message(client, userdata, message):
    try:
        # Decode the message payload
        payload = json.loads(message.payload.decode())
        print(f"Received activation message: {json.dumps(payload, indent=2)}")
        
        # Process the activation message
        for member_id, data in payload.items():
            consumers = data.get('consumers', [])
            for consumer_id in consumers:
                # Simulate activation of the consumer
                activate_consumer(member_id, consumer_id)
    except Exception as e:
        print(f"Error processing message: {str(e)}")

# Function to simulate the activation of a consumer device
def activate_consumer(member_id, consumer_id):
    print(f"Activating consumer {consumer_id} for member {member_id}")
    # Here you can implement actual hardware interaction (e.g., GPIO toggling)
    # For now, we are just simulating the activation
    # For example: GPIO.output(consumer_id, GPIO.HIGH)

# Main function
def main():
    # Initialize the MQTT client
    client = mqtt.Client()

    # Assign the callback functions
    client.on_connect = on_connect
    client.on_message = on_message

    # Connect to the MQTT broker
    print(f"Connecting to MQTT broker at {PORT}...")
    client.connect(PORT)

    # Start the MQTT client loop to listen for messages
    client.loop_forever()

if __name__ == "__main__":
    main()