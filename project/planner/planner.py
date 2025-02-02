import json
import os
from bottle import Bottle, request, run, HTTPResponse
import requests

# Debug mechanism based on environment variable
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

def debug_print(msg):
    if DEBUG:
        print(msg, flush=True)

# Executor API configuration using environment variable
EXECUTOR_API = os.getenv("EXECUTOR_API", "http://executor:8081")

class Planner:
    """
    Handles the logic for deciding which consumers to activate
    based on battery level, urgency, and other constraints,
    and sends commands to the Executor API.
    """
    def __init__(self, executor_api: str):
        self.executor_api = executor_api

    def choose_consumers(self, data: dict) -> dict:
        """
        Determines which consumers to activate based on:
          - battery level,
          - urgency (isUrgent),
          - difference (delta - tau).
        :param data: JSON data from the request.
        :return: Dictionary of activable consumers grouped by member.
        """
        battery_level = data['battery']  # Battery in kWh
        members = data['members']
        activable = {}

        for member_id, consumers in members.items():
            # Separate urgent consumers from non-urgent consumers
            urgent_consumers = [consumer for consumer in consumers if consumer.get('isUrgent')]
            non_urgent_consumers = [consumer for consumer in consumers if not consumer.get('isUrgent')]

            # Sort urgent consumers by (delta - tau) (tighter schedules are processed first)
            urgent_consumers.sort(key=lambda c: c['delta'] - c['tau'])
            # Also sort non-urgent consumers
            non_urgent_consumers.sort(key=lambda c: c['delta'] - c['tau'])

            activable[member_id] = []

            # Process urgent consumers first (regardless of battery level)
            for consumer in urgent_consumers:
                activable[member_id].append({
                    "consumer_id": consumer["consumer_id"],
                    "action": "activate"
                })
                battery_level -= consumer['cons_required']

            # Then process non-urgent consumers if battery is sufficient
            for consumer in non_urgent_consumers:
                if consumer['cons_required'] <= battery_level:
                    activable[member_id].append({
                        "consumer_id": consumer["consumer_id"],
                        "action": "activate"
                    })
                    battery_level -= consumer['cons_required']

        debug_print(f"DEBUG: Activable consumers determined: {activable}")
        return activable

    def send_to_executor(self, activable_consumers: dict) -> None:
        """
        Sends the activable consumers to the Executor via an HTTP request.
        :param activable_consumers: Dictionary of activable consumers grouped by member.
        """
        url = f"{self.executor_api}/commands"
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(url, headers=headers, json=activable_consumers)
            if response.status_code == 200:
                print("INFO: Commands successfully sent to the executor.", flush=True)
            else:
                print(f"ERROR: Failed to send commands to the executor. Status code: {response.status_code}", flush=True)
        except Exception as e:
            print(f"ERROR: Error sending commands to the executor: {e}", flush=True)

    def process_request(self, data: dict) -> (int, dict):
        """
        Processes the incoming request, validates the data,
        determines the activable consumers, and sends the commands.
        :param data: JSON data from the request.
        :return: A tuple (status_code, response_body).
        """
        print(f"INFO: Received activable consumers request: {data}", flush=True)

        # Validate incoming data
        if not data or 'members' not in data or 'battery' not in data:
            return 400, {"error": "Invalid input data"}

        activable = self.choose_consumers(data)

        if any(activable.values()):
            self.send_to_executor(activable)
            return 200, {"status": "success", "activable": activable}
        else:
            return 200, {"status": "no consumers activated"}

class APIManager:
    """
    Manages the API exposed via Bottle.
    Configures routes and forwards requests to the Planner.
    """
    def __init__(self, planner: Planner):
        self.planner = planner
        self.app = Bottle()
        self.setup_routes()

    def setup_routes(self) -> None:
        @self.app.post('/activable_consumers')
        def activable_consumers():
            try:
                data = request.json
                status_code, response_body = self.planner.process_request(data)
                return HTTPResponse(
                    body=json.dumps(response_body),
                    status=status_code,
                    headers={"Content-Type": "application/json"}
                )
            except Exception as e:
                print(f"ERROR: Error processing request: {e}", flush=True)
                return HTTPResponse(
                    body=json.dumps({"error": str(e)}),
                    status=500,
                    headers={"Content-Type": "application/json"}
                )

    def run(self) -> None:
        run(self.app, host="0.0.0.0", port=8080)

if __name__ == "__main__":
    planner = Planner(EXECUTOR_API)
    api_manager = APIManager(planner)
    api_manager.run()
