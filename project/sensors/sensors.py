import random
import json
import time
import threading
from bottle import Bottle, request, response, run
import os
import pandas as pd
import paho.mqtt.client as mqtt

# Debug mechanism via environment variable
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

def debug_print(msg):
    if DEBUG:
        print(msg, flush=True)

# Configuration of MQTT parameters and endpoints
BROKER = os.getenv("BROKER", "broker")
PORT = int(os.getenv("PORT", 1883))
PROD_TOPIC_STRUCTURE = "/producer/{member_id}/{prod_id}"
TAUDELTA_TOPIC_STRUCTURE = "/consumer/taudelta/{member_id}/{cons_id}"
BATTERY_TOPIC_STRUCTURE = "/battery"

# Simulation parameters
STEP_DURATION = int(os.getenv("STEP_DURATION", 1))  # duration of each step (seconds)
SECONDS_IN_A_SIMULATION_STEP = int(os.getenv("SECONDS_IN_A_SIMULATION_STEP", 60))
MINUTES_IN_A_SIMULATION_STEP = SECONDS_IN_A_SIMULATION_STEP / 60
HOURS_IN_A_SIMULATION_STEP = MINUTES_IN_A_SIMULATION_STEP / 60

TAU_DELTA_INTERVAL_BOUNDS = tuple(map(int, os.getenv("TAU_DELTA_INTERVAL_BOUNDS", "60,90").split(',')))

class Utils:
    @staticmethod
    def load_sensor_config() -> tuple:
        """
        Loads sensor configuration from the JSON file.
        Initializes tau, delta and activation status for each consumer.
        """
        with open('config/REC.json', 'r') as file:
            config = json.load(file)
            
        # Initialize tau and delta for each consumer
        for member in config["members"]:
            for consumer_id in config["members"][member]["consumers"]:
                config["members"][member]["consumers"][consumer_id]["tau"] = 0
                config["members"][member]["consumers"][consumer_id]["delta"] = 0
                config["members"][member]["consumers"][consumer_id]["activated"] = False
                
        return config["members"], config["battery"]

    @staticmethod
    def print_members_in_table(members: dict):
        """
        Prints the members' configuration in tabular format.
        """
        data = []
        # Append producers first
        for member_id, member_data in members.items():
            for producer_id, producer_data in member_data["producers"].items():
                data.append({
                    "member_id": member_id,
                    "type": "producer",
                    "id": producer_id,
                    "max_pi": producer_data["max-pi"],
                    "tau": None,
                    "delta": None,
                    "activated": None,
                    "cons": None
                })
        # Append consumers second
        for member_id, member_data in members.items():
            for consumer_id, consumer_data in member_data["consumers"].items():
                data.append({
                    "member_id": member_id,
                    "type": "consumer",
                    "id": consumer_id,
                    "max_pi": None,
                    "tau": consumer_data["tau"],
                    "delta": consumer_data["delta"],
                    "activated": consumer_data["activated"],
                    "cons": consumer_data["cons"]
                })
        df = pd.DataFrame(data)
        print(df.to_string(index=False), flush=True)

class MQTTManager:
    """
    Handles MQTT connection and message publishing.
    """
    def __init__(self, broker: str, port: int, prod_topic_structure: str,
                 taudelta_topic_structure: str, battery_topic_structure: str) -> None:
        self.broker = broker
        self.port = port
        self.prod_topic_structure = prod_topic_structure
        self.taudelta_topic_structure = taudelta_topic_structure
        self.battery_topic_structure = battery_topic_structure

        self.client = mqtt.Client("sensors")
        try:
            self.client.connect(self.broker, self.port)
            print(f"INFO: Connected to MQTT broker {self.broker}:{self.port}", flush=True)
        except Exception as e:
            print(f"ERROR: Failed to connect to MQTT broker: {e}", flush=True)
            raise

    def publish_production(self, member_id, prod_id, production, timestamp) -> None:
        topic = self.prod_topic_structure.format(member_id=member_id, prod_id=prod_id)
        message = f"production,producer_id={prod_id},member_id={member_id} value={production} {timestamp}"
        debug_print(f"DEBUG: Publishing on {topic}: {message}")
        self.client.publish(topic, message)

    def publish_tau_delta(self, cons_id, member_id, tau, delta, cons, activated, timestamp) -> None:
        topic = self.taudelta_topic_structure.format(member_id=member_id, cons_id=cons_id)
        message = f"tau_delta,consumer_id={cons_id},member_id={member_id},cons={cons} active={activated},tau={tau},delta={delta} {timestamp}"
        debug_print(f"DEBUG: Publishing on {topic}: {message}")
        self.client.publish(topic, message)

    def publish_battery(self, max_battery, battery_value, battery_consumption, non_battery_consumption, timestamp) -> None:
        topic = self.battery_topic_structure
        message = f"battery,max_value={max_battery} battery_consumption={battery_consumption},non_battery_consumption={non_battery_consumption},value={battery_value} {timestamp}"
        debug_print(f"DEBUG: Publishing on {topic}: {message}")
        self.client.publish(topic, message)

class APIManager:
    """
    Handles the API to update tau/delta parameters and activation status.
    """
    def __init__(self, sensor: "Sensor") -> None:
        self.sensor = sensor
        self.app = Bottle()
        self.setup_routes()

    def setup_routes(self) -> None:
        @self.app.post('/update_tau_delta')
        def update_tau_delta():
            data = request.json
            member_id = data.get('member_id')
            consumer_id = data.get('consumer_id')
            tau = data.get('tau')
            delta = data.get('delta')
            if member_id in self.sensor.members and consumer_id in self.sensor.members[member_id]["consumers"]:
                self.sensor.members[member_id]["consumers"][consumer_id]["tau"] = tau
                self.sensor.members[member_id]["consumers"][consumer_id]["delta"] = delta
                self.sensor.members[member_id]["consumers"][consumer_id]["activated"] = False
                response.content_type = 'application/json'
                return json.dumps({"status": "success"})
            else:
                response.status = 400
                response.content_type = 'application/json'
                return json.dumps({"status": "error", "message": "Invalid member_id or consumer_id"})

        @self.app.get('/health')
        def health():
            response.content_type = 'application/json'
            return json.dumps({"status": "ok"})

        @self.app.get('/activate')
        def update_activation_status():
            data = request.json
            member_id = data.get('member_id')
            consumer_id = data.get('consumer_id')
            print(f"INFO: Activation request received for {member_id}, {consumer_id}", flush=True)
            if member_id in self.sensor.members and consumer_id in self.sensor.members[member_id]["consumers"]:
                self.sensor.members[member_id]["consumers"][consumer_id]["activated"] = True
                response.content_type = 'application/json'
                return json.dumps({"status": "success"})
            else:
                response.status = 400
                response.content_type = 'application/json'
                return json.dumps({"status": "error", "message": "Invalid member_id or consumer_id"})

    def run(self) -> None:
        run(self.app, host="0.0.0.0", port=5000)

class Sensor:
    """
    Simulates sensor behavior, managing production, tau/delta distribution, and battery level.
    """
    def __init__(self, publishing_manager: MQTTManager) -> None:
        self.publishing_manager = publishing_manager
        self.members, self.battery_info = Utils.load_sensor_config()
        self.battery_value = 0
        self.step_counter = -1
        self.interval = random.randint(*TAU_DELTA_INTERVAL_BOUNDS)

    @staticmethod
    def generate_tau_delta_in_minutes():
        tau = random.randint(1, 5)
        delta = random.randint(tau + 1, int((tau + 1) * 1.5))
        return tau * 60, delta * 60

    @staticmethod
    def generate_production():
        return random.uniform(0, 1)

    def run(self) -> None:
        while True:
            Utils.print_members_in_table(self.members)
            timestamp = int(time.time() * 1e9)  # timestamp in nanoseconds

            total_production = 0
            total_consumption = 0

            # Processing each member
            for member_id, member_data in self.members.items():
                # Processing producers
                for producer_id, producer_data in member_data["producers"].items():
                    average_immediate_production = float(producer_data["max-pi"]) * self.generate_production()
                    production = average_immediate_production * HOURS_IN_A_SIMULATION_STEP
                    total_production += production
                    self.publishing_manager.publish_production(member_id, producer_id, production, timestamp)

                # Processing consumers
                for consumer_id, consumer_data in member_data["consumers"].items():
                    if consumer_data["delta"] > 0:
                        consumer_data["delta"] -= MINUTES_IN_A_SIMULATION_STEP
                    if consumer_data["activated"]:
                        consumer_data["tau"] -= MINUTES_IN_A_SIMULATION_STEP
                        if consumer_data["tau"] <= 0:
                            consumer_data["activated"] = False
                            consumer_data["tau"] = 0
                            consumer_data["delta"] = 0
                        total_consumption += consumer_data["cons"] * HOURS_IN_A_SIMULATION_STEP

                    self.publishing_manager.publish_tau_delta(
                        consumer_id,
                        member_id,
                        consumer_data["tau"],
                        consumer_data["delta"],
                        consumer_data["cons"],
                        consumer_data["activated"],
                        timestamp
                    )

            # Updating the battery value
            self.battery_value = max(min(self.battery_value + total_production, self.battery_info["max-capacity"]), 0)
            if total_consumption <= self.battery_value:
                battery_consumption = total_consumption
                non_battery_consumption = 0
                self.battery_value -= total_consumption
            else:
                battery_consumption = self.battery_value
                non_battery_consumption = total_consumption - self.battery_value
                self.battery_value = 0

            self.publishing_manager.publish_battery(
                self.battery_info["max-capacity"],
                self.battery_value,
                battery_consumption,
                non_battery_consumption,
                timestamp
            )

            # At each interval, generate new tau and delta for a random consumer
            if self.step_counter == self.interval or self.step_counter == -1:
                random_member_id = random.choice(list(self.members.keys()))
                member = self.members[random_member_id]
                unassigned_consumers = [cid for cid, cdata in member["consumers"].items() if cdata["tau"] == 0 and cdata["delta"] == 0]
                if unassigned_consumers:
                    random_consumer_id = random.choice(unassigned_consumers)
                    tau, delta = self.generate_tau_delta_in_minutes()
                    self.publishing_manager.publish_tau_delta(
                        random_consumer_id,
                        random_member_id,
                        tau,
                        delta,
                        member["consumers"][random_consumer_id]["cons"],
                        member["consumers"][random_consumer_id]["activated"],
                        timestamp
                    )
                    member["consumers"][random_consumer_id]["tau"] = tau
                    member["consumers"][random_consumer_id]["delta"] = delta
                self.step_counter = 0
                self.interval = random.randint(*TAU_DELTA_INTERVAL_BOUNDS)

            self.step_counter += 1
            time.sleep(STEP_DURATION)

# Main code
if __name__ == '__main__':
    publishing_manager = MQTTManager(BROKER, PORT, PROD_TOPIC_STRUCTURE, TAUDELTA_TOPIC_STRUCTURE, BATTERY_TOPIC_STRUCTURE)
    sensor = Sensor(publishing_manager)

    # Start API server in a separate thread
    api_manager = APIManager(sensor)
    api_thread = threading.Thread(target=api_manager.run)
    api_thread.daemon = True
    api_thread.start()

    # Start sensor simulation
    sensor.run()
