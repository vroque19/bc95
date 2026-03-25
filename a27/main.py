from gpib import Instrument, read_agilent, read_fluke, read_keithley_2306, setup_instruments, set_keithley, set_battsim, scan_gpib
import time
import csv
from datetime import datetime
from maxusb_spmi import maxusb

PATH = r"C:\Users\vroque\Programs\a27\data"
# Function to write to registers
def spmi_write(sid, addr, data):
    print(maxusb.spmi_ext_reg_wr(sid, addr, data))
    
def setup_max77795():
    # ----------------------------
    # 0x3 is SPMI SID for Charger portion of BC95
    # ----------------------------
    spmi_write(0x3, 0x56, [0x0C])  # Unlock charger in cfg_6
    spmi_write(0x3, 0x54, [0x37])  # Termination Voltage = 4530mV cfg_4
    spmi_write(0x3, 0x59, [0xFF])  # Charge Current limit for CHGIN cfg_9
    spmi_write(0x3, 0x5A, [0x7F])  # Charge Current limit for WCIN cfg_10
    spmi_write(0x3, 0x50, [0x05])  # Charge mode = 0x5
    spmi_write(0x3, 0x52, [0x33])  # Fast Charging Current = 2.5A cfg_2
    spmi_write(0x3, 0x67, [0x4E]) # enable inlim cont & dynamic floor cfg_23

wcin_chg_levels = [5.1, 6.8, 9, 12, 15.5] # WCIN

def get_vbatt_reg(instruments, vbatt_set: float, set_chgin, chg_cv_prm: int) -> float:
    agilent, keithley, battsim = instruments
    set_keithley(keithley, set_chgin)
    spmi_write(0x3, 0x54, [(chg_cv_prm)])
    time.sleep(1)  # wait for voltage to stabilize
    reading = read_agilent(agilent)
    return reading
    
def main():
    # scan_gpib() # uncomment to find GPIB addresses of connected instruments
    instruments = setup_instruments()
    agilent, keithley, battsim = instruments
    filename = f"{PATH}_datetime.now().strftime('%Y%m%d_%H%M%S').txt"
    chg_cv_prms = [0x37]
    set_battsim(battsim, 4.53, output_on=True)
    with open(filename, mode='w', newline='') as f:
        for chg in wcin_chg_levels:
            time.sleep(1)  # wait for voltage to stabilize
            vbatt = get_vbatt_reg(instruments, vbatt_set=chg, set_chgin=chg, chg_cv_prm=0x37)
            print(vbatt)
            f.write(f"{vbatt}\n")
    print(f"Data written to {filename}")

if __name__ == "__main__":
    setup_max77795()
    main()