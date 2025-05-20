# Output Files
These files are example outputs from the Windows Collector machine and the responder.py code. 

The **"20250507133228-ML-KEM-1024-3200_data.csv"** file is the full results from the singular example experiment run as per the Collector and PiExperimenter readme files.
Opening it there are all the accumulating results collected from the TC66C between the START and STOP messages.

There are details of the experiment: algorithm,  iteration counts, Experiment ID and sample period.
For each sample period, there is a timestamp together with instantanous measures of Voltage, Current, Wattage, Resistance and temperature of the tester.
Most importantly, there are also cumulative values for Joules (calculated by the code) and mAh used to calculate this Joules value.

The **"AllResults - Copy.csv"** file is a slightly tweaked version of the consolidated log.
The contents I have included here are from 3 batch experiments using the 10k 100k and 500k Input files, used for the graphs and results of this paper, and also the same singular experiment as included as above and in the Collector and PiExperimenter folders. 
I've seperated each with a blank line for clarity purposes.  I've cut out the other experiments which were in this log. 

This log exists to ensure that results don't have to be taken from screen (and get missed), so that they'll be retriveable later (this is a case in point as the batch experiments are from mid-to-late April!)
