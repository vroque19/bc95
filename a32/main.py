from gpib import Instrument, read_agilent, read_fluke, read_keithley, setup_instruments, set_keithley, set_battsim, scan_gpib
import time
import csv
from datetime import datetime
from maxusb_spmi import maxusb

vchgin_levels = [5]
Battery_CV_Voltage = 4.2
Battery_CC_Voltage = 2.7
MAX_CHARGE_CURRENT = 0b110010 + 1 # max is 50/ 0x33
CSV_HEADERS = ["timestamp", "CHGCC", "vbat", "ibat", "vchgin", "ichgin", "efficiency"]
SPMI_SLAVE_ID = 0x03 #
PATH=r'C:\Users\JRedhair\Documents\BC95_Efficiency'
VCHGIN = "vchgin"
WCIN = "wcin"

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
    
def regulate_battsim_voltage(
    battsim: Instrument,
    agilent: Instrument,
    target_v: float,
    current_setpoint: float,
    tol: float = 0.005,          # 5 mV deadband
    kp: float = 0.6,             # proportional gain (Vset change per V error)
    max_step: float = 0.050,     # max 50 mV per adjustment
    min_step: float = 0.001,     # min 1 mV to ensure progress when error is small
    settle_s: float = 0.20,      # settle time after changing setpoint
    max_iters: int = 50,
    min_setpoint: float = 0.0,
    max_setpoint: float = 6.0,
    verbose: bool = False,
):
    """
    Closed-loop trim: adjust battsim setpoint so Agilent VBAT -> target_v.
    Nudge DOWN if VBAT high, UP if VBAT low.
    Returns: (measured_vbat, updated_setpoint, iterations_used, success_bool)
    """
    setpoint = float(current_setpoint)

    for n in range(max_iters):
        v_meas = float(read_agilent(agilent))
        err = target_v - v_meas  # positive means VBAT is low => increase setpoint

        # Within deadband? Done.
        if abs(err) <= tol:
            return v_meas, setpoint, n, True

        # Proportional step toward reducing error
        raw_step = kp * err

        # Enforce minimum step magnitude (but keep sign)
        if abs(raw_step) < min_step:
            step = min_step if raw_step > 0 else -min_step
        else:
            step = raw_step

        # Clamp step to max_step magnitude
        if step > max_step:
            step = max_step
        elif step < -max_step:
            step = -max_step

        # Apply and clamp setpoint
        new_setpoint = setpoint + step
        new_setpoint = max(min_setpoint, min(max_setpoint, new_setpoint))

        if verbose:
            print(
                f"[battsim trim] v_meas={v_meas:.4f}V, target={target_v:.4f}V, "
                f"err={err:+.4f}V, step={step:+.4f}V => setpoint={new_setpoint:.4f}V"
            )

        # If clamped and cannot move further, abort to avoid infinite loop
        if new_setpoint == setpoint:
            return v_meas, setpoint, n, False

        setpoint = new_setpoint
        set_battsim(battsim, setpoint)
        time.sleep(settle_s)

    # Timeout
    v_meas = float(read_agilent(agilent))
    return v_meas, setpoint, max_iters, False

def read_all_data(csv_writer, instruments: list[Instrument], chgcc: int):
    agilent, fluke, keithley, *_ = instruments
    vbat, ibat, vchgin, ichgin = read_agilent(agilent), read_fluke(fluke), read_keithley(keithley, "voltage"), read_keithley(keithley, "current")
    efficiency = (vbat * ibat) / (vchgin * ichgin)
    row = {
        "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "CHGCC": hex(chgcc),
        "vbat": vbat,
        "ibat": ibat,
        "vchgin": vchgin,
        "ichgin": ichgin,
        "efficiency": efficiency
    }
    print(row)
    csv_writer.writerow(row)


# for every vchgin, go through all fast charge current modes and get readings
def get_efficiency(vchgin: float, csv_writer, instruments: list[Instrument], target_vbat: float = 4.2):
    agilent, fluke, keithley, battsim = instruments
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

    # Track the last setpoint commanded to battsim
    battsim_setpoint = target_vbat
    set_battsim(battsim, battsim_setpoint)

    for i in range(MAX_CHARGE_CURRENT):
        keithley.configure(":OUTP OFF")
        time.sleep(0.5)

        set_chgcc(i)
        time.sleep(0.5)

        keithley.configure(":OUTP ON")
        time.sleep(2) # wait for current to settle

        v_meas, battsim_setpoint, n, ok = regulate_battsim_voltage(
            battsim=battsim,
            agilent=agilent,
            target_v=target_vbat,
            current_setpoint=battsim_setpoint,
            tol=0.005,
            kp=0.6,
            max_step=0.05,
            settle_s=0.2,
            max_iters=50,
            min_setpoint=0.0,
            max_setpoint=5.5,
            verbose=False,
        )
        if not ok:
            print(f"WARNING: VBAT regulation did not converge. vbat={v_meas:.4f}V, setpoint={battsim_setpoint:.4f}V, CHGCC={i}")

        time.sleep(1) # Wait for settling
        read_all_data(csv_writer, instruments, i)
        time.sleep(0.5)

    keithley.configure("OUTP OFF")
    

# ----------------------------
# Voltage test sequence
# Stepping through 5V, 9V, and 12V
# ----------------------------
def run_tests(instruments: list[Instrument]=[]):
    for level in vchgin_levels:
        set_keithley(instruments[2], level) # set the vchgin level
        filename = fr"{PATH}\A.32_{datetime.now().strftime(f'%Y%m%d_%H_%M_%S-{level}V')}.csv" # create the csv
        with open(filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            get_efficiency(level, writer, instruments)

def setup_max77795(chgin: str = "vcin"):
    # ----------------------------
# SPMI setup for CHGIN
# 0x3 is SPMI SID for Charger portion of BC95
# ----------------------------
    spmi_write(0x3, 0x56, [0x0C])  # Unlock charger in cfg_6
    spmi_write(0x3, 0x52, [0x33])  # Fast Charging Current = 2.5A cfg_2
    spmi_write(0x3, 0x54, [0x37])  # Termination Voltage = 4530mV cfg_4
    spmi_write(0x3, 0x59, [0xFF])  # Charge Current limit for CHGIN cfg_9
    spmi_write(0x3, 0x5A, [0x7F])  # Charge Current limit for WCIN cfg_10
    spmi_write(0x3, 0x50, [0x05])  # Charge mode = 0x5

    # spmi_read_hex(0x3, 0x56, 1) # Reads config 6
    if chgin == "wcin":
        spmi_write(0x3, 0x67, [0x4E]) # enable inlim cont & dynamic floor cfg_23

def test_keithley(keithley: Instrument):
    
    # keithley.configure("*RST;*CLS")
    # keithley.configure(":SOUR:FUNC VOLT")
    # keithley.configure(":SYST:RSEN ON")      # <-- remote sense (4-wire)
    # keithley.configure(":OUTP ON")

    v = read_keithley(keithley, "voltage")
    i = read_keithley(keithley, "current")
    print(f"voltage: {v}V - current: {i}A")
    print()

def main():
    instruments = setup_instruments()
    setup_max77795(VCHGIN)
    agilent, fluke, keithley, battsim = instruments
    # test_keithley(keithley=keithley)

    print(instruments)
    run_tests(instruments=instruments)
    # ----------------------------
    # Cleanup to close GPIB comms
    # ----------------------------
    for instrument in instruments:
        instrument.close()

if __name__ == "__main__":
    main()