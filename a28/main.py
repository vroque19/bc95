from gpib import Instrument, read_agilent, read_fluke, read_keithley_2306, setup_instruments, set_keithley, set_battsim, scan_gpib
import time
import csv
from datetime import datetime
from maxusb_spmi import maxusb

SPMI_SLAVE_ID = 0x03 #
PATH=r'C:\Users\vroque\Programs\a28'
CSV_HEADERS = ["timestamp", "ibatt", "vbatt", "floor", "ceiling"]

ITRICKLE_VALS = [0.125, 0.466, 1, 1.225]
VTRICKLE_VALS = [3.1, 3.35]
ITRICKLE_COUNT = 2
VTRICKLE_COUNT = 2
CHARGE_VOLTAGE = 0 # 4.85, 5, 9, 15, 15.5
CHARGER_VOLTAGES = [4.85, 5, 9, 15, 15.5]
VTRICKLE_REGS = {
    3.1: 0x37,
    3.35: 0x39
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
    # SPMI setup for WCIN regulation
    # ----------------------------
    spmi_write(0x3, 0x56, [0x0C])  # Unlock charger in cfg_6
    spmi_write(0x3, 0x54, [0x37])  # Termination Voltage = 4530mV cfg_4
    spmi_write(0x3, 0x5A, [0x7F])  # Charge Current limit for CHGIN cfg_10
    # spmi_write(0x3, 0x5A, [hex(wcin_ilim)])  # Charge Current limit for WCIN cfg_10
    spmi_write(0x3, 0x50, [0x05])  # Charge mode = 0x5
    spmi_write(0x3, 0x52, [0x33])  # Max Out Fast Charging Current = 2.5A cfg_2
    spmi_write(0x3, 0x67, [0x4E]) # enable inlim cont & dynamic floor cfg_23

CURRENT_JUMP = 1.5 # value where current jumps out of v trickle

def step_down(instruments, writer, VBATT: float = 3.5, target_itrickle: float = 0.125, target_vtrickle: float = 3.1):
    fluke, keithley = instruments
    current_prev = read_keithley_2306(keithley)
    set_battsim(keithley, VBATT)
    current = current_prev
    while abs(current - current_prev) < CURRENT_JUMP:
        if VBATT > 2.9:
            VBATT -= 0.1
        elif VBATT > 2.8:
            VBATT -=0.05
        else: VBATT -= 0.01
        set_battsim(keithley, VBATT)
        current_prev = current
        current = read_keithley_2306(keithley)
        vbat = read_fluke(fluke)
        row = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "vbatt": vbat,
            "ibatt": current
        }
        if abs(current - current_prev) > CURRENT_JUMP:
            print(f"Found hysteresis floor: {vbat}")
            final_voltage = vbat

            row["floor"] = "true"
        print(row)
        writer.writerow(row)
    # take three extra measurements after reaching the jump
    for i in range(3):
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



def step_up(instruments, writer, VBATT: float = 3.8, target_itrickle: float = 0.125, target_vtrickle: float = 3.1):
    fluke, keithley = instruments
    current_prev = read_keithley_2306(keithley)
    current = current_prev
    set_battsim(keithley, VBATT)
    while abs(current - current_prev) < CURRENT_JUMP:
        if VBATT < 3:
            VBATT += 0.1
        else:
            VBATT += 0.01
        set_battsim(keithley, VBATT)
        current = read_keithley_2306(keithley)
        vbat = read_fluke(fluke)
        row = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "vbatt": vbat,
            "ibatt": current
        }
        if abs(current - current_prev) > CURRENT_JUMP:
            final_voltage = vbat
            print(f"Found hysteresis ceiling: {vbat}")
            row["ceiling"] = "true"
        print(row)
        writer.writerow(row)
    # take three extra measurements
    for i in range(3):
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
    return final_voltage


def find_hysteresis(instruments: list[Instrument], charger_voltage):
    if charger_voltage >= 5:
        ITRICKLE_COUNT = 4
    fluke, keithley = instruments
    set_battsim(keithley, 3.5)
    for v in range(VTRICKLE_COUNT):
        target_vtrickle = VTRICKLE_VALS[v]
        spmi_write(0x3, 0x63, [VTRICKLE_REGS[target_vtrickle]])
        for i in range(ITRICKLE_COUNT):
            target_itrickle = ITRICKLE_VALS[i]
            spmi_write(0x3, 0x63, [ITRICKLE_REGS[target_itrickle]])

            filename = fr"{PATH}\A.32_{datetime.now().strftime(f'%Y%m%d_%H_%M_%S-{charger_voltage}-{target_vtrickle}V_{target_itrickle}A')}.csv"
            with open(filename, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
                writer.writeheader()
                floor = step_down(instruments, writer, 3.8, target_itrickle)
                ceiling = step_up(instruments, writer, floor, target_itrickle)
                print(floor, ceiling)

            

def main():
    # scan_gpib()
    instruments = setup_instruments()
    setup_max77795()
    fluke, keithley = instruments
    print("Input the charge voltage you want to test (4.85, 5, 9, 15, 15.5)\n\n")
    CHARGE_VOLTAGE = float(input("Voltage: "))
    if(CHARGE_VOLTAGE not in CHARGER_VOLTAGES):
        CHARGE_VOLTAGE = int(input("Voltage: "))
    find_hysteresis(instruments=instruments, charger_voltage=CHARGE_VOLTAGE)
    # target_vtrickle = VTRICKLE_VALS[0]
    # target_itrickle = ITRICKLE_VALS[0]
    # filename = fr"{PATH}\A.28_{datetime.now().strftime(f'%Y%m%d_%H_%M_%S-{target_vtrickle}V_{target_itrickle}A')}.csv"
    # with open(filename, "w", newline="") as f:
    #     writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
    #     writer.writeheader()
    #     floor = step_down(instruments, writer, 3.8, target_itrickle, target_vtrickle)
    #     print(floor)



    # for instrument in instruments:
    #     instrument.close()
if __name__ == "__main__":
    main()