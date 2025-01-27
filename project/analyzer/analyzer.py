import json
import time
from influxdb_client import InfluxDBClient
import os
import pandas as pd
import requests

import warnings
from influxdb_client.client.warnings import MissingPivotFunction
warnings.simplefilter("ignore", MissingPivotFunction)

def load_sensor_config() -> dict:
    with open('config/REC.json', 'r') as file:
        config = json.load(file)

    consumers = {}

    # Initialize tau and delta for each consumer
    for member in config["members"]:
        for consumer_id in config["members"][member]["consumers"]:
            config["members"][member]["consumers"][consumer_id]["tau"] = 0
            config["members"][member]["consumers"][consumer_id]["delta"] = 0
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
            return query_api.query_data_frame(query)
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}", flush=True)
            if attempt < retries - 1:
                time.sleep(5)
            else:
                raise


def get_battery_level():
    BUCKET = os.getenv('INFLUXDB_BUCKET')
    query = f"""
        from(bucket: "{BUCKET}")
            |> range(start: -30s)
            |> filter(fn: (r) => r["_measurement"] == "battery")
            |> last()
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        """

    return query_influxdb(query)["value"].values[0]


def update_tau_delta(consumers: dict):
    BUCKET = os.getenv('INFLUXDB_BUCKET')
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

    return consumers


def calculate_cons_required(consumers: dict):
    for member in consumers:
        for consumer in consumers[member]:
            consumers[member][consumer]["cons_required"] = (consumers[member][consumer]["tau"]/60) * consumers[member][consumer]["cons"]
            
    return consumers

def get_activable_consumers(consumers: dict, battery_level: float):
    activable_consumers = {}
    for member in consumers:
        for consumer in consumers[member]:
            if consumers[member][consumer]["cons_required"] > 0 and battery_level > consumers[member][consumer]["cons_required"]:
                activable_consumers[member] = {"consumer_id": consumer, "cons_required": consumers[member][consumer]["cons_required"], "tau": consumers[member][consumer]["tau"], "delta": consumers[member][consumer]["delta"]}
    return activable_consumers

def send_activable_consumers(activable_consumers: dict):
    PLANNER_API = os.getenv('PLANNER_API')
    url = f"{PLANNER_API}/activable_consumers"
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, headers=headers, json=activable_consumers)

    if response.status_code == 200:
        print("Data successfully sent to the planner API.")
    else:
        print(f"Failed to send data to the planner API. Status code: {response.status_code}")


if __name__ == '__main__':

    consumers = load_sensor_config()
    print(consumers, flush=True)
    time.sleep(10)
    while True:
        battery_level = get_battery_level()
        consumers = update_tau_delta(consumers)
        consumers = calculate_cons_required(consumers)
        activable_consumers = get_activable_consumers(consumers, battery_level)
        
        if activable_consumers:
            # send_activable_consumers(activable_consumers)
            print(activable_consumers, flush=True)
        
        time.sleep(1)
