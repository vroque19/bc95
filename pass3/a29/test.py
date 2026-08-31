import pyvisa

# Create a VISA resource manager
rm = pyvisa.ResourceManager()

# List all connected instruments
instruments = rm.list_resources()
print("Connected instruments:", instruments)

# Filter for GPIB instruments
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
