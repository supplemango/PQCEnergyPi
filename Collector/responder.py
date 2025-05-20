"""
Module Name: responder.py

Author: Cameron Patterson,  incorporating library code to handle the TC66C from TheHWCave - details/license below.
Date Created: 2023-04-01
Last Updated: 2023-05-10
Version: 6.14

Description:
------------
** Ensure the Power and PD switches on the TC66 meter are turned OFF before testing **

This is a python script/program which runs on the collecting device for Cameron Patterson's CS11131 coursework.
It's purpose is to set up a connection to the TC66C device on a USB/virtual serial port from where:
    Using an additional thread it periodically polls instantaneous measured voltage, current and power information from the meter...
        ... It also collects cumulative information such as the energy used in mWh which is gathered to determine energy used.
It sets up another thread to listen for network messages (the device under test will send control messages like:
    GETREADY, START and STOP gathering data from the control channel.
The data from the meter is written to 2 files, a detailed one for each experiment, and another to an existing log, in summary:
    1)  e.g. '20250426095115-ML-KEM-512-500000_data.csv'  this has all data in it + a header row in CSV format. 
        The filename starts with a ISO date and time (sortable), Here this is 26th April 2025 starting at 09:51:15
        It contrains data from the experiment using cryptographic algorithm ML-KEM-512, run over half a million iterations.
        A new row is created for each iteration (e.g. every 0.1s or 0.5s depending on the parameter provided to the device on test)
        This has timestamps, algo, Optional User-defined experiment ID, sample period, cumulative Joules (calculated)...
            ...and from the meter: instantaneous Volts, Current, Power, Resist, 2x cumulative mWh, TC66c temp etc.
    2) `AllResults.csv' this has a single line entry added for each experiment run, an Experiment summary...
        Timestamp, Iteration, Algorithm, TotalJ recorded between START and STOP, Time between, Rates: calculated J and time per 1000 keygens
When Stop is received, files and sockets are closed down and this script ends. For batch testing, just loop me in shell...
   ... e.g.  while ($true) { python .\responder.py --com COM5 }     # Ctrl+C once all experiments are complete.

Notable Dependencies:
---------------------
pyserial, pycryptodome

Usage (from --help):
--------------------
usage: responder.py [-h] [--com COM_PORT] [--nonet-startdelay SECONDS] [--nonet-duration SECONDS]
   --com as above if specified bypasses interactive user selection

Notes/TODOs: 
------------
In Version 6.14 added in --nonet-startdelay and --nonet-duration options, to allow recording to start without GETREADY, START, and STOP messages.
Included licence notice from TheHWCave library below this section
Started collecting data from G0 and G1 channels as seems to flip flop between (1-at-a-time so aggregating both)
Sanity Check added - error checking on input data - if see a negative Joules then corruption on serial connection so ignore
GatherErrorCount printed - notes on screen to user as part of live update the number of such glitch/errors to see if endemic
Set Allresults.csv to RO unless being written, if user opens files/leaves it open - this stops log being updated = bad.
TODO: TCP mode not implemented - UDP is better for energy and latency, network is reliable back-to-back, so not yet complete
TODO: Code is monolitic, simple, but may in future be better be split up

"""

# Includes Code from HWCave for the Ruideng RDTech TC66[c] https://github.com/TheHWcave/TC66/tree/main
# Data recovery from the TC66C energy meter is based on work by theHWcave and subject to Licence from TheHWcave Code which is used...
#
# MIT License
#
# Copyright (c) 2022 TheHWcave
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
#
#

import os
import stat
import struct
import socket
import threading
import json
import time
from datetime import datetime
import sys
import argparse
import serial
import serial.tools.list_ports
import platform  # To detect the operating system
import math
from Crypto.Cipher import AES
from collections import namedtuple

# --- Global Variables ---
experiment_params = {}  #comes from device doing testing as part of the packet
output_file = None  # gets generated
running = False
master_output_file = None
data_thread = None
network_thread = None
stop_event = threading.Event()
com_port_override = False  # Flag to track if COM port was overridden
tc66c_instance = None  # Initialise TC66C instance
first_reading_time = None
last_reading_time = None
first_mWh = None
last_mWh = None
total_joules = 0.0
stop_data = {}  # Initialise stop_data
previous_joules = None  # To track previous Joules value
GatherErrorCount = 0  # capture how may misreads from the TC66 channel are detected in the run


# --- Configuration ---
HOST = "0.0.0.0"  # Listen on all available interfaces
PORT = 65432  # have just hard coded this used for UDP or TCP (although TCP is not implemented - just a vestige)
TCP_MODE = False  # Default to UDP, will be updated based on Pi's setting (in GETREADY) - TODO - not implemented
com_port = "COM5"  # Default COM port, if user choice times out it uses this, user can override as command line argument
master_filename = f"AllResults.csv"  #we want this to be the same every time as cumulative 1 line per experiment


# --- TC66C Class (Extracted + Adapted from 3rd party code, licence and links above)
class TC66C:
    _SIF: None
    _AES: None

    PollData = namedtuple(
        "PollData",
        [
            "Name",
            "Version",
            "SN",
            "Runs",
            "Volt",
            "Current",
            "Power",
            "Resistance",
            "G0_mAh",
            "G0_mWh",
            "G1_mAh",
            "G1_mWh",
            "Temp",
            "D_plus",
            "D_minus",
        ],
    )

    RecData = namedtuple("RecData", ["Volt", "Current"])

    def __init__(self, port_dev=None):
        STATIC_KEY = [
            0x58,
            0x21,
            0xFA,
            0x56,
            0x01,
            0xB2,
            0xF0,
            0x26,
            0x87,
            0xFF,
            0x12,
            0x04,
            0x62,
            0x2A,
            0x4F,
            0xB0,
            0x86,
            0xF4,
            0x02,
            0x60,
            0x81,
            0x6F,
            0x9A,
            0x0B,
            0xA7,
            0xF1,
            0x06,
            0x61,
            0x9A,
            0xB8,
            0x72,
            0x88,
        ]

        if port_dev is None:
            port_dev = com_port
        try:
            self._SIF = serial.Serial(
                port=port_dev,
                baudrate=115200,
                bytesize=8,
                parity="N",
                stopbits=2,
                xonxoff=0,
                rtscts=0,
                dsrdtr=1,
                timeout=5,
            )
            time.sleep(1.0)
        except serial.SerialException as e:
            print("failed to open:" + port_dev)
            print(e)
            sys.exit(1)

        self._AES = AES.new(bytes(STATIC_KEY), AES.MODE_ECB)

    def Poll(self):
        """
        Polls the TC66C for new data and returns it in form of
        a PollData record

        The data comes in a 192 byte package AES encrypted
        """
        if not self._SIF.isOpen():
            self._SIF.open()
        self.SendCmd("getva")

        buf = self._SIF.read(192)
        try:
            data = self._AES.decrypt(buf)
        except Exception as e:
            print("decrypt error")
            return None

        pac1 = struct.unpack("<4s4s4s13I", data[0:64])
        pac2 = struct.unpack("<4s15I", data[64:128])
        pac3 = struct.unpack("<4s15I", data[128:192])

        if pac2[6] == 1:
            tsign = -1
        else:
            tsign = 1

        pd = self.PollData(
            Name=pac1[1].decode(),
            Version=pac1[2].decode(),
            SN=pac1[3],
            Runs=pac1[11],
            Volt=float(pac1[12]) * 1e-4,
            Current=float(pac1[13]) * 1e-5,
            Power=float(pac1[14]) * 1e-4,
            Resistance=float(pac2[1]) * 1e-1,
            G0_mAh=pac2[2],
            G0_mWh=pac2[3],
            G1_mAh=pac2[4],
            G1_mWh=pac2[5],
            Temp=pac2[7] * tsign,
            D_plus=float(pac2[8]) * 1e-2,
            D_minus=float(pac2[9]) * 1e-2,
        )

        return pd

    def GetRec(self):
        """
        Fetches the complete used recording buffer (up to 1440 entries)
        from the TC66C and returns it in from of a list of RecData
        Each RecData entry is a Volt , Current pair
        """
        rd = []
        if not self._SIF.isOpen():
            self._SIF.open()
        self.SendCmd("gtrec")
        rec = bytearray()
        while True:
            buf = self._SIF.read(8)

            if len(buf) == 0:
                break
            rec.extend(buf)
            if len(rec) >= 8:
                r = struct.unpack("<2I", rec[0:8])
                rd_entry = self.RecData(
                    Volt=float(r[0]) * 1e-4, Current=float(r[1]) * 1e-5
                )
                rd.append(rd_entry)
                rec = rec[8:]
        return rd

    def SendCmd(self, msg):
        """
        sends a command string to the TC66C. There are only 7 valid ones (so far):

            query     response    4 bytes     'firm' or 'boot'
            getva     response 192 bytes     (see Poll function)
            gtrec     response variable       (see GetRec function)
            lastp     response    0 bytes     (previous page on the TC66 display)
            nextp     response    0 bytes     (next page on the TC66 display)
            rotat     response    0 bytes     (rotate TC66 screen)
            update    response    5 bytes     'uprdy' = prepare to load new firmware
        """
        self._SIF.write(msg.encode("ascii"))
        return


# --- Data Acquisition Function (Extracted + Adapted from 3rd party code, licence and links above)
def read_usb_data(tc66c_instance):
    """Reads data from the TC66C USB tester."""
    global first_reading_time, last_reading_time, first_mWh, last_mWh, previous_joules, GatherErrorCount
    try:
        if first_reading_time is None:  
            pd = tc66c_instance.Poll()
            # flush any stale data first time out
        pd = tc66c_instance.Poll()
        if pd:
            data = {
                "Volt": pd.Volt,
                "Current": pd.Current,
                "Power": pd.Power,
                "Resistance": pd.Resistance,
                "G0_mAh": pd.G0_mAh,
                "G0_mWh": pd.G0_mWh,
                "G1_mAh": pd.G1_mAh,
                "G1_mWh": pd.G1_mWh,
                "Temp": pd.Temp,
                "D_plus": pd.D_plus,
                "D_minus": pd.D_minus,
            }
            
            if first_reading_time is None:
                first_reading_time = datetime.now()
                first_mWh = data.get("G0_mWh", 0.0) + data.get("G1_mWh", 0.0)
                # adjusted as we do not know whether channel G0 or G1 is in use (only one at a time) so use both
            last_reading_time = datetime.now()
            last_mWh = data.get("G0_mWh", 0.0) + data.get("G1_mWh", 0.0)
            #print("DEBUG: ", first_mWh, last_mWh)
            if last_mWh >= 0:
                current_joules = (
                    (data.get("G0_mWh", 0.0) + data.get("G1_mWh", 0.0))
                    - (first_mWh if first_mWh is not None else 0.0)
                ) * 3.6
                print(
                    f"\r  Joules thus far: {current_joules:.1f}J, in {(last_reading_time-first_reading_time).total_seconds():.1f}seconds",
                    end="",
                    flush=True,
                )  # Include label in every update
                if GatherErrorCount > 0:
                    print(
                        f"!ReadErrs:{GatherErrorCount}!", end="", flush=True
                    )  # Include label in every update
                print(f"               ", end="", flush=True)  #
                # print(f"\r  Joules thus far: {current_joules:.1f}J,         ", end="", flush=True)  # Include label in every update
                previous_joules = current_joules
            return data
        else:
            print("Error polling TC66C")
            return None
    except Exception as e:
        GatherErrorCount += 1
        # print(f"Error reading data from TC66C: {e}")
        #   commented as during longer runs this spoils the output as every so often there's a serial misread (theory: OS / USB-232 driver)
        #   the result is based on cumulative numbers, so in theory only the last reading actually matters, the rest are progress indication only.
        return None


# --- Data Acquisition Thread ---
def data_acquisition():
    global running, output_file, experiment_params, stop_event, com_port, tc66c_instance, first_mWh, total_joules, previous_joules
    print("Data Acquisition Thread started.")
    sample_period = experiment_params.get(
        "sample_period", 1.0
    )  # Default to 1.0 if not received

    try:
        # USB device (TC66C) is now initialised in process_network_message
        if not tc66c_instance:
            print("Error: TC66C not initialised. Data acquisition aborted.")
            return

        while running and not stop_event.is_set():
            if output_file:
                # Read data from the USB device
                data = read_usb_data(tc66c_instance)
                if data:  # Only proceed if data is valid
                    # Calculate Joules for this reading
                    current_joules = (
                        (data.get("G0_mWh", 0.0) + data.get("G1_mWh", 0.0))
                        - (first_mWh if first_mWh is not None else 0.0)
                    ) * 3.6

                    # Format data for CSV
                    timestamp = datetime.now().isoformat()
                    csv_row = f"{timestamp},{experiment_params.get('iterations', 'NA')},{experiment_params.get('algorithm', 'NA')},\"{experiment_params.get('experiment_id', 'NA')}\",{sample_period:.2f},{current_joules:.2f}, \
                                {data.get('Volt', 'NA'):.4f},{data.get('Current', 'NA'):.4f},{data.get('Power', 'NA'):.4f},{data.get('Resistance', 'NA'):.4f},{data.get('G0_mAh', 'NA')},{data.get('G1_mAh', 'NA')},{data.get('Temp', 'NA'):.2f}, \
                                {data.get('D_plus', 'NA'):.4f},{data.get('D_minus', 'NA'):.4f}\n"
                    output_file.write(csv_row)
                    output_file.flush()  # Ensure data is written promptly

                    ##print("\n",{data.get('Volt', 'NA')},{data.get('Current', 'NA')},{data.get('D_plus', 'NA')},{data.get('D_minus', 'NA')},"\n")
                    # print("\n",{timestamp},{experiment_params.get('iterations', 'NA')},{experiment_params.get('algorithm', 'NA')},{experiment_params.get('experiment_id', 'NA')})
                    # print({sample_period},{current_joules})
                    # print({data.get('Volt', 'NA')},{data.get('Current', 'NA')},{data.get('Power', 'NA')},{data.get('Resistance', 'NA')})
                    # print({data.get('G0_mAh', 'NA')},{data.get('G1_mAh', 'NA')})
                    # print({data.get('Temp', 'NA')},{data.get('D_plus', 'NA')},{data.get('D_minus', 'NA')},"\n")
                    ###print(csv_row) # to show progress (not prowess!)   # DEBUG!!!

                    time.sleep(sample_period)
                else:
                    time.sleep(0.1)  # Wait a bit if no data is available
            else:
                time.sleep(0.1)  # Wait a bit if no output file is open
    except Exception as e:
        print(f"Error in Data Acquisition Thread: {e}")
    finally:
        if output_file:
            output_file.close()
            print(
                f"Data logging finished for ExperimentID: <{experiment_params.get('experiment_id', 'unknown')}>."
            )
        print("Data Acquisition Thread stopped.")


# --- Network Listener Thread ---
def network_listener():
    global running, experiment_params, output_file, data_thread, TCP_MODE, stop_event, com_port, com_port_override

    if TCP_MODE:
        sock_type = socket.SOCK_STREAM
        print("Network Listener started in TCP mode.")
        # TODO not fully implemented yet - placeholder - prefer UDP as no messy acks or 3 way delay (we have a reliable network for UDP datagrams)
    else:
        sock_type = socket.SOCK_DGRAM
        print("Network Listener started in UDP mode.")

    with socket.socket(socket.AF_INET, sock_type) as sock:
        sock.bind((HOST, PORT))
        if TCP_MODE:
            sock.listen()
            conn, addr = sock.accept()
            with conn:
                print(f"Connected by {addr}")
                while not stop_event.is_set():
                    try:
                        conn.settimeout(
                            1
                        )  # Set a timeout for recv to allow checking the stop event
                        data = conn.recv(1024).decode()
                        if not data:
                            break
                        process_network_message(data)
                    except socket.timeout:
                        continue
                    except ConnectionResetError:
                        print("Connection with Raspberry Pi reset.")
                        break
                    except Exception as e:
                        print(f"Error receiving data (TCP): {e}")
                        break
        else:
            print(f"Listening for UDP packets on {HOST}:{PORT}")
            while not stop_event.is_set():
                try:
                    sock.settimeout(1)  # Set a timeout for recvfrom
                    data, addr = sock.recvfrom(1024)
                    process_network_message(data.decode())
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error receiving data (UDP): {e}")
                    break

    print("Network Listener stopped.")


# --- Function to Handle a received network message ---
def process_network_message(message):
    global running, experiment_params, output_file, data_thread, TCP_MODE, stop_event, com_port, com_port_override, tc66c_instance, first_reading_time, last_reading_time, first_mWh, last_mWh
    if message.startswith("STOP"):
        print(
            " Signalled to Stop. Live Updates Ends"
        )  # bit of information, + a bit of a force of a newline
    print(
        f"Received: '{message}'"
    )  # some duplication here - do we want to keep this one? Yes for now.
    if message.startswith("GETREADY"):
        # here we initialise everything, the files, the connection to the TC66C meter and check for errors, next in a few secs: START
        try:
            _, params_json = message.split(maxsplit=1)
            experiment_params = json.loads(params_json)
            print(f"Experiment parameters received: {experiment_params}")
            TCP_MODE = experiment_params.get("tcp", False)  # Update TCP mode if sent
            experiment_id = experiment_params.get("experiment_id", "default_experiment")
            filename = f"{experiment_id}_data.csv"
            try:
                output_file = open(filename, "w")
                output_file.write(
                    "Timestamp,Iterations,Algorithm,Experiment_ID,Sample_Period,Joules,Volt,Current,Power,Resistance,G0_mAh,G1_mAh,Temp,D_plus,D_minus\n"
                )  # Corrected header 
                print(f"Output file opened: {filename}")
                # create new file for each experiment - write the headers to the experiment CSV for later understanding
            except Exception as e:
                print(f"Error opening output file: {e}")
            # If GETREADY comes in before user selects a part interactively, use the default COM port (and set the flag)
            if not com_port_override:  # Only override if not already set by the user
                com_port = com_port  # changed from COM5 explicitly 
                print(f"GETREADY received, using COM port: {com_port}")
                com_port_override = True  # Set the flag to prevent further changes
            # Initialise TC66C here
            try:
                tc66c_instance = TC66C(com_port)
                print(
                    "TC66C meter initialised, ready to read when we get the START message"
                )
            except Exception as e:
                print(f"Error initialising TC66C: {e}")
                # Handle the error appropriately (e.g., exit, set a flag, etc.)
                return  # Or raise an exception to stop further processing
            # Reset start and end times for a new experiment
            first_reading_time = None
            last_reading_time = None
            first_mWh = None
            last_mWh = None
            previous_joules = None  # Reset previous_joules for a new experiment
        except json.JSONDecodeError as e:
            print(f"Error decoding GETREADY parameters: {e}")
        except ValueError:
            print("Invalid GETREADY message format.")
        except Exception as e:
            print(f"Error processing GETREADY: {e}")
    elif message == "START":
        # this is the last thing sent from the experimentation platform before starting experiment
        if (
            experiment_params and output_file and tc66c_instance
        ):  # Check if tc66c_instance is initialised
            print("START signal received. Starting data acquisition.")
            # Ensure the initial values are reset right before starting data collection
            #first_reading_time = None
            #last_reading_time = None
            #first_mWh = None
            #last_mWh = None
            #previous_joules = None  
            running = True
            data_thread = threading.Thread(target=data_acquisition)
            data_thread.start()
            # kick off the thread to start reading the TC66C data at the required interval (specified as param from DUT)
        else:
            print(
                "Error: Received START before GETREADY or output file not initialised."
            )
    elif message.startswith("STOP"):
        # Stop closes down all the files, threads and stops the timers etc.
        try:
            print("STOP signal received. Stopping data acquisition.")
            running = False
            if data_thread and data_thread.is_alive():
                data_thread.join()
            cleanup()
            stop_event.set()  # Signal the network thread to stop

            _, params_json = message.split(maxsplit=1)
            stop_data = json.loads(params_json)
            # print(f"STOP data received: {stop_data}") - too busy to print with params like remote temps etc.
            print(f"STOP message and data received.")
            # Now you can access data like:
            # stop_data["time_to_run"], stop_data["start_temperature"], etc.
        except json.JSONDecodeError as e:
            print(f"Error decoding STOP parameters: {e}")
        except ValueError:
            print("Invalid STOP message format.")
        except Exception as e:
            print(f"Error processing STOP: {e}")
    else:
        # only the 3 types of messages for now.
        print(f"Unknown message received: {message}")


# --- Function to end experiment, calculate final totals for time and Joules, update log file with single line of results, update user ---
def cleanup():
    global master_filename, master_output_file, output_file, first_reading_time, last_reading_time, first_mWh, last_mWh, experiment_params, stop_data, previous_joules
    if output_file:
        output_file.close()
        print("Cleanup complete.")
    if (
        first_reading_time
        and last_reading_time
        and first_mWh is not None
        and last_mWh is not None
    ):
        total_joules = (last_mWh - first_mWh) * 3.6
        iterations = experiment_params.get("iterations", 1)  # Default to 1 if not found
        joules_per_1000_iterations = (
            (total_joules / iterations) * 1000 if iterations > 0 else "N/A"
        )
        experiment_duration = (last_reading_time - first_reading_time).total_seconds()
        time_per_1000_iterations = (
            (experiment_duration / iterations) * 1000 if iterations > 0 else "N/A"
        )
        # time_per_1000_iterations = 666 # test value
        print(
            f"*Total Energy Consumed: {total_joules:.1f} Joules over {experiment_duration:.1f} seconds"
        )
        print(
            f"  *Energy Rate: {float(joules_per_1000_iterations):.1f} J/1000 key generations"
            if isinstance(joules_per_1000_iterations, (int, float))
            else f"  Energy Rate: {joules_per_1000_iterations} J/1000 key generations"
        )

        # get a single liner written to a master results document for easy ingest
        timestamp = datetime.now().isoformat()
        # string_input.replace(" ", "")
        singleliner1 = f"{timestamp},{experiment_params.get('iterations', 'NA')},"
        singleliner2 = f"{experiment_params.get('algorithm', 'NA')},{experiment_params.get('experiment_id', 'NA')},"
        singleliner3 = f"{total_joules:.2f},{experiment_duration:.1f},{joules_per_1000_iterations:.3f},{time_per_1000_iterations:.3f}\n"
        singleliner = (
            singleliner1.replace(" ", "") + singleliner2 + singleliner3.replace(" ", "")
        )
        # remove any stray whitespace
        # singleliner = f"{timestamp},{experiment_params.get('iterations', 'NA')},{experiment_params.get('algorithm', 'NA')},{experiment_params.get('experiment_id', 'NA')},{total_joules:.2f},{experiment_duration:.1f},{joules_per_1000_iterations:.3f},{time_per_1000_iterations:.3f}\n"
        # print(singleliner)

        # file_attributes = os.stat(master_filename).st_mode
        try:
            os.chmod(master_filename, stat.S_IREAD | stat.S_IWRITE)
        except Exception as e:
            print(f"***WARNING**** Can't set the Master output file as RW: {e}")
        # this sets the master filename as RW, to update it.  It normally is RO

        try:
            master_output_file = open(master_filename, "a")
        except Exception as e:
            print(f"Error opening Master output file: {e}")
        if master_output_file:
            master_output_file.write(singleliner)
            master_output_file.flush()  # Ensure data is written promptly
            master_output_file.close()  # and file closed back down
            print(f"Master:{master_filename}:Update:{singleliner}", end="")

        try:
            os.chmod(master_filename, stat.S_IREAD)
        except Exception as e:
            print(f"***WARNING**** Can't set the Master output file back to RO: {e}")
        # this sets the master filename as RW, to update it.  It normally is RO

        if stop_data:  # Check if stop_data is available
            print("\nExperiment Summary from Pi:")
            print(
                f"  Time to run on Pi: {stop_data.get('time_to_run', 'N/A'):.2f} seconds"
            )
            print(
                f"  Start Temperature: {stop_data.get('start_temperature', 'N/A'):.2f} C"
            )
            print(
                f"  Stop Temperature: {stop_data.get('stop_temperature', 'N/A'):.2f} C"
            )
            if "time_data" in stop_data:
                print(f"  Pi Time Data: {stop_data.get('time_data', 'N/A')}")
    previous_joules = None  # Reset for the next experiment


# --- Probs a bit windowsey - read which COM ports are available if not specified on command line, and allow user to select, times-out if no response ---
def list_com_ports():
    """Lists available COM ports and lets the user choose."""
    global com_port
    ports = list(serial.tools.list_ports.comports())
    if ports:
        print(
            "\nPlease select which COM port the TC66C tester is attached to from the detected COM ports:"
        )
        for i, port in enumerate(ports):
            print(
                f"    {i + 1}: {port.device}- {port.description} "
            )  # Indented by 4 spaces
        print(
            "Enter line# to use then Enter (or wait 5secs for default:",
            com_port,
            ")...",
        )  # printing explicitly as input doesn't seem to print it
        while True:
            try:
                import msvcrt

                start_time = time.time()
                choice = ""
                while time.time() - start_time < 5:  # Changed timeout to 10 seconds
                    if msvcrt.kbhit():
                        choice += msvcrt.getch().decode()
                        if choice.endswith("\r"):  # Enter key pressed
                            choice = choice[:-1]  # Remove the carriage return
                            break
                if not choice:
                    print(f"No user response after 5s, so defaulting to ", com_port)
                    return com_port
                choice = choice.strip()
                if not choice:
                    return com_port  # Default
                if choice.isdigit() and 1 <= int(choice) <= len(ports):
                    return ports[int(choice) - 1].device
                else:
                    print("Invalid choice. Please try again.")
            except ImportError:
                # If msvcrt is not available (e.g., not on Windows), use the original input
                choice = input(
                    "Enter line# to use. (Enter, or wait 5s for default: ", com_port
                )  # Doesn't appear to print, so print explicitly above
                if not choice:
                    return com_port  # Default
                if choice.isdigit() and 1 <= int(choice) <= len(ports):
                    return ports[int(choice) - 1].device
                else:
                    print("Invalid choice. Please try again.")
    else:
        print("No COM ports found. Using default ", com_port, ".")
        return com_port




# --- Main funtion, start here ---
def main():
    global network_thread, stop_event, com_port, com_port_override, tc66c_instance, previous_joules

    if platform.system() != "Windows":
        print("This script is designed to be run on Windows.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Windows data acquisition server.")
    parser.add_argument(
        "--com",
        dest="com_port",
        action="store",
        type=str,
        help="COM port to use for USB tester (overrides interactive selection)",
    )
    parser.add_argument(
        "--nonet-delaystart",
        dest="nonet_delaystart",
        action="store",
        type=float,
        default=0.0,
        help="Delay in seconds before sending START message in no-network mode",
    )
    parser.add_argument(
        "--nonet-duration",
        dest="nonet_duration",
        action="store",
        type=float,
        default=30.0,
        help="Duration in seconds to run the data acquisition in no-network mode",
    )
    args = parser.parse_args()

    if args.com_port:
        com_port = args.com_port
    else:
        com_port = list_com_ports()
    print(f"\n\nSelected COM Port: {com_port}")
    print("Please start the experiment on the Device Under Test (DUT) now COM port is selected.")


    run_no_network = False    # only if we get any nonet arguments do we go into this mode, otherwise normal network operations
    if '--nonet-delaystart' in sys.argv and '--nonet-duration' in sys.argv:
        if args.nonet_delaystart is not None and args.nonet_duration is not None and args.nonet_delaystart >= 0 and args.nonet_duration > 0:
            run_no_network = True
    elif '--nonet-delaystart' in sys.argv and '--nonet-duration' not in sys.argv:
        if args.nonet_delaystart is not None and args.nonet_delaystart >= 0:
            run_no_network = True # Use default duration if only delay is provided
    elif '--nonet-duration' in sys.argv and '--nonet-delaystart' not in sys.argv:
        if args.nonet_duration is not None and args.nonet_duration > 0:
            run_no_network = True # Use default delay if only duration is provided
            
    if run_no_network:
        print(f"\nRunning in no-network mode - Start delay: {args.nonet_delaystart:.2f}s, Duration: {args.nonet_duration:.2f}s\n")
        # Simulate GETREADY
        getready_message = f"GETREADY {{\"experiment_id\": \"manual_run\", \"algorithm\": \"test_algo\", \"iterations\": 1000, \"sample_period\": 0.1}}"
        process_network_message(getready_message)
        time.sleep(args.nonet_delaystart)
        # Simulate START
        process_network_message("START")
        time.sleep(args.nonet_duration)
        # Simulate STOP
        stop_message = f"STOP {{\"time_to_run\": {args.nonet_duration:.2f}, \"start_temperature\": 25.0, \"stop_temperature\": 26.0}}"
        process_network_message(stop_message)
        print("No-network run finished.")
    else:
        network_thread = threading.Thread(target=network_listener)
        network_thread.daemon = True
        network_thread.start()
        print("Main thread started. Waiting for GETREADY (Ctrl+C to exit)...")
        try:
            while True:
                time.sleep(0.1)
                if not network_thread.is_alive():
                    break
        except KeyboardInterrupt:
            print("Exiting...")
            running = False
            stop_event.set()
            if data_thread and data_thread.is_alive():
                data_thread.join()
            cleanup()
            sys.exit(0)




if __name__ == "__main__":
    import sys

    main()


# END CODE