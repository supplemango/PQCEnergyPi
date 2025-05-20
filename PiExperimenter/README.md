# PiExperimenter Source Files 
There are a couple of files here:

**experimenter.py**  which is a single experiment for a certain algorithm over a number of iterations.

**batch_experimenter.py**  which runs a few experiments consecutively using a source file with the parameters for each.


e.g. a command and it's output at the Pi experimenter end:

<code>cameron@crypto:~ $ **python ./experimenter.py --algorithm ML-KEM-1024 --iterations 3200**
UDP: Sent 'GETREADY {"iterations": 3200, "algorithm": "ML-KEM-1024", "experiment_id": "20250507133228-ML-KEM-1024-3200", "sample_period": 1.0}' to Windows Measurement Machine (192.168.5.59:65432)
Starting experiment: 20250507133228-ML-KEM-1024-3200
Setting up environment on the Device Under Test (DUT), setting fan and CPU to max
Start Temperature: 46.85 C
UDP: Sent 'START' to Windows Measurement Machine (192.168.5.59:65432)
STARTing experiment with 3200 iterations and algorithm ML-KEM-1024
Experiment finished
UDP: Sent 'STOP {"time_to_run": 17.38626154800295, "start_temperature": 46.85, "stop_temperature": 50.7}' to Windows Measurement Machine (192.168.5.59:65432)
Time to run on Pi: 17.39 seconds
Start Temperature: 46.85 C
Stop Temperature: 50.70 C
Environment on Device Under Test (DUT) defaulted
cameron@crypto:~ $
</code>
There's a reasonable amount of print and debug action shown, so the user knows what's going on.  For the corresponding example at the Collector end - see the readme in that folder.


e.g of batch:
cameron@crypto:~ $ **python ./batch_experimenter.py 500kSourceRSAscaled.txt**    
(be prepared to wait about a day for this one!)
Output shows basically the same stuff with the following extras:

<code>cameron@crypto:~ $ **python ./batch_experimenter.py 10kSourceRSAscaled.txt**
Detected algorithm: EC -pkeyopt ec_paramgen_curve:secp160r1, Iterations: 10000 (parameters file)
Running: python experimenter.py --algorithm 'EC -pkeyopt ec_paramgen_curve:secp160r1' --sample_period 0.5 --iterations 10000 --host 192.168.5.59 --port 65432
[[SNIP]]
Experiment with algorithm 'EC -pkeyopt ec_paramgen_curve:secp160r1' and 10000 iterations completed. Pausing for 15 seconds to cool/synch...</code>

<code>Detected algorithm: EC -pkeyopt ec_paramgen_curve:secp224r1, Iterations: 10000 (parameters file)
Running: python experimenter.py --algorithm 'EC -pkeyopt ec_paramgen_curve:secp224r1' --sample_period 0.5 --iterations 10000 --host 192.168.5.59 --port 65432
<<SNIP>>
Experiment with algorithm 'EC -pkeyopt ec_paramgen_curve:secp224r1' and 10000 iterations completed. Pausing for 15 seconds to cool/synch...</code>

<code>Detected algorithm: NULL, Iterations: 10000 (parameters file)
Running: python experimenter.py --algorithm 'NULL' --sample_period 0.5 --iterations 10000 --host 192.168.5.59 --port 65432
[[SNIIIIIIIIIIIIIIIIIIIIIIIP]]</code>

<code>etc. etc.</code>

(As I wasn't willing to wait 24 hours for this output, I ran a shorter example with 10 iterations per algorithm to show what it looks like when it ends!...)

<code>[[SNIP]]
Experiment with algorithm 'RSA -pkeyopt rsa_keygen_bits:4096' and 10 iterations completed. Pausing for 15 seconds to cool/synch...
Note: Skipping blank line in parameter file.</code>

<code>Note: Parameter file processing completed.
cameron@crypto:~ $
</code>


Further documentation is in the source code or available with --help
