import random
import json
import time
import paho.mqtt.client as mqtt

def generate_tau_delta_in_minutes():
    tau = random.randint(1, 5)
    delta = random.randint(tau, 10)
    
    return tau * 60, delta * 60 

def generate_production():
    return random.uniform(0, 1)

def load_sensor_config() -> dict:
    with open('config/REC.json', 'r') as file:
        config = json.load(file)
    return config["REC"]

# Configurazione del broker MQTT
BROKER = "broker"  # Nome del servizio nel docker-compose.yml
PORT = 1883
PROD_TOPIC_STRUCTURE = "/producer/{member_id}/{prod_id}"  
TAUDELTA_TOPIC_STRUCTURE = "/consumer/taudelta/{member_id}/{cons_id}" 

# Let's assume that every step of simulation (one second) is a minute in real life
STEP_DURATION = 1 # seconds
SECONDS_IN_A_SIMULATION_STEP = 60

TAU_DELTA_INTERVAL_BOUNDS = (45, 90)

if __name__ == '__main__':
    client = mqtt.Client("sensors")
    client.connect(BROKER, PORT)
    
    rec = load_sensor_config()
    
    i = 0
    # Generate a random tau, delta every 60-90 steps
    interval = random.randint(**TAU_DELTA_INTERVAL_BOUNDS)
    
    while True:
        timestamp = int(time.time() * 1e9)  # Convert to nanoseconds for InfluxDB line protocol
        
        # Generate production values for each producer in each member every second (minute in real life) 
        for member in rec:
            for producer_id, producer_data in rec[member]["producers"].items():
                # Simulate average immediate production (production for each second) and calculate the production in a step in kWh
                average_immediate_production = float(producer_data["max-pi"]) * generate_production() 
                production = average_immediate_production * (SECONDS_IN_A_SIMULATION_STEP / 3600) # Convert to kWh
                
                # Publish the production value
                topic = PROD_TOPIC_STRUCTURE.format(member_id=member, prod_id=producer_id)
                message = f"production,producer_id={producer_id},member_id={member} value={production} {timestamp}"
                client.publish(topic, message)
                
        
        # Each interval, generate a tau and delta value for a random consumer and publish it
        if i == interval:
            member_id = random.choice(list(rec.keys()))
            member = rec[member_id]
            
            consumer_id = random.choice(list(member["consumers"].keys()))

            tau, delta = generate_tau_delta_in_minutes()
            topic = TAUDELTA_TOPIC_STRUCTURE.format(member_id=member_id, cons_id=consumer_id)
            
            message = f"tau_delta,consumer_id={consumer_id},member_id={member_id} tau={tau},delta={delta} {timestamp}"
            client.publish(topic, message)
            
            i = 0
            interval = random.randint(**TAU_DELTA_INTERVAL_BOUNDS)
        
        i += 1
        time.sleep(STEP_DURATION)
            
            
            