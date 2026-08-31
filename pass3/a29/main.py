from gpib import Instrument, read_agilent, read_fluke, read_keithley_2306, setup_instruments, set_keithley, set_battsim, scan_gpib
import time
import csv
import glob
import pandas as pd
from datetime import datetime
from maxusb_spmi import maxusb
from icecream import ic

SPMI_SLAVE_ID = 0x03
CHG_IN = 5

PATH=rf'C:\Users\vroque\Programs\a30\{CHG_IN}'
CSV_HEADERS = ["timestamp", "v", "i", "vset", "ibatt", "vbatt", "floor", "ceiling"]

FINAL_VALS = []

VPRCHRG_VALS = [2.5, 3]
IPRCHRG_VALS = [.02, .055]
IPRCHRG_COUNT = 2
V_COUNT = 2


VPRCHRG_REGS = {
    2.5: 0x27, # vtrickle = 3.1, vprecharge = 2.5
    3: 0x3F #vtrickle = 3.35, vprecharge = 3
}

IPRCHRG_REGS = {
    .02: 0x50,
    0.055: 0xD0
}

VPRECHARGE_REG = 0x62
IPRECHARGE_REG = 0x5F


# # Function to write to registers
def spmi_write(sid, addr, data):
    print(maxusb.spmi_ext_reg_wr(sid, addr, data))


def setup_max77795():
    # ----------------------------
    # SPMI setup for precharge
    # ----------------------------
    spmi_write(0x3, 0x56, [0x0C])  # Unlock charger in cfg_6
    spmi_write(0x3, 0x54, [0x37])  # Termination Voltage = 4530mV cfg_4
    spmi_write(0x3, 0x59, [0xFF])  # Charge Current limit for CHGIN cfg_10
    spmi_write(0x3, 0x5A, [0x7F])  # Charge Current limit for WCIN cfg_10
    spmi_write(0x3, 0x50, [0x05])  # Charge mode = 0x5
    spmi_write(0x3, 0x52, [0x1E])  # Increase Fast Charging Current = 1.5A cfg_2
    spmi_write(0x3, 0x67, [0x0E]) # enable inlim cont & dynamic floor cfg_23 & low bandwidth

CURRENT_JUMP = 0.04 # value where current jumps out of precharge

def step_down(instruments, writer, VBATT: float, target_IPRCHRG: float = 0.125, target_VPRCHRG: float = 3.1):
    fluke, keithley = instruments
    current_prev = read_keithley_2306(keithley)
    current = current_prev
    vbat_prev = read_fluke(fluke)
    while abs(current - current_prev) < CURRENT_JUMP:
        print(VBATT)
        set_battsim(keithley, VBATT)
        current_prev = current
        current = read_keithley_2306(keithley)
        vbat = read_fluke(fluke)
        if vbat > (target_VPRCHRG - 0.2):
            VBATT -= 0.1
        else:
            VBATT -= 0.05
        row = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "v": target_VPRCHRG,
            "i": target_IPRCHRG,
            "vset": VBATT,
            "vbatt": vbat,
            "ibatt": current
        }
        if abs(current - current_prev) > CURRENT_JUMP:
            # print(f"Found hysteresis floor: {vbat}")
            print(f"set: {VBATT}\nread: {vbat_prev}")
            final_voltage = (vbat_prev, VBATT)
            row["floor"] = "true"
        writer.writerow(row)
        vbat_prev = vbat
    for i in range(1):
        current = read_keithley_2306(keithley)
        vbat = read_fluke(fluke)
        row = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "vbatt": vbat,
            "ibatt": current,
            "floor": "true"
        }
        print(row)
        writer.writerow(row)

    return final_voltage



def step_up(instruments, writer, VBATT: float = 2.8, target_IPRCHRG: float = 0.125, target_VPRCHRG: float = 3.1):
    fluke, keithley = instruments
    current_prev = read_keithley_2306(keithley)
    current = current_prev
    vbat_prev = read_fluke(fluke)
    while abs(current - current_prev) < CURRENT_JUMP:
        print(VBATT)
        set_battsim(keithley, VBATT)
        vbat = read_fluke(fluke)
        if vbat < target_VPRCHRG - 0.06:
            VBATT += 0.05
        else:
            VBATT += 0.002
        current_prev = current
        current = read_keithley_2306(keithley)
        row = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "v": target_VPRCHRG,
            "i": target_IPRCHRG,
            "vset": VBATT,
            "vbatt": vbat,
            "ibatt": current
        }
        if abs(current - current_prev) > CURRENT_JUMP:
            final_voltage = (vbat_prev, VBATT)
            row["ceiling"] = "true"
            print(f"set: {VBATT}\nread: {vbat}")
        writer.writerow(row)
        vbat_prev = vbat

    for i in range(1):
        current = read_keithley_2306(keithley)
        vbat = read_fluke(fluke)
        row = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "vbatt": vbat,
            "ibatt": current,
            "ceiling": "true"
        }
        print(row)
        writer.writerow(row)
        print(f"set: {VBATT}\nread: {vbat}")

    row = {
        "timestamp": "Change register values for next test"
    }
    writer.writerow(row)

    return final_voltage


def find_hysteresis(instruments: list[Instrument], charger_voltage):
    fluke, keithley = instruments
    set_battsim(keithley, 3.0)
    for v in range(V_COUNT):
        target_VPRCHRG = VPRCHRG_VALS[v]
        spmi_write(0x3, VPRECHARGE_REG, [VPRCHRG_REGS[target_VPRCHRG]])
        print(f"Change V-PRECHARGE to {VPRCHRG_VALS[v]}")

        for i in range(IPRCHRG_COUNT):
            target_IPRCHRG = IPRCHRG_VALS[i]
            spmi_write(0x3, IPRECHARGE_REG, [IPRCHRG_REGS[target_IPRCHRG]])
            print(f"Change I-Trickle to {IPRCHRG_VALS[i]}")
            filename = fr"{PATH}\A.28_{datetime.now().strftime(f'%Y%m%d_%H_%M_%S-{charger_voltage}-{target_VPRCHRG}V_{target_IPRCHRG}A')}.csv"
            with open(filename, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
                writer.writeheader()
                vstart = target_VPRCHRG  
                ic(target_VPRCHRG, target_IPRCHRG)   
                ic(vstart)         
                floor = step_down(instruments, writer, vstart, target_IPRCHRG, target_VPRCHRG)
                ic(floor)
                step_up_start = floor[1]
                step_up_start += 0.3
                ceiling = step_up(instruments, writer, step_up_start, target_IPRCHRG, target_VPRCHRG)
                print(f"floor, ceiling: {floor[0], ceiling[0]}")
                floor_round = round(floor[0], 3)
                FINAL_VALS.append((floor_round, ceiling[0]))
    ic(f"Final Vals: {FINAL_VALS}")

  

def main():
    # scan_gpib()
    instruments = setup_instruments()
    setup_max77795()
    fluke, keithley = instruments
    CHARGE_VOLTAGE = CHG_IN
    CHARGER_VOLTAGES = [4.85, 5, 9, 15, 15.5]
    print("Slect [1]CHGIN or [2]WCIN\n\n")
    inp = int(input("Input:  "))
    if inp == 2:
        CHARGER_VOLTAGES = [5.1, 6.8, 9, 12, 15.5]


    print(f"Input the charge voltage you want to test {CHARGER_VOLTAGES}\n\n")
    CHARGE_VOLTAGE = float(input("Voltage: "))
    if(CHARGE_VOLTAGE not in CHARGER_VOLTAGES):
        print("Not a valid vin\n")
        CHARGE_VOLTAGE = int(input("Voltage: "))
    find_hysteresis(instruments=instruments, charger_voltage=CHARGE_VOLTAGE)

    master_filename = fr"{PATH}\A.28_DONE_{CHARGE_VOLTAGE}V_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    csv_files = glob.glob(fr"{PATH}\A.28_*-{CHARGE_VOLTAGE}-*.csv")
    dfs = [pd.read_csv(f) for f in csv_files]
    if dfs:
        pd.concat(dfs, ignore_index=True).to_csv(master_filename, index=False)
        print(f"Master CSV saved: {master_filename}")
    for instrument in instruments:
        instrument.close()
if __name__ == "__main__":
    main()