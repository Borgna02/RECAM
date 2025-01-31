import json
import os
from bottle import Bottle, request, run, HTTPResponse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Bottle app
app = Bottle()

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
    Process a command (e.g., activate or deactivate a consumer).
    :param member_id: ID of the member
    :param consumer: Consumer dictionary (e.g., {"consumer_id": "consumer1", "action": "activate"})
    """
    action = consumer.get("action")
    if action == "activate":
        logging.info(f"Activating consumer {consumer['consumer_id']} for member {member_id}")
        # TODO: Implement activation logic (e.g., send signal to actuator)
    elif action == "deactivate":
        logging.info(f"Deactivating consumer {consumer['consumer_id']} for member {member_id}")
        # TODO: Implement deactivation logic (e.g., send signal to actuator)
    else:
        logging.warning(f"Unknown action: {action}")

# Start the Bottle server
if __name__ == "__main__":
    run(app, host="0.0.0.0", port=8081)