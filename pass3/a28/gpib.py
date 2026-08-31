import pyvisa
import numpy as np

KEITHLEY_2306 = 'GPIB0::16::INSTR'    # Battery simulator
FLUKE_8845A = 'GPIB0::24::INSTR'     # Battery voltage DMM


class Instrument:
    def __init__(self, resource_manager, addr: str):
        self.device = resource_manager.open_resource(addr)
        self.addr = addr

    def configure(self, command: str) -> None:
        """Send a SCPI command (write)."""
        self.device.write(command)

    def query(self, command: str) -> str:
        """Send a SCPI query and return the raw response."""
        return self.device.query(command)

    def read_avg(
        self,
        query_cmd: str,
        samples: int = 3,
        parse: str = 'float',
        round_digits: int | None = None,
    ) -> float:
        """Generic N-sample average reader.

        Parameters
        ----------
        query_cmd:
            SCPI query to execute each sample.
        samples:
            Number of samples to average.
        parse:
            'float'    -> response is a single float
            'keithley' -> response is semicolon-delimited; first token is the value
        round_digits:
            If provided, rounds each sample before averaging.
        """
        readings: list[float] = []

        for _ in range(samples):
            raw = self.query(query_cmd)

            if parse == 'keithley':
                # Example: "5.000192E+00;5.000192E+00" -> take first token
                val = float(raw.strip().split(';')[0])
            else:
                val = float(raw)

            if round_digits is not None:
                val = round(val, round_digits)

            readings.append(val)

        return float(np.mean(readings))

    def close(self) -> None:
        self.device.close()


def setup_instruments()-> list:
    """Open all instruments and put them in a known configuration."""
    rm = pyvisa.ResourceManager()

    battsim = Instrument(rm, KEITHLEY_2306)
    dmm = Instrument(rm, FLUKE_8845A)

    dmm.configure('*RST; :CONF:CURR:DC 10')  # 10A range

    # 2461: known-good state for 4-wire sense + voltage source; keep output OFF by default

    return [dmm, battsim]


def read_agilent(voltmeter: Instrument, digits: int = 6, samples: int = 3) -> float:
    return round(voltmeter.read_avg('READ?', samples=samples, parse='float'), digits)


def read_fluke(currentmeter: Instrument, digits: int = 6, samples: int = 3) -> float:
    return round(currentmeter.read_avg('READ?', samples=samples, parse='float'), digits)

def read_keithley_2306(battsim: Instrument, digits: int = 6, samples: int = 3) -> float:
    return round(battsim.read_avg("MEAS:CURR?", samples, "float"), digits)

def set_keithley_2306(battsim: Instrument, voltage: float, output_on: bool = True) -> None:
    """Set 2306 battery simulator voltage and (optionally) enable output."""
    battsim.configure(f'SOUR:VOLT {voltage}')
    if output_on:
        battsim.configure('OUTP ON')


def read_keithley(sourcemeter: Instrument, mode: str, digits: int = 6, samples: int = 3) -> float:
    """Read voltage or current from the 2461 and return an N-sample average."""
    mode_map = {
        'voltage': ':SENS:FUNC "VOLT"; :MEAS:VOLT?; :FETCh?',
        'current': ':SENS:FUNC "CURR"; :MEAS:CURR?; :FETCh?',
    }

    query_cmd = mode_map.get(mode.lower())
    if query_cmd is None:
        raise ValueError("mode must be 'voltage' or 'current'")

    val = sourcemeter.read_avg(query_cmd, samples=samples, parse='keithley')
    return round(val, digits)


def set_keithley(sourcemeter: Instrument, voltage: float, output_on: bool = True) -> None:
    """Set 2461 to source a voltage and (optionally) enable output."""
    state = 'ON' if output_on else 'OFF'
    sourcemeter.configure(f':SOUR:FUNC VOLT; :SOUR:VOLT {voltage}; :OUTP {state}')


def set_battsim(battsim: Instrument, voltage: float, output_on: bool = True) -> None:
    """Set 2306 battery simulator voltage and (optionally) enable output.

    NOTE: If your 2306 uses a different command than 'OUTP ON', change it here.
    """
    battsim.configure(f'SOUR:VOLT {voltage}')
    if output_on:
        battsim.configure('OUTP ON')


def scan_gpib() -> None:
    rm = pyvisa.ResourceManager()
    resources = rm.list_resources()
    print('Connected instruments:', resources)

    gpib_resources = [r for r in resources if 'GPIB' in r]
    if not gpib_resources:
        print('No GPIB instruments found.')
        return

    for address in gpib_resources:
        print(f'Connecting to {address}...')
        instrument = None
        try:
            instrument = rm.open_resource(address)
            idn = instrument.query('*IDN?')
            print(f'Instrument at {address} responded with ID: {idn}')
        except Exception as e:
            print(f'Failed to communicate with {address}: {e}')
        finally:
            try:
                if instrument is not None:
                    instrument.close()
            except Exception:
                pass
