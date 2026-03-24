from gpib import Instrument, read_agilent, read_fluke, read_keithley_2306, setup_instruments, set_keithley, set_battsim, scan_gpib
import time
import csv
from datetime import datetime
from maxusb_spmi import maxusb
import glob
import pandas as pd
from icecream import ic 

CHG_IN = 15.5
SPMI_SLAVE_ID = 0x03
PATH=rf'C:\Users\vroque\Programs\a30\{CHG_IN}'

CSV_HEADERS = ["timestamp", "v", "i", "vset", "ibatt", "vbatt", "floor", "ceiling"]
FINAL_VALS = []
ITRICKLE_VALS = [.125, .466, 1, 1.225]
VTRICKLE_VALS = [3.1, 3.35]
ITRICKLE_COUNT = 4
VTRICKLE_COUNT = 2
CHARGE_VOLTAGE = 0 # 4.85, 5, 9, 15, 15.5
CHARGER_VOLTAGES = [5.1, 6.8, 9, 12, 15.5] # WCIN
# CHARGER_VOLTAGES = [4.85, 5, 9, 15, 15.5]
VTRICKLE_REGS = {
    3.1: 0x37,
    3.35: 0x3F
}
ITRICKLE_REGS = {
    .125: 0x0B,
    0.466: 0x4B,
    1: 0x8B,
    1.225: 0xCB
}


# # Function to read register
# def spmi_read_hex(sid, addr, length):
#     print([hex(n) for n in maxusb.spmi_ext_reg_rd(sid, addr, length)])

# # Function to write to registers
def spmi_write(sid, addr, data):
    print(maxusb.spmi_ext_reg_wr(sid, addr, data))


def setup_max77795():
    # ----------------------------
    # SPMI setup trickle charge
    # ----------------------------
    spmi_write(0x3, 0x56, [0x0C])  # Unlock charger in cfg_6
    spmi_write(0x3, 0x54, [0x37])  # Termination Voltage = 4530mV cfg_4
    spmi_write(0x3, 0x59, [0xFF])  # Charge Current limit for CHGIN cfg_10
    spmi_write(0x3, 0x5A, [0x7F])  # Charge Current limit for WCIN cfg_10
    spmi_write(0x3, 0x50, [0x05])  # Charge mode = 0x5
    spmi_write(0x3, 0x52, [0x1E])  # Increase Fast Charging Current = 1.5A cfg_2
    spmi_write(0x3, 0x67, [0x0E]) # enable inlim cont & dynamic floor cfg_23 & low bandwidth

CURRENT_JUMP = 0.5 # value where current jumps out of v trickle

def step_down(instruments, writer, VBATT: float, target_itrickle: float = 0.125, target_vtrickle: float = 3.1):
    fluke, keithley = instruments
    # set_battsim(keithley, VBATT)
    current_prev = read_keithley_2306(keithley)
    current = current_prev
    vbat_prev = read_fluke(fluke)
    # ic(VBATT)
    while abs(current - current_prev) < CURRENT_JUMP:
        # time.sleep(0.1)
        # ic(VBATT)
        print(VBATT)
        set_battsim(keithley, VBATT)
        current_prev = current
        current = read_keithley_2306(keithley)
        vbat = read_fluke(fluke)
        if vbat > 3.2:
            VBATT -= 0.01
        else:
            VBATT -= 0.002
        row = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "v": target_vtrickle,
            "i": target_itrickle,
            "vset": VBATT,
            "vbatt": vbat,
            "ibatt": current
        }
        if abs(current - current_prev) > CURRENT_JUMP:
            # print(f"Found hysteresis floor: {vbat}")
            print(f"set: {VBATT}\nread: {vbat_prev}")
            final_voltage = (vbat_prev, VBATT)

            row["floor"] = "true"
        # print(row)
        writer.writerow(row)
    # take three extra measurements after reaching the jump
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
        vbat_prev = vbat

    return final_voltage



def step_up(instruments, writer, VBATT: float = 2.9, target_itrickle: float = 0.125, target_vtrickle: float = 3.1):
    fluke, keithley = instruments
    current_prev = read_keithley_2306(keithley)
    current = current_prev
    # set_battsim(keithley, VBATT)
    vbat_prev = read_fluke(fluke)
    while abs(current - current_prev) < CURRENT_JUMP:
        print(VBATT)
        set_battsim(keithley, VBATT)
        vbat = read_fluke(fluke)
        if vbat < target_vtrickle - 0.2:
            VBATT += 0.005
        else:
            VBATT += 0.002

        # ic(VBATT)
        current_prev = current
        current = read_keithley_2306(keithley)
        row = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "v": target_vtrickle,
            "i": target_itrickle,
            "vset": VBATT,
            "vbatt": vbat,
            "ibatt": current
        }
        if abs(current - current_prev) > CURRENT_JUMP:
            # print(f"Found hysteresis ceiling: {vbat_prev}")
            final_voltage = (vbat_prev, VBATT)
            row["ceiling"] = "true"
            print(f"set: {VBATT}\nread: {vbat}")
        # print(row)
        writer.writerow(row)
        vbat_prev = vbat

    # take three extra measurements
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
    vbat_prev = vbat

    return final_voltage


def find_hysteresis(instruments: list[Instrument], charger_voltage):
    fluke, keithley = instruments
    set_battsim(keithley, 3.0)
    for v in range(VTRICKLE_COUNT):
        target_vtrickle = VTRICKLE_VALS[v]
        spmi_write(0x3, 0x62, [VTRICKLE_REGS[target_vtrickle]])
        print(f"Change V-Trickle to {VTRICKLE_VALS[v]}")

        for i in range(ITRICKLE_COUNT):
            target_itrickle = ITRICKLE_VALS[i]
            spmi_write(0x3, 0x63, [ITRICKLE_REGS[target_itrickle]])
            print(f"Change I-Trickle to {ITRICKLE_VALS[i]}")
            filename = fr"{PATH}\A.28_{datetime.now().strftime(f'%Y%m%d_%H_%M_%S-{charger_voltage}-{target_vtrickle}V_{target_itrickle}A')}.csv"
            with open(filename, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
                writer.writeheader()
                vstart = target_vtrickle + 0.05   
                ic(target_vtrickle, target_itrickle)   
                ic(vstart)         
                floor = step_down(instruments, writer, vstart, target_itrickle, target_vtrickle)
                ic(floor)
                step_up_start = floor[1]
                step_up_start += 0.15
                if target_itrickle >= 0.466:
                    step_up_start -= 0.05
                ceiling = step_up(instruments, writer, step_up_start, target_itrickle, target_vtrickle)
                print(f"floor, ceiling: {floor[0], ceiling[0]}")
                floor_round = round(floor[0], 3)
                FINAL_VALS.append((floor_round, ceiling[0]))
    ic(f"Final Vals: {FINAL_VALS}")

            

def main():
    # scan_gpib()
    instruments = setup_instruments()
    setup_max77795()
    fluke, keithley = instruments
    print(f"Input the charge voltage you want to test {CHARGER_VOLTAGES}\n\n")
    CHARGE_VOLTAGE = float(input("Voltage: "))
    if(CHARGE_VOLTAGE not in CHARGER_VOLTAGES):
        CHARGE_VOLTAGE = int(input("Voltage: "))
    ic(CHARGE_VOLTAGE)
    find_hysteresis(instruments=instruments, charger_voltage=CHARGE_VOLTAGE)
    charger_voltage = CHARGE_VOLTAGE
        # Merge all CSVs for this charger voltage into one master file
    master_filename = fr"{PATH}\A.28_DONE_{charger_voltage}V_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    csv_files = glob.glob(fr"{PATH}\A.28_*-{charger_voltage}-*.csv")
    dfs = [pd.read_csv(f) for f in csv_files]
    if dfs:
        pd.concat(dfs, ignore_index=True).to_csv(master_filename, index=False)
        print(f"Master CSV saved: {master_filename}")



    for instrument in instruments:
        instrument.close()
if __name__ == "__main__":
    main()