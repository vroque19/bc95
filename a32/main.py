from gpib import Instrument, read_agilent, read_fluke, read_keithley, setup_instruments, set_keithley, scan_gpib
import time
import csv
from datetime import datetime

# from maxusb_spmi import maxusb

vchgin_levels = [5, 9, 12]
MAX_CHARGE_CURRENT = 0b1000 + 1
CSV_HEADERS = ["timestamp", "CHGCC", "vbat", "ibat", "vchgin", "ichgin"]
# TODO: verify SID
SPMI_SLAVE_ID = 0x03 # Not shown in data sheet?

"""
TODO
1. fill in all the functions to set the instruments by calling gpib API
    - not sure which instrument connects to which part of the board
2. fill in fast charge current function using spmi API


"""

# # Function to read register
# def spmi_read_hex(sid, addr, length):
#     print([hex(n) for n in maxusb.spmi_ext_reg_rd(sid, addr, length)])

# Function to write to registers
def spmi_write(sid, addr, data):
    print(maxusb.spmi_ext_reg_wr(sid, addr, data))


def set_chgcc(val: int):
    # call spmi code
    print("Setting CHGCC to", val)
    spmi_write(sid=SPMI_SLAVE_ID, addr=0x52, data=[val])
    

def read_all_data(csv_writer, instruments: list[Instrument], chgcc: int):
    agilent, fluke, keithley = instruments
    row = {
        "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "CHGCC": chgcc,
        "vbat": read_agilent(agilent),
        "ibat": read_fluke(fluke),
        "vchgin": read_keithley(keithley),
        "ichgin": read_keithley(keithley),
    }
    csv_writer.writerow(row)


# for every vchgin, go through all fast charge current modes and get readings
def get_efficiency(vchgin: float, csv_writer, instruments: list[Instrument]):
    agilent, fluke, keithley = instruments
    """
    CHG_CFG_02: bits 5-0 CHGCC (Fast Charge Current mA)
    page 464 of data sheet
    2461 off
    sleep 0.5s
    write chgcc
    sleep 5s
    2461 on
    measure
    """
    for i in range(MAX_CHARGE_CURRENT):
        keithley.configure("OUTP OFF")
        time.sleep(0.5)
        set_chgcc(i)
        time.sleep(1)
        keithley.configure("OUTP ON")
        time.sleep(1) # wait for current to settle
        read_all_data(csv_writer, instruments, i)

    keithley.configure("OUTP OFF")
    

# ----------------------------
# Voltage test sequence
# Stepping through 5V, 9V, and 12V
# ----------------------------
def run_tests(instruments: list[Instrument]=[]):
    for level in vchgin_levels:
        set_keithley(instruments[2], level) # set the vchgin level
        filename = f"A.32_{datetime.now().strftime(f'%Y%m%d_%H_%M_%S-{level}V')}.csv" # create the csv
        with open(filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            get_efficiency(level, writer, instruments)


def main():
    instruments = setup_instruments()
    run_tests()
    # ----------------------------
    # Cleanup to close GPIB comms
    # ----------------------------
    for instrument in instruments:
        instrument.close()


if __name__ == "__main__":
    main()