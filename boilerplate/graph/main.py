import glob
import csv
import re
import matplotlib.pyplot as plt

# CHGCC range in mA (from CHGCC(A) column * 1000)
CHGCC_MA = [
    150, 150, 150, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650,
    700, 750, 800, 850, 900, 950, 1000, 1050, 1100, 1150, 1200, 1250, 1300,
    1350, 1400, 1450, 1500, 1550, 1600, 1650, 1700, 1750, 1800, 1850, 1900,
    1950, 2000, 2050, 2100, 2150, 2200, 2250, 2300, 2350, 2400, 2450, 2500,
]
voltages = [5, 9, 15]


def parse_efficiency(val):
    return float(val.strip().replace("%", ""))


def get_identifier(filepath):
    match = re.search(r"([A-Z]\d{2})", filepath)
    return match.group(1) if match else ""


def find_header_row(rows, keyword):
    """Find the row index containing the keyword."""
    for i, row in enumerate(rows):
        for cell in row:
            if cell.strip().lower() == keyword.lower():
                return i
    return 0


def find_groups(header_row, eff_key="efficiency", x_key=None):
    """Find column groups by locating all efficiency columns and optional x columns."""
    groups = []
    for i, cell in enumerate(header_row):
        if cell.strip().lower() == eff_key:
            group = {"eff_col": i}
            # Look backwards for x_key column
            if x_key:
                for j in range(i - 1, -1, -1):
                    if header_row[j].strip().lower() == x_key:
                        group["x_col"] = j
                        break
            # Determine VCHGIN label from the vchgin column value (will be set later)
            for j in range(i - 1, -1, -1):
                if header_row[j].strip().lower() == "vchgin":
                    group["vchgin_col"] = j
                    break
            groups.append(group)
    print(groups)
    return groups


def get_vchgin_label(data_rows, vchgin_col):
    """Get VCHGIN voltage label from data."""
    for row in data_rows:
        if vchgin_col < len(row) and row[vchgin_col].strip():
            val = float(row[vchgin_col])
            return f"VCHGIN = {val:g}V"
    return "VCHGIN = ?V"


def plot_chgcc(filepath):
    identifier = get_identifier(filepath)
    with open(filepath, newline="") as f:
        rows = list(csv.reader(f))

    header_idx = find_header_row(rows, "efficiency")
    header_row = rows[header_idx]
    data_rows = rows[header_idx + 1:]

    groups = find_groups(header_row)
    if identifier == "A33":
        voltages[0] = 6.8
    else:
        voltages[0] = 5
    label_idx = 0
    for g in groups:
        efficiencies = []
        for row in data_rows:
            if g["eff_col"] < len(row) and row[g["eff_col"]].strip():
                efficiencies.append(parse_efficiency(row[g["eff_col"]]))
        label = f"VCHGIN = {voltages[label_idx]}V"

        plt.figure()
        plt.plot(CHGCC_MA[:len(efficiencies)], efficiencies, marker="o", markersize=3)
        plt.xlabel("CHGCC (mA)")
        plt.ylabel("Efficiency (%)")
        plt.title(f"{identifier} - Charging Current vs Efficiency ({label})")
        plt.minorticks_on()
        plt.grid(True, color="grey")
        plt.grid(which='major', linestyle='-', linewidth=1, color="black")
        plt.grid(which='minor', linestyle=':', linewidth=0.5, color="grey")
        plt.tight_layout()
        label_idx+=1


def plot_vbatt(filepath):
    identifier = get_identifier(filepath)
    with open(filepath, newline="") as f:
        rows = list(csv.reader(f))

    header_idx = find_header_row(rows, "efficiency")
    header_row = rows[header_idx]
    data_rows = rows[header_idx + 1:]
    label_idx = 0

    groups = find_groups(header_row, x_key="vbat")
    if identifier == "A33":
        voltages[0] = 6.8
    else:
        voltages[0] = 5

    for g in groups:
        vbat = []
        efficiencies = []
        for row in data_rows:
            if g["eff_col"] < len(row) and row[g["eff_col"]].strip():
                try:
                    vbat.append(float(row[g["x_col"]]))
                    efficiencies.append(parse_efficiency(row[g["eff_col"]]))
                except (ValueError, IndexError):
                    continue

        label = f"VCHGIN = {voltages[label_idx]}V"


        plt.figure()
        plt.plot(vbat, efficiencies, marker="o", markersize=3)
        plt.xlabel("VBATT (V)")
        plt.ylabel("Efficiency (%)")
        plt.title(f"{identifier} - Charging Voltage vs Efficiency ({label})")
        plt.minorticks_on()
        plt.grid(True)
        plt.grid(which='major', linestyle='-', linewidth=1, color="black")
        plt.grid(which='minor', linestyle=':', linewidth=0.5, color="grey")
        plt.tight_layout()
        label_idx += 1



def main():
    csv_files = glob.glob("*.csv")
    for f in csv_files:
        if "CHGCC" in f:
            plot_chgcc(f)
        elif "VBATT" in f:
            plot_vbatt(f)

    plt.show()


if __name__ == "__main__":
    main()
