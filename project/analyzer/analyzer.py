import json
import time
import os
import pandas as pd
import requests
import warnings
from influxdb_client import InfluxDBClient
from influxdb_client.client.warnings import MissingPivotFunction

# Suppress specific InfluxDB warnings
warnings.simplefilter("ignore", MissingPivotFunction)

# Environment variables
BUCKET = os.getenv('INFLUXDB_BUCKET')
TOKEN = os.getenv('INFLUXDB_TOKEN')
ORG = os.getenv('INFLUXDB_ORG')
URL = os.getenv('INFLUXDB_URL')
PLANNER_API = os.getenv('PLANNER_API')
IS_URGENT_THRESHOLD = int(os.getenv('IS_URGENT_THRESHOLD'))
SIMULATION_STEP = int(os.getenv('SIMULATION_STEP', 1))


class DBManager:
    """
    Handles InfluxDB queries and sensor configuration updates.
    """
    def __init__(self, bucket: str, token: str, org: str, url: str):
        self.bucket = bucket
        self.token = token
        self.org = org
        self.url = url
        self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
        self.query_api = self.client.query_api()

    def query(self, query_str: str) -> pd.DataFrame:
        """
        Executes an InfluxDB query and returns the result as a pandas DataFrame.
        Retries up to 10 times if the query fails.
        """
        retries = 10
        for attempt in range(retries):
            try:
                query_result = self.query_api.query_data_frame(query_str)
                # If query_result is a list of DataFrames, concatenate them
                if isinstance(query_result, list):
                    return pd.concat(query_result, ignore_index=True)
                else:
                    return query_result
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {e}", flush=True)
                if attempt < retries - 1:
                    time.sleep(5)
                else:
                    raise

    def get_battery_level(self) -> float:
        """
        Retrieves the current battery level from InfluxDB.
        """
        query_str = f"""
            from(bucket: "{self.bucket}")
                |> range(start: -30s)
                |> filter(fn: (r) => r["_measurement"] == "battery")
                |> last()
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        """
        df = self.query(query_str)
        # Assumes the battery level is in the column "value"
        return df["value"].values[0]

    def update_tau_delta(self, consumers: dict) -> dict:
        """
        Updates tau, delta, and active status for each consumer by querying InfluxDB.
        """
        query_str = f"""
            from(bucket: "{self.bucket}")
                |> range(start: -30s)
                |> filter(fn: (r) => r["_measurement"] == "tau_delta")
                |> last()
        """
        query_result = self.query(query_str)
        for _, row in query_result.iterrows():
            member_id = row["member_id"]
            consumer_id = row["consumer_id"]
            field = row["_field"]
            value = row["_value"]
            if member_id in consumers and consumer_id in consumers[member_id]:
                if field == "tau":
                    consumers[member_id][consumer_id]["tau"] = value
                elif field == "delta":
                    consumers[member_id][consumer_id]["delta"] = value
                elif field == "active":
                    consumers[member_id][consumer_id]["active"] = value
        return consumers

    def calculate_cons_required(self, consumers: dict) -> dict:
        """
        Calculates the required consumption for each consumer based on tau and the consumption rate.
        """
        for member in consumers:
            for consumer in consumers[member]:
                # Convert tau from seconds to minutes (tau/60) and multiply by the consumption rate (cons)
                consumers[member][consumer]["cons_required"] = (consumers[member][consumer]["tau"] / 60) * consumers[member][consumer]["cons"]
        return consumers

    def load_sensor_config(self) -> dict:
        """
        Loads the sensor configuration from the REC.json file and initializes values.
        """
        with open('config/REC.json', 'r') as file:
            config = json.load(file)

        consumers = {}
        # Initialize tau, delta, active and cons_required for each consumer
        for member in config["members"]:
            for consumer_id in config["members"][member]["consumers"]:
                config["members"][member]["consumers"][consumer_id]["tau"] = 0
                config["members"][member]["consumers"][consumer_id]["delta"] = 0
                config["members"][member]["consumers"][consumer_id]["active"] = False
                config["members"][member]["consumers"][consumer_id]["cons_required"] = 0
            consumers[member] = config["members"][member]["consumers"]
        return consumers


class Analyzer:
    """
    Analyzes sensor data to determine which consumers are eligible for activation.
    """
    def __init__(self, is_urgent_threshold: int):
        self.is_urgent_threshold = is_urgent_threshold

    def get_activable_consumers(self, consumers: dict, battery_level: float) -> dict:
        """
        Determines which consumers can be activated based on their tau, delta,
        required consumption, and the current battery level.
        """
        activable_consumers = {}
        for member in consumers:
            activable_consumers[member] = []
            for consumer in consumers[member]:
                # Only consider consumers that are not currently active
                if not consumers[member][consumer]["active"]:
                    delta = consumers[member][consumer]["delta"]
                    tau = consumers[member][consumer]["tau"]
                    # Determine urgency: if (delta - tau) is less than the threshold and tau is positive
                    is_urgent = True if (delta - tau) < self.is_urgent_threshold and tau > 0 else False
                    # If the consumer requires consumption and battery is sufficient, or if it is urgent
                    if (consumers[member][consumer]["cons_required"] > 0 and battery_level > consumers[member][consumer]["cons_required"]) or is_urgent:
                        activable_consumers[member].append({
                            "consumer_id": consumer,
                            "cons_required": consumers[member][consumer]["cons_required"],
                            "tau": tau,
                            "delta": delta,
                            "isUrgent": is_urgent
                        })
            if not activable_consumers[member]:
                # Remove member if there are no activable consumers
                del activable_consumers[member]
        return activable_consumers

    def print_activable_consumers_in_table(self, activable_consumers: dict) -> None:
        """
        Prints the activable consumers in a tabular format using pandas.
        """
        df = pd.DataFrame.from_dict({(i, j): activable_consumers[i][j]
                                       for i in activable_consumers.keys()
                                       for j in range(len(activable_consumers[i]))},
                                      orient='index')
        df.reset_index(inplace=True)
        df.drop(columns='level_1', inplace=True)
        df.rename(columns={'level_0': 'member_id'}, inplace=True)
        print(df.to_string(index=False), flush=True)


class APIManager:
    """
    Manages communication with the Planner API.
    """
    def __init__(self, planner_api: str):
        self.planner_api = planner_api

    def send_activable_consumers(self, activable_consumers: dict) -> None:
        """
        Sends the activable consumers data to the Planner API.
        Retries up to 5 times if the request fails.
        """
        url = f"{self.planner_api}/activable_consumers"
        headers = {'Content-Type': 'application/json'}
        retries = 5
        for attempt in range(retries):
            try:
                response = requests.post(url, headers=headers, json=activable_consumers)
                if response.status_code == 200:
                    print("Data successfully sent to the planner API.", flush=True)
                    break
                else:
                    print(f"Failed to send data to the planner API. Status code: {response.status_code}", flush=True)
                    if attempt < retries - 1:
                        time.sleep(5)
            except requests.exceptions.ConnectionError as e:
                print(f"Attempt {attempt + 1} failed: {e}", flush=True)
                if attempt < retries - 1:
                    time.sleep(5)
                else:
                    print("Max retries exceeded. Could not connect to the planner API.", flush=True)


if __name__ == '__main__':
    db_manager = DBManager(BUCKET, TOKEN, ORG, URL)
    analyzer = Analyzer(IS_URGENT_THRESHOLD)
    api_manager = APIManager(PLANNER_API)

    consumers = db_manager.load_sensor_config()
    print("Starting simulation with simulation step", SIMULATION_STEP, flush=True)
    time.sleep(10)
    while True:
        battery_level = db_manager.get_battery_level()
        consumers = db_manager.update_tau_delta(consumers)
        consumers = db_manager.calculate_cons_required(consumers)
        activable_consumers = analyzer.get_activable_consumers(consumers, battery_level)

        if activable_consumers:
            message = {"members": activable_consumers, "battery": battery_level}
            api_manager.send_activable_consumers(message)
            analyzer.print_activable_consumers_in_table(activable_consumers)
        time.sleep(SIMULATION_STEP)
