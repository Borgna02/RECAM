import json
import time
from influxdb_client import InfluxDBClient
import os
import pandas as pd
import requests

import warnings
from influxdb_client.client.warnings import MissingPivotFunction
warnings.simplefilter("ignore", MissingPivotFunction)


BUCKET = os.getenv('INFLUXDB_BUCKET')
TOKEN = os.getenv('INFLUXDB_TOKEN')
ORG = os.getenv('INFLUXDB_ORG')
URL = os.getenv('INFLUXDB_URL')
PLANNER_API = os.getenv('PLANNER_API')


def load_sensor_config() -> dict:
    with open('config/REC.json', 'r') as file:
        config = json.load(file)

    consumers = {}

    # Initialize tau and delta for each consumer
    for member in config["members"]:
        for consumer_id in config["members"][member]["consumers"]:
            config["members"][member]["consumers"][consumer_id]["tau"] = 0
            config["members"][member]["consumers"][consumer_id]["delta"] = 0
            config["members"][member]["consumers"][consumer_id]["active"] = False
            config["members"][member]["consumers"][consumer_id]["cons_required"] = 0

        consumers[member] = config["members"][member]["consumers"]
 
    return consumers


def query_influxdb(query: str):
    TOKEN = os.getenv('INFLUXDB_TOKEN')
    ORG = os.getenv('INFLUXDB_ORG')
    URL = os.getenv('INFLUXDB_URL')
    client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
    query_api = client.query_api()

    retries = 10
    for attempt in range(retries):
        try:
            query_result = query_api.query_data_frame(query)
            
            # Controlla se query_result è una lista
            if isinstance(query_result, list):
                # Concatena i DataFrame se ci sono più risultati
                return pd.concat(query_result, ignore_index=True)
            else:
                # Ritorna direttamente il DataFrame se è un singolo risultato
                return query_result

        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}", flush=True)
            if attempt < retries - 1:
                time.sleep(5)
            else:
                raise


# Get the current battery level from InfluxDB
def get_battery_level():
    query = f"""
        from(bucket: "{BUCKET}")
            |> range(start: -30s)
            |> filter(fn: (r) => r["_measurement"] == "battery")
            |> last()
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        """

    return query_influxdb(query)["value"].values[0]

# Get the current tau and delta values from InfluxDB
def update_tau_delta(consumers: dict):
    query = f"""
        from(bucket: "{BUCKET}")
            |> range(start: -30s)
            |> filter(fn: (r) => r["_measurement"] == "tau_delta")
            |> last()
        """

    query_result = query_influxdb(query)

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

# Calculate the required consumption for each consumer
def calculate_cons_required(consumers: dict):
    for member in consumers:
        for consumer in consumers[member]:
            consumers[member][consumer]["cons_required"] = (consumers[member][consumer]["tau"]/60) * consumers[member][consumer]["cons"]
            
    return consumers

# Get the consumers that can be activated
def get_activable_consumers(consumers: dict, battery_level: float):
    activable_consumers = {}
    for member in consumers:
        activable_consumers[member] = [] if member not in activable_consumers else activable_consumers[member]
        for consumer in consumers[member]:
            if not consumers[member][consumer]["active"]:
                delta = consumers[member][consumer]["delta"]
                tau = consumers[member][consumer]["tau"]
                isUrgent = True if delta - tau < 15 and tau > 0 else False

                if (consumers[member][consumer]["cons_required"] > 0 and battery_level > consumers[member][consumer]["cons_required"]) or isUrgent:
                    activable_consumers[member].append({"consumer_id": consumer, "cons_required": consumers[member][consumer]["cons_required"], "tau": tau, "delta": delta, "isUrgent": isUrgent})
                
        if not activable_consumers[member]:
            del activable_consumers[member]
    return activable_consumers

def send_activable_consumers(activable_consumers: dict):
    url = f"{PLANNER_API}/activable_consumers"
    print(url, flush=True)
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


def print_activable_consumers_in_table(activable_consumers: dict):
    df = pd.DataFrame.from_dict({(i, j): activable_consumers[i][j] 
                                    for i in activable_consumers.keys() 
                                    for j in range(len(activable_consumers[i]))},
                                orient='index')
    df.reset_index(inplace=True)
    df.drop(columns='level_1', inplace=True)
    df.rename(columns={'level_0': 'member_id'}, inplace=True)
    print(df.to_string(index=False), flush=True)

if __name__ == '__main__':

    consumers = load_sensor_config()
    time.sleep(10)
    while True:
        battery_level = get_battery_level()
        consumers = update_tau_delta(consumers)
        consumers = calculate_cons_required(consumers)
        activable_consumers = get_activable_consumers(consumers, battery_level)
        
        if activable_consumers:
            message = {"members": activable_consumers, "battery": battery_level}
            send_activable_consumers(message)
            print_activable_consumers_in_table(activable_consumers)
            
        time.sleep(1)
