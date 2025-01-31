import json
import os
from bottle import Bottle, request, run, HTTPResponse
import logging
import paho.mqtt.client as mqtt

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Bottle app
app = Bottle()

# Initialize MQTT client
BROKER = os.getenv('BROKER', 'broker')
PORT = int(os.getenv('PORT', 1883))

client = mqtt.Client(client_id=f"executor")
try:
    client.connect(BROKER, PORT)
    client.loop_start()
except Exception as e:
    logging.error(f"Failed to connect to MQTT broker: {e}")


# Route to handle commands from the planner
@app.post('/commands')
def receive_commands():
    """
    Receive commands from the planner and process them.
    """
    try:
        data = request.json
        logging.info(f"Received commands: {data}")

        # Process each command
        for member_id, consumers in data.items():
            for consumer in consumers:
                process_command(member_id, consumer)

        return HTTPResponse(
            body=json.dumps({"status": "success"}),
            status=200,
            headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        logging.error(f"Error processing commands: {e}")
        return HTTPResponse(
            body=json.dumps({"error": str(e)}),
            status=500,
            headers={"Content-Type": "application/json"}
        )

# Function to process a command
def process_command(member_id, consumer):
    """
    Process a command (e.g., activate a consumer).
    :param member_id: ID of the member
    :param consumer: Consumer dictionary (e.g., {"consumer_id": "consumer1", "action": "activate"})
    """
    action = consumer.get("action")
    if action == "activate":
        logging.info(f"Activating consumer {consumer['consumer_id']} for member {member_id}")
        try:
            # Utilizza sempre lo stesso topic
            topic = "/consumer/activation"
            # Includi member_id e consumer_id nel payload
            message = json.dumps({
                "member_id": member_id,
                "consumer_id": consumer['consumer_id'],
                "action": "activate"
            })
            client.publish(topic, message)
            logging.info(f"Published activation message {message} to {topic}")
        except Exception as e:
            logging.error(f"Failed to publish activation message: {e}")
    else:
        logging.warning(f"Unknown action: {action}")



# Start the Bottle server
if __name__ == "__main__":
    run(app, host="0.0.0.0", port=8081)