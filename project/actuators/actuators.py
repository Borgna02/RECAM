import json
import os
import requests
import paho.mqtt.client as mqtt

# MQTT parameters and sensors API configuration using environment variables
BROKER = os.getenv("BROKER", "broker")
PORT = int(os.getenv("PORT", 1883))
MQTT_TOPIC = "/consumer/activation"
SENSORS_API = os.getenv("SENSORS_API", None)

class APIManager:
    """
    Handles connections with the API.
    """
    def __init__(self, base_url: str) -> None:
        # Removes any trailing slashes to avoid duplications
        self.base_url = base_url.rstrip('/')

    def activate_consumer(self, member_id, consumer):
        """
        Sends an activation request to the /activate endpoint.
        """
        url = f"{self.base_url}/activate"
        print(
            f"INFO: Sending activation request to {url} with consumer_id {consumer} and member_id {member_id}",
            flush=True,
        )
        response = requests.get(url, json={"consumer_id": consumer, "member_id": member_id})
        return response

class Actuator:
    """
    Represents an actuator capable of executing commands,
    for example, activating a device via an API.
    """
    def __init__(self, sensors_api: APIManager = None) -> None:
        self.api_manager = sensors_api

    def activate(self, member_id, consumer) -> None:
        print(f"INFO: Activating consumer {consumer} of member {member_id}", flush=True)
        if self.api_manager:
            try:
                response = self.api_manager.activate_consumer(member_id, consumer)
                if response.status_code == 200:
                    print(
                        f"INFO: Successfully sent activation to sensors API: {member_id} {consumer}",
                        flush=True,
                    )
                else:
                    print(
                        f"ERROR: Failed to activate consumer {consumer} for member {member_id}: "
                        f"{response.status_code} {response.text}",
                        flush=True,
                    )
            except requests.RequestException as e:
                print(f"ERROR: Error sending request to sensors API: {e}", flush=True)
            except Exception as e:
                print(f"ERROR: Error activating consumer: {e}", flush=True)
        else:
            print("ERROR: SENSORS_API is not configured", flush=True)

class MQTTManager:
    """
    Manages the MQTT connection, message reception, and distribution
    of commands to the actuator.
    """
    def __init__(self, broker: str, port: int, topic: str, actuator: Actuator) -> None:
        self.broker = broker
        self.port = port
        self.topic = topic
        self.actuator = actuator

        self.client = mqtt.Client(client_id="consumer", clean_session=False)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            print(f"INFO: Connected to MQTT broker {self.broker}:{self.port}", flush=True)
            client.subscribe(self.topic, qos=1)
        else:
            print(f"ERROR: Connection failed with result code {rc}", flush=True)

    def on_disconnect(self, client, userdata, rc) -> None:
        if rc != 0:
            print(f"ERROR: Unexpected disconnection from MQTT broker. Result code: {rc}", flush=True)
        else:
            print("INFO: Disconnected from MQTT broker", flush=True)

    def on_message(self, client, userdata, message) -> None:
        try:
            # Decodes the payload and converts it from JSON to a dictionary
            payload = json.loads(message.payload.decode("utf-8"))
            print(f"INFO: Received message on {message.topic}: {payload}", flush=True)

            if not isinstance(payload, dict):
                print("ERROR: Payload is not a dictionary", flush=True)
                raise ValueError("Payload is not a dictionary")

            # Extracts the necessary parameters
            member_id = payload.get("member_id")
            consumer_id = payload.get("consumer_id")
            action = payload.get("action")

            if not all([member_id, consumer_id, action]):
                raise ValueError("Missing required fields in payload")

            # Executes the command via the actuator
            self.actuator.activate(member_id, consumer_id)

        except json.JSONDecodeError:
            print("ERROR: Received invalid JSON payload", flush=True)
        except ValueError as e:
            print(f"ERROR: Invalid message format: {e}", flush=True)
        except Exception as e:
            print(f"ERROR: Error processing MQTT message: {e}", flush=True)

    def connect(self) -> None:
        try:
            self.client.connect(self.broker, self.port, keepalive=30)
        except Exception as e:
            print(f"ERROR: Failed to connect to MQTT broker: {e}", flush=True)
            raise

    def loop_forever(self) -> None:
        self.client.loop_forever()

def main() -> None:
    sensors_api = APIManager(SENSORS_API)
    actuator = Actuator(sensors_api)
    publisher = MQTTManager(BROKER, PORT, MQTT_TOPIC, actuator)

    try:
        publisher.connect()
        publisher.loop_forever()
    except KeyboardInterrupt:
        print("INFO: Subscriber stopped by user", flush=True)
        publisher.client.disconnect()
    except Exception as e:
        print(f"ERROR: Subscriber failed to start: {e}", flush=True)

# Run the actuator
if __name__ == "__main__":
    main()