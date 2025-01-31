import json
import os
import paho.mqtt.client as mqtt
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# MQTT broker configuration
BROKER = os.getenv("BROKER", "broker")  # Service name in docker-compose.yml
PORT = int(os.getenv("PORT", 1883))
MQTT_TOPIC = "commands/+/+"  # Subscribe to all commands

# MQTT on_message callback
def on_message(client, userdata, message):
    """
    Callback function to handle incoming MQTT messages.
    """
    try:
        # Decode the message payload
        payload = message.payload.decode("utf-8")
        command = json.loads(payload)
        logging.info(f"Received command: {command}")

        # Extract topic information
        topic_parts = message.topic.split("/")
        member_id = topic_parts[1]
        consumer_id = topic_parts[2]

        # Process the command (e.g., turn on/off a device)
        process_command(member_id, consumer_id, command)

    except Exception as e:
        logging.error(f"Error processing MQTT message: {e}")

# Function to process commands
def process_command(member_id, consumer_id, command):
    """
    Process a command (e.g., activate or deactivate a device).
    :param member_id: ID of the member
    :param consumer_id: ID of the consumer
    :param command: Command dictionary (e.g., {"action": "activate"})
    """
    action = command.get("action")
    if action == "activate":
        logging.info(f"Activating device for consumer {consumer_id} (Member: {member_id})")
        # TODO: Implement device activation logic (e.g., turn on a relay)
    elif action == "deactivate":
        logging.info(f"Deactivating device for consumer {consumer_id} (Member: {member_id})")
        # TODO: Implement device deactivation logic (e.g., turn off a relay)
    else:
        logging.warning(f"Unknown action: {action}")

# Set up MQTT client
def setup_mqtt_client():
    """
    Set up and connect the MQTT client.
    """
    client = mqtt.Client()
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, 60)
        client.subscribe(MQTT_TOPIC)
        logging.info(f"Subscribed to MQTT topic: {MQTT_TOPIC}")
        return client
    except Exception as e:
        logging.error(f"Failed to connect to MQTT broker: {e}")
        raise

# Run the actuator
if __name__ == "__main__":
    # Set up MQTT client
    mqtt_client = setup_mqtt_client()

    # Start the MQTT loop (blocking)
    mqtt_client.loop_forever()