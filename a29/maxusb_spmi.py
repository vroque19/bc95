import sys, time, ftd2xx as ftd
"""
  Download and install libftd2xx (example for Linux x86_64):                                                                      
  wget https://ftdichip.com/wp-content/uploads/2022/07/libftd2xx-x86_64-1.4.27.tgz
  tar xzf libftd2xx-x86_64-1.4.27.tgz
  cd release/build
  sudo cp libftd2xx.so.1.4.27 /usr/local/lib/
  sudo ln -sf /usr/local/lib/libftd2xx.so.1.4.27 /usr/local/lib/libftd2xx.so
  sudo ldconfig
  LD_LIBRARY_PATH=/home/vroque/playground/bc95/a32-test/lib python main.py
"""
if sys.version_info > (3, 0):
    encode = lambda c: bytes([c])
    decode = lambda x: x
else:
    encode = chr
    decode = ord

class I2CError(Exception):  pass
class SPMIError(Exception):  pass

class MAXUSB:
    SPMI_SSC=b'\x80\x02\x03'*2 + b'\x80\x00\x03'*2
    SPMI_BIT1=b'\x80\x03\x03\x80\x02\x03'
    SPMI_BIT0=b'\x80\x01\x03\x80\x00\x03'
    SPMI_BP=b'\x80\x01\x03\x80\x00\x01'
    SPMI_BP2=b'\x80\x01\x01\x80\x00\x03'
    SPMI_READ=b'\x80\x01\x01\x80\x00\x01\x81'
    def __init__(self, spmi=False):
        self.device = None
        self.last_try = 0.0
        self.debug=[]
        self.retrymode=False
        print("MAXUSB init")
        try:
            self.connect()
            self.init_maxusb(spmi)
        except Exception as e:
            print("Could not connect MaxUSB")
            return
    def reconnect(self):
        self.connect()
        self.init_spmi() if self.spmi else self.init_tw()
    def findslaves(self):
        if self.spmi:
            raise IOError('in SPMI mode')
        def hello(saddr):
            try:  self.i2c_rdwr(saddr,[0],0,retry=0)
            except I2CError as e:  return -1
            return saddr
        saddrs = [hello(saddr) for saddr in range(0,0x100,2)]
        saddrs = [saddr for saddr in saddrs if saddr>0]
        return saddrs
    def connect(self):
        print("MAXUSB connect")
        if (time.time() - self.last_try) > 5.0: # Don't want to spam connection attempts
            self.last_try = time.time()
            numdevs=ftd.createDeviceInfoList()
            for index in range(numdevs):
                dtl=ftd.getDeviceInfoDetail(index)
                if b'Dual RS232-HS A' in dtl['description'] and len(dtl['serial']) == 1 and b'A' in dtl['serial']:#
                    dev = ftd.open(index)
                    dev.setDataCharacteristics(8,0,0)
                    dev.setFlowControl(0,17,19)
                    dev.setBaudRate(9600)
                    self.device=dev
                    break
        else:
            raise IOError('MAXUSB cooldown period')
        if not self.device:
            raise IOError('Unable to find a suitable FTDI device.')
        print("MAXUSB device")
        print(self.device)
    def init_maxusb(self, spmi):
        #see https://www.ftdichip.com/Support/Documents/AppNotes/AN_108_Command_Processor_for_MPSSE_and_MCU_Host_Bus_Emulation_Modes.pdf
        #for FTDI bit-banging commands/setup
        print("MAXUSB.init_maxusb()")
        self.spmi = spmi
        dev=self.device
        dev.setTimeouts(5000,5000)  ;   dev.setLatencyTimer(16)
        dev.setFlowControl(256,0,0) ;   dev.setBitMode(0,0)
        dev.setBitMode(0,2)         ;   bytes_available= dev.getQueueStatus()
        if bytes_available > 0:         bytes_read  = dev.read(bytes_available)
        dev.write(b'\xaa')          ;   rxbuf           = dev.read(2)
        if b'\xfa\xaa' not in rxbuf[:2]:raise IOError('Unexpected return value')
        dev.write(b'\xab')          ;   rxbuf           = dev.read(2)
        if b'\xfa\xab' not in rxbuf[:2]:raise IOError('Unexpected return value')
        self.clkdiv=b'\x31\x00'
        if spmi:
            dev.write(b'\x8a\x97\x8d\x86\x00\x00\x85\x80\x00\x03') 
            #0x8A: disable clk/5          ,     0x97: Disable adaptive clocking, 0x8D: Disable 3phase-data, 
            #0x86: Clock divisor=0 0x0000       0x80,0,3:  SDATA/SCLK drive low
        else:
            dev.write(b'\x8a\x97\x8c\x86\x31\x00\x85\x80\x00\x00') 
            #0x8A: disable clk/5          ,     0x97: Disable adaptive clocking, 0x8C,0x31,0x00: 3phase-data, 
            #0x86: Clock divisor=49 0x0031      0x80,0,0:  SDA/SCL goes high
    def setclock(self,clkdiv): #Set alternate clock speeds
        dev=self.device
        dev.write(b'\x86'+clkdiv)
        self.clkdiv=clkdiv
    def i2c_rdwr(self, saddr, wrdata, rdcount,delay=False,retry=0): #Perform low-level reads/writes
        if self.spmi:
            raise IOError('in SPMI mode')
        dev     = self.device
        slow_clk = fast_clk = b''
        clkdiv =self.clkdiv
        if(type(delay) is not bool):  
            clkdiv=delay
            delay=True
        if delay:  slow_clk,fast_clk     = b'\x86\x00\x03',b'\x86'+self.clkdiv
        # if delay:   slow_clk,fast_clk  = b'\x86\x00\x03',b'\x86\x32\x00'
        txstr                            = b'\x80\x00\x00'*6 + b'\x80\x00\x02'*6 + b'\x80\x00\x03' # start:        (SCL/SDA hi)*6, SDA_Lo*6, SCL_Lo*6
        if wrdata:
            txstr                       += b'\x80\x00\x03\x11\x00\x00' + encode(saddr & 0xfe) + b'\x80\x00\x01\x22\x00\x87' # saddr
            # data bytes                      SDA/SCL Lo  Byte-out        slave-address              SDA Hi     bit-in  flushbuffer
            for byte in wrdata: txstr   += b'\x80\x00\x03\x11\x00\x00' + encode(byte)         + b'\x80\x00\x01'+slow_clk+b'\x22\x00'+fast_clk+b'\x87' # write data
            # data bytes                      SDA/SCL Lo  Byte-out        byte                       SDA Hi     bit-in  flushbuffer
        if rdcount > 0:
            if wrdata:          txstr   += b'\x80\x00\x00'*36 + b'\x80\x00\x02'*6 + b'\x80\x00\x03' # repeat start (SCL/SDA hi)*36 SDA_Lo*6, SCL_Lo*3
            txstr                       += b'\x80\x00\x03\x11\x00\x00' + encode(saddr | 0x01) + b'\x80\x00\x01'+slow_clk+b'\x22\x00'+fast_clk+b'\x87' # saddr
            # data bytes                      SDA/SCL Lo  Byte-out        slave-address              SDA Hi     bit-in  flushbuffer
            for i in range(rdcount):
                txstr                   += b'\x80\x00\x01\x20\x00\x00\x80\x00\x03'+slow_clk+b'\x13\x00' # read data
                txstr                   += b'\xff' if i == (rdcount-1) else b'\x00' # ack bit
                txstr                   += slow_clk+b'\x80\x00\x01'+fast_clk+b'\x87' # finish read byte
        txstr                           += b'\x80\x00\x03'*6 + b'\x80\x00\x02'*6 + b'\x80\x00\x00'*6 # stop
        rxlen   = (1 + len(wrdata) if wrdata else 0) + (1 + rdcount if rdcount else 0)
        try:
            while(True): 
                dev.write(txstr)
                timeout = 10.0 + 0.025 * (len(wrdata) + rdcount) 
                if delay: timeout *= 2
                while True:
                    time.sleep(0.001)
                    timeout -= 1
                    bytes_available=dev.getQueueStatus()
                    if bytes_available >= rxlen:    break
                    elif timeout < 0:               break
                if timeout < 0:                     raise IOError('Read timed out')
                rxbuf   = dev.read(bytes_available)
                rddata  = [decode(c) for c in rxbuf]#[:bytes_read.value]]
                #if bytes_read.value < rxlen:            raise IOError('Expected %d bytes, got %d' % (rxlen, bytes_read.value))
                if any([b & 0x01 for b in rddata[bytes_available-rxlen:bytes_available-rdcount]]):#[bytes_read.value-rxlen:bytes_read.value-rdcount]]):
                    # print('rddata,rdcount,rxlen,bytes_available = ',rddata,rdcount,rxlen,bytes_available)
                    # print('txstr=',txstr) ; 
                    # print('wrdata=',wrdata)#[bytes_read.value-rxlen:bytes_read.value-rdcount])
                    retry-=1
                    if(retry>0):
                        print('!',end="")
                        time.sleep(0.05)
                        continue
                    else:
                        raise I2CError('NACK received on slave address ' + hex(saddr))
                return rddata[-rdcount:] if rdcount else []
        except IOError as e:
            print(e)
            return
    def _spmi_ext_reg_base(self, saddr, regaddr, arg, delay=False, retry=0):
        dev = self.device
        if type(arg) is list:
            count = len(arg)
            write = True
        else:
            count = arg
            write = False     
        txstr = self.SPMI_SSC
        cframe = f'{saddr&0xF:04b}{"0000" if write else "0010"}{count-1:04b}'
        cframe += '0' if cframe.count('1') % 2 else '1'
        txstr += b''.join([self.SPMI_BIT1 if c == '1' else self.SPMI_BIT0 for c in cframe]) # command frame
        regaddr = f'{regaddr&0xFF:08b}'
        regaddr += '0' if regaddr.count('1') % 2 else '1'
        txstr += b''.join([self.SPMI_BIT1 if c == '1' else self.SPMI_BIT0 for c in regaddr]) # register address
        if write:
            for byte in arg:
                data = f'{byte&0xFF:08b}'
                data += '0' if data.count('1') % 2 else '1'
                txstr += b''.join([self.SPMI_BIT1 if c == '1' else self.SPMI_BIT0 for c in data]) # register data
        txstr += self.SPMI_BP + (1 if write else 9 * count) * self.SPMI_READ + self.SPMI_BP2 + b'\x87'
        try:
            while(True): 
                dev.write(txstr)
                timeout = 10.0 + 0.025 * count
                if delay: timeout *= 2
                while True:
                    time.sleep(0.001)
                    timeout -= 1
                    bytes_available=dev.getQueueStatus()
                    if bytes_available >= 1:        break
                    elif timeout < 0:               break
                if timeout < 0:                     raise IOError('Read timed out')
                rxbuf   = dev.read(bytes_available)
                rddata  = ['1' if decode(c) & 0x02 else '0' for c in rxbuf]
                if write:
                    if rddata[0] != '1':
                        retry-=1
                        if(retry>0):
                            print('!',end="")
                            time.sleep(0.05)
                            continue
                        else:
                            return False
                    return True
                else:
                    rdbytes = [int(''.join(rddata[i:i+8]),2 ) for i in range(0, len(rddata), 9)]
                    if not all([''.join(rddata[i:i+9]).count('1') % 2 for i in range(0, len(rddata), 9)]):
                        print('SPMI read parity error')
                    return rdbytes
        except IOError as e:
            print(e)
    def spmi_ext_reg_wr(self, saddr, regaddr, wrdata, delay=False, retry=0): #Perform extended register write
        if not self.spmi:
            raise IOError('in I2C mode')
        if not type(wrdata) is list:
            raise SPMIError('wrdata expecting a list')
        if len(wrdata) > 16 or len(wrdata) == 0:
            raise SPMIError('wrdata length must be between 1 and 16 ')
        return self._spmi_ext_reg_base(saddr, regaddr, wrdata, delay, retry)
    def spmi_ext_reg_rd(self, saddr, regaddr, rdcount, delay=False, retry=0): #Perform extended register write
        if not self.spmi:
            raise IOError('in I2C mode')
        if rdcount > 16 or rdcount < 1:
            raise SPMIError('rdcount length must be between 1 and 16 ')
        return self._spmi_ext_reg_base(saddr, regaddr, rdcount, delay, retry)
"""

  1. Start sequence (line 166): Sends SPMI_SSC — the SPMI bus start condition (sequence of clock/data transitions).
  2. Command frame (lines 167-169): Builds a 13-bit binary string:
    - Bits [12:9]: saddr (4-bit slave ID)
    - Bits [8:5]: 0010 — the SPMI opcode for extended register read
    - Bits [4:1]: rdcount - 1 (byte count, zero-indexed)
    - Bit [0]: odd parity over the 12 data bits

  Each bit is encoded as SPMI_BIT1 or SPMI_BIT0 (bit-bang sequences that toggle SDATA/SCLK via FTDI).
  3. Register address (lines 170-172): 8-bit address + odd parity bit, same bit-bang encoding.
  4. Bus park + read clocks (line 178): Sends a bus park (SPMI_BP), then 9 * rdcount read clock cycles (SPMI_READ) — 9 bits per byte
  (8 data + 1 parity). Ends with SPMI_BP2 and a flush (0x87).
"""
maxusb = MAXUSB(True)

def ww(sa, ra, d):
     maxusb.i2c_rdwr(sa, [ra, d%256, d/256], 0)

def rw(sa, ra):
     d = maxusb.i2c_rdwr(sa, [ra], 2)
     return hex(d[0] + d[1]*256)
