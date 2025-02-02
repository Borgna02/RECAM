import json
import os
from bottle import Bottle, request, run, HTTPResponse
import paho.mqtt.client as mqtt

# Set debug flag based on environment variable
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

def debug_print(msg):
    """Print debug messages if DEBUG is enabled."""
    if DEBUG:
        print(msg, flush=True)

class MQTTManager:
    """
    Manages MQTT connection and message publishing.
    """
    def __init__(self, broker: str, port: int) -> None:
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(client_id="executor")
        try:
            self.client.connect(self.broker, self.port)
            self.client.loop_start()
            print(f"INFO: Connected to MQTT broker {self.broker}:{self.port}", flush=True)
        except Exception as e:
            print(f"ERROR: Failed to connect to MQTT broker: {e}", flush=True)

    def publish_message(self, topic: str, message: str) -> None:
        """
        Publishes a message to the specified MQTT topic.
        """
        try:
            self.client.publish(topic, message)
            print(f"INFO: Published message {message} to topic {topic}", flush=True)
            debug_print(f"DEBUG: MQTT publish details - topic: {topic}, message: {message}")
        except Exception as e:
            print(f"ERROR: Failed to publish message: {e}", flush=True)

class Executor:
    """
    Processes commands received from the planner and uses MQTTManager to publish MQTT messages.
    """
    def __init__(self, pubsub_manager: MQTTManager) -> None:
        self.pubsub_manager = pubsub_manager

    def process_command(self, member_id: str, consumer: dict) -> None:
        """
        Processes a command. If the action is 'activate', publishes an activation message.
        :param member_id: ID of the member.
        :param consumer: Consumer dictionary (e.g., {"consumer_id": "consumer1", "action": "activate"}).
        """
        action = consumer.get("action")
        if action == "activate":
            print(f"INFO: Activating consumer {consumer.get('consumer_id')} for member {member_id}", flush=True)
            try:
                topic = "/consumer/activation"
                message_payload = {
                    "member_id": member_id,
                    "consumer_id": consumer.get("consumer_id"),
                    "action": "activate"
                }
                message = json.dumps(message_payload)
                self.pubsub_manager.publish_message(topic, message)
                print(f"INFO: Activation message published: {message}", flush=True)
            except Exception as e:
                print(f"ERROR: Failed to publish activation message: {e}", flush=True)
        else:
            print(f"WARNING: Unknown action: {action}", flush=True)

class APIManager:
    """
    Manages the API endpoints using Bottle and routes commands to the Executor.
    """
    def __init__(self, executor: Executor) -> None:
        self.executor = executor
        self.app = Bottle()
        self.setup_routes()

    def setup_routes(self) -> None:
        @self.app.post('/commands')
        def receive_commands():
            """
            Receives commands from the planner and processes them.
            """
            try:
                data = request.json
                print(f"INFO: Received commands: {data}", flush=True)
                # Process each command in the received data
                for member_id, consumers in data.items():
                    for consumer in consumers:
                        self.executor.process_command(member_id, consumer)
                return HTTPResponse(
                    body=json.dumps({"status": "success"}),
                    status=200,
                    headers={"Content-Type": "application/json"}
                )
            except Exception as e:
                print(f"ERROR: Error processing commands: {e}", flush=True)
                return HTTPResponse(
                    body=json.dumps({"error": str(e)}),
                    status=500,
                    headers={"Content-Type": "application/json"}
                )

    def run(self, host: str = "0.0.0.0", port: int = 8081) -> None:
        """
        Runs the Bottle API server.
        """
        run(self.app, host=host, port=port)

if __name__ == "__main__":
    # Read MQTT broker configuration from environment variables
    BROKER = os.getenv('BROKER', 'broker')
    PORT = int(os.getenv('PORT', 1883))
    
    # Initialize MQTTManager, Executor, and APIManager
    pubsub_manager = MQTTManager(BROKER, PORT)
    executor = Executor(pubsub_manager)
    api_manager = APIManager(executor)
    
    # Run the Bottle API server
    api_manager.run()
