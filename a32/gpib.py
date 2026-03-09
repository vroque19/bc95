import pyvisa
import numpy as np
import time
import csv

AGILENT_34401A = 'GPIB0::21::INSTR' # measure battery voltage
KEITHLEY_2461 = 'GPIB0::18::INSTR' # sourcemeter handles chgin
FLUKE_8845A = 'GPIB0::24::INSTR' # battery current

class Instrument:
    def __init__(self, resource_manager, addr: str):
        self.device = resource_manager.open_resource(addr)
        self.addr = addr

    def configure(self, command):
        """Send configuration strings."""
        self.device.write(command)

    def read_avg(self, query_cmd: str, samples=5, split_index=None):
        """Generic averaging function for any meter."""
        readings = []
        for _ in range(samples):
            raw = self.device.query(query_cmd)
            # If the response is a CSV string (like Keithley), split it
            if split_index is not None:
                val = float(raw.split(',')[split_index])
            else:
                val = float(raw)
            readings.append(val)
        return np.mean(readings)

    def close(self):
        self.device.close()
        

def setup_instruments():
    rm = pyvisa.ResourceManager()

    voltmeter = Instrument(rm, AGILENT_34401A)
    currentmeter = Instrument(rm, FLUKE_8845A)
    sourcemeter = Instrument(rm, KEITHLEY_2461)

    voltmeter.configure("*RST; :CONF:VOLT:DC")
    currentmeter.configure("*RST; :CONF:CURR:DC 10") # set current range to 10A
    sourcemeter.configure(":SOUR:FUNC VOLT; :OUTP ON")

    return voltmeter, currentmeter, sourcemeter # agilent, fluke, keithley

def read_agilent(voltmeter: Instrument):
    avg_volt = voltmeter.read_avg(query_cmd="READ?", samples=10)
    return avg_volt
    
def read_fluke(currentmeter: Instrument):
    avg_current = currentmeter.read_avg(query_cmd="READ?")
    return avg_current

def read_keithley(sourcemeter: Instrument, mode: str):
    """
    Reads voltage, current, or resistance from Keithley 2461 SourceMeter and returns the average.
    """
    mode_map = {
        "voltage": ":MEAS:VOLT?",
        "current": ":MEAS:CURR?",
        "resistance": ":MEAS:RES?",
    }

    query_cmd = mode_map.get(mode.lower())
    return sourcemeter.read_avg(query_cmd=query_cmd)

def set_keithley(sourcemeter: Instrument, voltage: float):
    """
    Configures and turns on the Keithley 2461 SourceMeter to output voltage.
    """
    sourcemeter.configure(f":SOUR:FUNC VOLT; :SOUR:VOLT {voltage}; :OUTPut:STATe ON")
    return f"SourceMeter ON: {voltage}V"

# test gpib code
def scan_gpib():
    rm = pyvisa.ResourceManager()
    instruments = rm.list_resources()
    print("Connected instruments:", instruments)

    gpib_instruments = [i for i in instruments if "GPIB" in i]

    if not gpib_instruments:
        print("No GPIB instruments found.")
    else:
        for address in gpib_instruments:
            print(f"Connecting to {address}...")
            try:
                instrument = rm.open_resource(address)
                idn = instrument.query("*IDN?")
                print(f"Instrument at {address} responded with ID: {idn}")
            except Exception as e:
                print(f"Failed to communicate with {address}: {e}")
            finally:
                try:
                    instrument.close()
                except:
                    pass

