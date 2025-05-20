# Collector Source Code
The **responder.py** code runs on the Windows Collector machine.
Here's a single example (during the experiment the line in **BOLD** is updated a few times a second showing progress, when completed it moves to the next line):

<code>PS C:\Users\Camster> **python .\responder.py**

Please select which COM port the TC66C tester is attached to from the detected COM ports:
    1: COM4- Standard Serial over Bluetooth link (COM4)
    2: COM5- USB Serial Device (COM5)
    3: COM3- Standard Serial over Bluetooth link (COM3)
Enter line# to use then Enter (or wait 5secs for default: COM5 )... 
</code>_2+Enter_<code>
Selected COM Port: COM5
Please start the experiment on the Device Under Test (DUT) now COM port is selected.
Network Listener started in UDP mode.
Main thread started. Waiting for GETREADY (Ctrl+C to exit)...
Listening for UDP packets on 0.0.0.0:65432
Received: 'GETREADY {"iterations": 3200, "algorithm": "ML-KEM-1024", "experiment_id": "20250507133228-ML-KEM-1024-3200", "sample_period": 1.0}'
Experiment parameters received: {'iterations': 3200, 'algorithm': 'ML-KEM-1024', 'experiment_id': '20250507133228-ML-KEM-1024-3200', 'sample_period': 1.0}
Output file opened: 20250507133228-ML-KEM-1024-3200_data.csv
GETREADY received, using COM port: COM5
TC66C meter initialised, ready to read when we get the START message
Received: 'START'
START signal received. Starting data acquisition.
Data Acquisition Thread started.</code>

**Joules thus far: 90.0J, in 17.0seconds**
<code>         Signalled to Stop. Live Updates Ends
Received: 'STOP {"time_to_run": 17.38626154800295, "start_temperature": 46.85, "stop_temperature": 50.7}'
STOP signal received. Stopping data acquisition.
Data logging finished for ExperimentID: <20250507133228-ML-KEM-1024-3200>.
Data Acquisition Thread stopped.
Cleanup complete.
*Total Energy Consumed: 90.0 Joules over 17.0 seconds
  *Energy Rate: 28.1 J/1000 key generations
Master:AllResults.csv:Update:2025-05-07T13:32:49.902712,3200,ML-KEM-1024,20250507133228-ML-KEM-1024-3200,90.00,17.0,28.125,5.320
STOP message and data received.
Network Listener stopped.
PS C:\Users\Camster>
</code>

It can be simply looped when a batch experiment is initiated by the Pi.
e.g. <code> **while ($true) { python .\responder.py --com COM5 } **</code>

It's best to name the COM serial port explicitly when in the experiment is a batch so you don't have to interact.

The only difference in output for batch is a few blank lines printed between each output to separate results.


v6.14 option allows running without a network attached experimeter e.g.:  
**"python '.\responder.py' --com COM5 --nonet-delaystart 1.32 --nonet-duration 13"**   for a 13 sec capture after a 1.32 second start delay.

Further documentation is in the source code or available with --help as an argument.
