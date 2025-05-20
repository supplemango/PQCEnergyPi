"""
Module Name: experimenter.py

Author: Cameron Patterson
Date Created: 2023-04-01
Last Updated: 2023-05-07
Version: 8

Description:
------------
This is a python script/program which kicks off an openssl key generation experiment for the pre-requisite number of iterations.
It takes a number of command line arguments, about the algorithm and how many times a key should be generated as well as the IP/port# of the data collector.
Around this experiment, it signals the collector over UDP to GETREADY, and when the experiment STARTs and STOPs, and which collection parameters to use.
It sets a stable environment, with fan at 100% and CPU pinned to avoid and DVFS where possible.
   ...  e.g. use:  python experimenter.py --algorithm 'EC -pkeyopt ec_paramgen_curve:secp160r1' --sample_period 0.5 --iterations 100000 --host 192.168.5.59 --port 65432

Notable Dependencies:
---------------------
OpenSSL3.5

Usage (from --help):
--------------------
usage: experimenter.py [-h] [--iterations ITERATIONS] [--tcp] [--host HOST] [--port PORT] [--sample_period PERIOD] [--experiment_id TEXT]
                       [--algorithm {ML-DSA-44,ML-DSA-65,ML-DSA-87,ML-KEM-512,ML-KEM-768,ML-KEM-1024}]
options:
  -h, --help            show this help message and exit
  --iterations          how many times the key generation should be run for this experiment, (default=1000)
  --tcp                 ** FUTURE USE - NOT IMPLEMENTED ** Use TCP instead of UDP for communication TODO
  --host HOST           IP address of the Windows Measurement Machine (default=192.168.5.59)
  --port PORT           Port number for communication to the measurement machine (default=65432)
  --algorithm           Cryptographic algorithm to use as OpenSSL option {ML-DSA-44,ML-DSA-65,ML-DSA-87,ML-KEM-512,ML-KEM-768,ML-KEM-1024} (default=ML-KEM-1024)
  --sample_period       This is how often the collector should collect the data from 0.1 to 1.0 seconds in tenth of a second increments (default is 1.0)
  --experiment_id       This is transferred to the collector a user defined field about the test, if defaulted it is algorimically generated from date, algorithm and iterations

Notes/TODOs: 
------------
Send parameters of time and temperature over to the collector, can extend the dictionary to add more as required in future.
TODO: TCP mode not implemented - UDP is better for energy and latency, network is reliable back-to-back, so not yet complete
    TCP could also be a blocker, as need the 3-way handshake so would block the experiement if the other end isn't ready.

"""


import subprocess
import time
import socket
import argparse
import sys
import json
from datetime import datetime
import re  # For regular expressions for parsing

# --- Command Line Parsing Stuff ---

parser = argparse.ArgumentParser(
    description="Raspberry Pi control script for experiment."
)
parser.add_argument(
    "--iterations",
    "-i",
    help="Number of iterations for the experiment (default=1000)",
    dest="iterations",
    action="store",
    type=int,
    default=1000,
)
parser.add_argument(
    "--tcp",
    dest="use_tcp",
    action="store_true",
    help="Use TCP instead of UDP for communication (not yet functional DONOTUSE)",
    default=False,
)
# TODO - write a receiver on UDP, then then flips to TCP if required, or open 2 ports (wasteful), just use UDP for now
parser.add_argument(
    "--host",
    dest="host",
    action="store",
    type=str,
    default="192.168.5.59",
    help="IP address of the Windows Measurement Machine (default=192.168.5.59)",
)
parser.add_argument(
    "--port",
    dest="port",
    action="store",
    type=int,
    default=65432,
    help="Port number for communication (default=65432)",
)
parser.add_argument(
    "--algorithm",
    dest="algorithm",
    action="store",
    type=str,
    default="ML-KEM-1024",
    choices=[
        "NULL",
        "NULLNoLoop",
        "ML-DSA-44",
        "ML-DSA-65",
        "ML-DSA-87",
        "ML-KEM-512",
        "ML-KEM-768",
        "ML-KEM-1024",
        "RSA -pkeyopt rsa_keygen_bits:1024",
        "RSA -pkeyopt rsa_keygen_bits:1536",
        "RSA -pkeyopt rsa_keygen_bits:2048",
        "RSA -pkeyopt rsa_keygen_bits:3072",
        "RSA -pkeyopt rsa_keygen_bits:4096",
        "EC -pkeyopt ec_paramgen_curve:secp160r1",
        "EC -pkeyopt ec_paramgen_curve:secp224r1",
        "EC -pkeyopt ec_paramgen_curve:P-256",
        "EC -pkeyopt ec_paramgen_curve:P-384",
        "EC -pkeyopt ec_paramgen_curve:P-521",
        "XXXX",
    ],
    help='Cryptographic algorithm to use (default=ML-KEM-1024). Use "NULL" for a no-op test.',
)
parser.add_argument(
    "--experiment_id",
    dest="experiment_id",
    action="store",
    type=str,
    default=None,  # Default is now None
    help='Identifier for the experiment (default is "yyyymmddhhmmss,Algorithm,Iterations")',
)
parser.add_argument(
    "--sample_period",
    dest="sample_period",
    action="store",
    type=float,
    default=1.0,
    choices=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    help="Sampling period in seconds for data collection on Windows (0.1 to 1.0 in 0.1s increments, default=1.0)",
)


# --- Proc to Executes a shell command and handles errors. ---

def run_command(command): 
    try:
        result = subprocess.run(
            ["bash", "-c", command], check=True, capture_output=True, text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command '{command}': {e.stderr}")
        sys.exit(1)



# --- Sends a message to the Windows Measurement Machine with a defined message - needs to be coordinated with collector for parsing. NOTE: TCP not functional: vestiges remain ---

def send_message(message, host, port, use_tcp):
    try:
        if use_tcp:
            sock_type = socket.SOCK_STREAM
        else:
            sock_type = socket.SOCK_DGRAM

        with socket.socket(socket.AF_INET, sock_type) as s:
            if use_tcp:
                s.connect((host, port))
                s.sendall(message.encode())
                print(
                    f"TCP: Sent '{message}' to Windows Measurement Machine ({host}:{port})"
                )
            else:
                s.sendto(message.encode(), (host, port))
                print(
                    f"UDP: Sent '{message}' to Windows Measurement Machine ({host}:{port})"
                )

    except socket.gaierror as e:
        print(f"Error: Address-related error: {e}")
        sys.exit(1)
    except socket.timeout as e:
        print(f"Error: Connection timed out: {e}")
        sys.exit(1)
    except socket.error as e:
        print(f"Error sending message: {e}")
        sys.exit(1)




# --- Main funtion, start here ---

if __name__ == "__main__":
    null_sleep_time = 0.005  # to give measureable background energy and not be optimised out by compiler for NULL tests (time not really relevant as asleep, but set to match default algo approx.)
    arg = parser.parse_args()

    # Generate default experiment_id if not provided (haven't really been using this to be honest, but it's there)
    if arg.experiment_id is None:
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        arg.experiment_id = f"{now}-{arg.algorithm}-{arg.iterations}"

    # Create the parameters dictionary to go over to the Collector so it know the parameters of the experiment
    experiment_params = {
        "iterations": arg.iterations,
        "algorithm": arg.algorithm,
        "experiment_id": arg.experiment_id,
        "sample_period": arg.sample_period,
    }

    # Send the GETREADY message with parameters as a JSON string
    getready_message = f"GETREADY {json.dumps(experiment_params)}"
    send_message(getready_message, host=arg.host, port=arg.port, use_tcp=arg.use_tcp)

    # Setup Phase
    print(f"Starting experiment: {arg.experiment_id}")
    print(
        "Setting up environment on the Device Under Test (DUT), setting fan and CPU to max"
    )

    # the below sets up the CPU frequency to be pinned at the highest frequency, and not dynamically scale up and down - for experimental consistency
    run_command(
        "sudo sh -c 'echo performance > /sys/devices/system/cpu/cpufreq/policy0/scaling_governor'"
    )

    # the below command sets the fan to be 100% (to keep the CPU cool while it keygens), and gives it a few secs to spin up and settle
    run_command("pinctrl FAN_PWM op dl")
    time.sleep(3)

    # note the temp of the CPU at the start (for interest, passed to screen/collector)
    StartTemperature = run_command("cat /sys/class/thermal/thermal_zone0/temp")
    print(f"Start Temperature: {float(StartTemperature) / 1000.0:.2f} C")

    # Run the Experiment Phase - send message to collector to say to start collecting data, and capture the timings locally
    send_message("START", host=arg.host, port=arg.port, use_tcp=arg.use_tcp)
    experiment_start_time = time.monotonic()

    if arg.algorithm == "NULL":
        print(f"STARTing NULL experiment with {arg.iterations} iterations")
        for _ in range(arg.iterations):
            time.sleep(null_sleep_time)  # Sleep for null_sleep_time milliseconds (so loop isn't optimised out)
    elif arg.algorithm == "NULLNoLoop":
        time.sleep(
            arg.iterations * null_sleep_time
        )  # sleep but without doing the loops - multiply out the time so about the same - might be of interest...
        # likely to be close to NULL, but worth a rate check.
        #   will add this rate to match total exe time and underlying Energy in J
        #   We could then subtract this from the Energy of a test to get true EXTRA energy
        #    but loops are stull run, so this is probably not as good a measure/subtraction than the NULL option
    else:
        experiment_command = f"time bash -c 'for ((i=0; i<{arg.iterations}; i++)); do openssl genpkey -algorithm {arg.algorithm} > /dev/null; done'"
        print(
            f"STARTing experiment with {arg.iterations} iterations and algorithm {arg.algorithm}"
        )
        run_command(experiment_command)
        # this runs the experiment for the prerequistite number of times, output is dropped to dev/null for all experiements consistently

    experiment_end_time = time.monotonic()
    experiment_duration = experiment_end_time - experiment_start_time
    # note how long the experiment took to run on wall clock time

    # End Experiment Phase
    StopTemperature = run_command("cat /sys/class/thermal/thermal_zone0/temp")
    print("Experiment finished")

    experiment_data = {
        "time_to_run": experiment_duration,
        "start_temperature": float(StartTemperature) / 1000.0,
        "stop_temperature": float(StopTemperature) / 1000.0,
    }

    stop_message = f"STOP {json.dumps(experiment_data)}"

    send_message(stop_message, host=arg.host, port=arg.port, use_tcp=arg.use_tcp)
    # data about experiement length and begin/end CPU temperatures sent to the collector as part of the STOP message to stop energy data gathering

    print(f"Time to run on Pi: {experiment_duration:.2f} seconds")
    print(f"Start Temperature: {float(StartTemperature) / 1000.0:.2f} C")
    print(f"Stop Temperature: {float(StopTemperature) / 1000.0:.2f} C")
    # keep the user informed (outside the experiment so not influencing energy data)

    # Reset Parameters Phase
    run_command("pinctrl FAN_PWM a0")
    run_command(
        "sudo sh -c 'echo ondemand > /sys/devices/system/cpu/cpufreq/policy0/scaling_governor'"
    )
    print("Environment on Device Under Test (DUT) defaulted")
    # we drop the CPU fan and frequency scaling back to default


# END CODE
