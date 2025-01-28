import random
import json
import time
import threading
from flask import Flask, request, jsonify
import paho.mqtt.client as mqtt

def generate_tau_delta_in_minutes():
    tau = random.randint(1, 5)
    delta = random.randint(tau + 1, int((tau+1)*1.5))
    
    return tau * 60, delta * 60 

def generate_production():
    return random.uniform(0, 1)

def load_sensor_config() -> dict:
    with open('config/REC.json', 'r') as file:
        config = json.load(file)
        
    # Initialize tau and delta for each consumer
    for member in config["members"]:
        for consumer_id in config["members"][member]["consumers"]:
            config["members"][member]["consumers"][consumer_id]["tau"] = 0
            config["members"][member]["consumers"][consumer_id]["delta"] = 0
            config["members"][member]["consumers"][consumer_id]["activated"] = False
            
    return config["members"], config["battery"]

def publish_tau_delta(cons_id, member_id, tau, delta, cons, activated, timestamp):
    message = f"tau_delta,consumer_id={cons_id},member_id={member_id},cons={cons} active={activated},tau={tau},delta={delta} {timestamp}"
    client.publish(TAUDELTA_TOPIC_STRUCTURE.format(member_id=member_id, cons_id=cons_id), message)
    
def publish_production(member_id, prod_id, production, timestamp):
    message = f"production,producer_id={prod_id},member_id={member_id} value={production} {timestamp}"
    client.publish(PROD_TOPIC_STRUCTURE.format(member_id=member_id, prod_id=prod_id), message)
    
def publish_battery(max_battery, battery_value, timestamp):
    message = f"battery,max_value={max_battery} value={battery_value} {timestamp}"
    client.publish(BATTERY_TOPIC_STRUCTURE, message)

# MQTT broker configuration
BROKER = "broker"  # Service name in docker-compose.yml
PORT = 1883
PROD_TOPIC_STRUCTURE = "/producer/{member_id}/{prod_id}"  
TAUDELTA_TOPIC_STRUCTURE = "/consumer/taudelta/{member_id}/{cons_id}" 
BATTERY_TOPIC_STRUCTURE = "/battery"

# Let's assume that every step of simulation (one second) is a minute in real life
STEP_DURATION = 1 # seconds
SECONDS_IN_A_SIMULATION_STEP = 60
MINUTES_IN_A_SIMULATION_STEP = SECONDS_IN_A_SIMULATION_STEP / 60
HOURS_IN_A_SIMULATION_STEP = MINUTES_IN_A_SIMULATION_STEP / 60

TAU_DELTA_INTERVAL_BOUNDS = (60, 90)

# API for aligning tau and delta with dashboard inserts
app = Flask(__name__)

@app.route('/update_tau_delta', methods=['POST'])
def update_tau_delta():
    data = request.json
    member_id = data['member_id']
    consumer_id = data['consumer_id']
    tau = data['tau']
    delta = data['delta']
    
    if member_id in members and consumer_id in members[member_id]["consumers"]:
        members[member_id]["consumers"][consumer_id]["tau"] = tau
        members[member_id]["consumers"][consumer_id]["delta"] = delta
        members[member_id]["consumers"][consumer_id]["activated"] = False
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"status": "error", "message": "Invalid member_id or consumer_id"}), 400

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200

def run_api():
    app.run(host="0.0.0.0", port=5000)
    
if __name__ == '__main__':
    api_thread = threading.Thread(target=run_api)
    api_thread.daemon = True
    api_thread.start()
                
    client = mqtt.Client("sensors")
    client.connect(BROKER, PORT)
    
    members, battery_info = load_sensor_config()
    
    i = -1
    # Generate a random tau, delta every 60-90 steps
    interval = random.randint(*TAU_DELTA_INTERVAL_BOUNDS)
    
    battery_value = 0
    while True:
        timestamp = int(time.time() * 1e9)  # Convert to nanoseconds for InfluxDB line protocol
        
        battery_delta = 0
        # Generate production values for each producer in each member every second (minute in real life) 
        for member in members:
            for producer_id, producer_data in members[member]["producers"].items():
                # Simulate average immediate production (production for each second) and calculate the production in a step in kWh
                average_immediate_production = float(producer_data["max-pi"]) * generate_production() 
                production = average_immediate_production * HOURS_IN_A_SIMULATION_STEP # Convert to kWh
                battery_delta += production
                
                # Publish the production value
                publish_production(member, producer_id, production, timestamp)
                
            for consumer_id, consumer_data in members[member]["consumers"].items():
                # Simulate the time passing for delta
                if consumer_data["delta"] != 0:
                    consumer_data["delta"] -= MINUTES_IN_A_SIMULATION_STEP
                    
                    # TODO replace this random with a reading from actuators
                    # if not consumer_data["activated"]:
                    #     probability = max(0.001, 1 - abs(consumer_data["delta"] - consumer_data["tau"]) / consumer_data["tau"])
                    #     if random.uniform(0, 1) < probability:
                    #         consumer_data["activated"] = True
                    #         print(f"Consumer {consumer_id} in member {member} activated", flush=True)
                    
                if consumer_data["activated"]:
                    consumer_data["tau"] -= MINUTES_IN_A_SIMULATION_STEP
                    if consumer_data["tau"] == 0:
                        consumer_data["activated"] = False
                        consumer_data["delta"] = 0
                        
                    battery_delta -= consumer_data["cons"] * HOURS_IN_A_SIMULATION_STEP
                        
                publish_tau_delta(consumer_id, member, consumer_data["tau"], consumer_data["delta"], consumer_data["cons"], consumer_data["activated"], timestamp)
            
        battery_value = max(min(battery_value + battery_delta, battery_info["max-capacity"]), 0)
        # Publish the battery delta
        publish_battery(battery_info["max-capacity"], battery_value, timestamp)
                
                
                
        
        # Each interval, generate a tau and delta value for a random consumer and publish it
        if i == interval or i == -1:
            member_id = random.choice(list(members.keys()))
            member = members[member_id]
            
            
            unassigned_consumers = [cid for cid, cdata in member["consumers"].items() if cdata["tau"] == 0 and cdata["delta"] == 0]
            if unassigned_consumers:
                
                consumer_id = random.choice(unassigned_consumers)

                tau, delta = generate_tau_delta_in_minutes()
                publish_tau_delta(consumer_id, member_id, tau, delta, member["consumers"][consumer_id]["cons"], member["consumers"][consumer_id]["activated"], timestamp)
                
                # Update the configuration
                members[member_id]["consumers"][consumer_id]["tau"] = tau
                members[member_id]["consumers"][consumer_id]["delta"] = delta
            
                

                
            i = 0
            interval = random.randint(*TAU_DELTA_INTERVAL_BOUNDS)
        
        i += 1
        time.sleep(STEP_DURATION)


