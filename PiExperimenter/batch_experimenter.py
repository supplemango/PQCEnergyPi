"""
Module Name: batch_experimenter.py

Author: Cameron Patterson
Date Created: 2023-04-01
Last Updated: 2023-05-07
Version: 5

Description:
------------
This is a python script/program which batches together multiple experiments on the collecting device for Cameron Patterson's CS11131 coursework.
It's purpose is to read an input file, specified at the command-line and use the parameters in it to send to the experiment.py script
    It also should handle some of the common errors that might be seen along the way.
This is quite a simple script. The source parameter file has 2 comma separated values, the OpenSSL keyget argument, iteration count. e.g.
        EC -pkeyopt ec_paramgen_curve:secp224r1,100000
        NULL,100000
        ML-KEM-512,100000
        RSA -pkeyopt rsa_keygen_bits:3072,500
    The first section is effecively the argument for OpenSSL to generate that key, then the number of iterations to be performed of it.
        NULL is an option to run everything except a keygen for benchmarking.
        Larger RSA keys take a long time, so iterations are typically scaled down compared with the others

When the end of the CSV is detected the scripts exits and prints a message to the user on the console.

   ... e.g.  python .\batch_experimenter.py --host 22.33.44.55 10kSourceRSAscaled.csv  # Use this parameter file and signal this collector IP.


Notable Dependencies:
---------------------
csv - to read from a file formatted using comma sepearated values

Usage (from --help):
--------------------
usage: batch_experimenter.py [-h] [--iterations ITERATIONS] [--sample_period SAMPLE_PERIOD] [--host HOST] [--port PORT] parameter_file

--iterations this optional argument allows the user to override the iteration count from the parameter_file (useful for short test verification)
--sample_period - this sets how often the collector will poll results from the test meter.(e.g. 0.1 is 10Hz,  1 is 1Hz)  - defaults to 0.5 secs.
   In shorter experiements this should be lower to ensure that when the experiment stops a recent final value is used
   For longer experiments then this becomes less significant compared with total experiment time
   This is also how often the live screen is updated on the collector station so the user can keep track
--host - to use a different collector station host IP address from the default below `default_host'
--port - similarly to use a different port number (note: no command line option for TCP as we are defaulting to UDP)
parameter_file - this is the source information for the experiments, 1 line per experiment in CSV file of format. See explanation above

Notes/TODOs: 
------------
Open CSV formatted file (doesn't need .csv actually) in read only, line by line igoring blanks now.
Set up iterations so if specified at CLI overrides entry in file field 2, and if no entry in field 2 of source, then fall-back to default
TODO: TCP mode not implemented - UDP is better for energy and latency, network is reliable back-to-back, so not yet complete

"""


import subprocess
import time
import csv
import argparse

# Parameters (some are defaults if not overridden by command line)
cooldown_pause = 15  # wait this many seconds between experiment runs in the batch (gives time for collector to restart too)
default_iterations = 10
default_sample_period = 0.5
default_host = "192.168.5.59"
default_port = 65432


# --- Run the experiment - call the experimenter.py script from the current directory passing through parameters ---

def run_experiment(algorithm, iterations, sample_period, host, port):
    # Runs the experiment with the given algorithm.
    command = f"python experimenter.py --algorithm '{algorithm}' --sample_period {sample_period} --iterations {iterations} --host {host} --port {port}"
    print(f"Running: {command}")  # keep the user updated, but outside the test itself so not influencing
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running experiment with algorithm '{algorithm}': {e}")



# --- Main funtion, start here ---

def main():
    parser = argparse.ArgumentParser(
        description="Pi batch script for running Cammy's keygen experiments."
    )
    parser.add_argument(
        "parameter_file", help="CSV file containing algorithm parameters."
    )
    parser.add_argument(
        "--iterations",
        "-i",
        type=int,
        default=None,
        help=f"Override iterations for all experiments",
    )
    parser.add_argument(
        "--sample_period",
        "-sp",
        type=float,
        default=default_sample_period,
        help=f"Sampling period (default: {default_sample_period})",
    )
    parser.add_argument(
        "--host",
        "-ho",
        type=str,
        default=default_host,
        help=f"Host IP address (default: {default_host})",
    )
    parser.add_argument(
        "--port",
        "-po",
        type=int,
        default=default_port,
        help=f"Port number (default: {default_port})",
    )
    args = parser.parse_args()

    try:
        with open(args.parameter_file, "r") as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                # print(f"DEBUG: Raw row from CSV: {row}")  # Debug print
                if row:  # Check if the row is not empty
                    algorithm = row[0].strip()  # Get algorithm from the first element
                    iterations_from_file = None
                    iterations_source = (
                        "(code default)"  # Initialize iterations_source here
                    )
                    if len(row) >= 2:  # Check if there's a second element (iterations)
                        try:
                            iterations_from_file = int(
                                row[1].strip()
                            )  # Get iterations from the second element
                            iterations_source = "(parameters file)"
                            # print(f"DEBUG: Iterations from file (attempted): {iterations_from_file}")  # Debug print
                        except ValueError:
                            print(
                                f"Note: Invalid iterations value '{row[1]}' for algorithm '{algorithm}'. Using default: {default_iterations}"
                            )
                            iterations_from_file = default_iterations

                    if algorithm:  # Check if the algorithm entry is not empty
                        iterations_to_use = (
                            args.iterations
                            if args.iterations is not None
                            else (
                                iterations_from_file
                                if iterations_from_file is not None
                                else default_iterations
                            )
                        )
                        if args.iterations:
                            iterations_source = "(CLI argument)"
                        # print(f"DEBUG: Iterations to use: {iterations_to_use}")  # Debug print
                        print(
                            f"\n\nDetected algorithm: {algorithm}, Iterations: {iterations_to_use} {iterations_source}"
                        )
                        # print where we got our count from as it can come for 3 places: hard_coded, CLI argument, source csv itself

                        run_experiment(
                            algorithm,
                            iterations_to_use,
                            args.sample_period,
                            args.host,
                            args.port,
                        )
                        print(
                            f"Experiment with algorithm '{algorithm}' and {iterations_to_use} iterations completed. Pausing for {cooldown_pause} seconds to cool/synch..."
                        )
                        time.sleep(cooldown_pause)
                    else:
                        print("Note: Skipping line with no algorithm data.")
                else:
                    print("Note: Skipping blank line in parameter file.")
        print("\nNote: Parameter file processing completed.")
    except FileNotFoundError:
        print(f"Error: Parameter file '{args.parameter_file}' not found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    
    # at the end of the day - keep the user updated with message to screen (only outside experiment, non influencing)

if __name__ == "__main__":
    main()

# END CODE
