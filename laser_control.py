import serial
import time
import serial.tools.list_ports as stlp

class LaserRelay :
    """
    Controls the USB relay to turn laser on and off
    """

    def __init__(self, baudrate=9600, timeout=0.5, device_hint="CP210x", port=None): 
        self.baudrate = baudrate
        self.timeout = timeout
        self.device_hint = device_hint
        self.port = port      # None = auto-detect, string = fixed port
        self.ser = None

    def find_port(self) :
        """
        Search connected serial devices for the relay
        """

        ports_list = list(stlp.comports())

        for comport in ports_list : 
            if self.device_hint in comport.description : 
                return comport.device
        
        return None
        
    def open(self) : 
        """
        Open serial connection to relay
        """

        if self.port : 
            portname = self.port
        else : 
            portname = self.find_port()

        if portname is None : 
            raise RuntimeError("Laser relay device not found.")
        
        try :
            self.ser = serial.Serial(portname, self.baudrate, timeout=self.timeout)

        except Exception as error : 
            raise RuntimeError(f"Could not open laser relay serial port: {error}")

        if not self.ser.is_open : 
            raise RuntimeError("Could not open laser relay serial port")
        
        self.off()

    def on(self) : 
        """
        Turn relay on
        """

        # Check if serial connection does not exist or is not open
        if self.ser is None or not self.ser.is_open : 
            raise RuntimeError("Laser relay is not open")
        
        try : 
            self.ser.write(b"AT+CH1=1")
            # Force serial buffer to send immediately
            self.ser.flush()

        except Exception as error : 
            raise RuntimeError(f"Laser relay ON command failed: {error}")

    def off(self) : 
        """
        Turn relay channel 1 off
        """
        
        if self.ser is None or not self.ser.is_open : 
            raise RuntimeError("Laser relay is not open")
        
        try :
            self.ser.write(b"AT+CH1=0")
            self.ser.flush() # Immediate serial buffer send
        
        except Exception as error :
            raise RuntimeError(f"Laser relay OFF command failed: {error}") 

    def reconnect(self) :
        """
        Close (if open) and re-open the serial connection to the relay.

        Used to recover from a transient USB/serial glitch on a long run so a
        single momentary fault doesn't abort the whole experiment. Re-detects
        the port via open() when no fixed port was configured. Raises
        RuntimeError if the relay still can't be opened.
        """

        if self.ser is not None :
            try :
                self.ser.close()
            except Exception :
                pass
            finally :
                self.ser = None

        # open() re-detects the port and raises RuntimeError on failure.
        self.open()

    def close(self) :
        """
        Turn laser off and close serial connection
        """

        if self.ser is not None and self.ser.is_open :
            try :
                self.off()
                time.sleep(0.1) # This is needed to give enough time to safely turn off and close the relay
            finally :
                self.ser.close()