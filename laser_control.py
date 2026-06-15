import serial
import time
import serial.tools.list_ports as stlp

class LaserRelay :
    """
    Controls the USB relay to turn laser on and off
    """

    def __init__(self, baudrate=9600, timeout=0.5, device_hint="CP210x"): 
        self.baudrate = baudrate
        self.timeout = timeout
        self.device_hint = device_hint
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

        portname = self.find_port()

        if portname is None : 
            raise RuntimeError("Laser relay device not found")
        
        self.ser = serial.Serial(portname, self.baudrate, timeout=self.timeout)

        if not self.ser.is_open : 
            raise RuntimeError("Could not open laser relay serial port")
        
        print(f"Laser relay connected on {self.ser.name}")

        self.off()

    def on(self) : 
        """
        Turn relay on
        """

        if self.ser is None or not self.ser.is_open : 
            raise RuntimeError("Laser relay is not open")
        
        self.ser.write(b"AT+CH1=1")

    def off(self) : 
        """
        Turn relay channel 1 off
        """
        
        if self.ser is None or not self.ser.is_open : 
            raise RuntimeError("Laser relay is not open")
        
        self.ser.write(b"AT+CH1=0")

    def close(self) : 
        """
        Turn laser off and close serial connection
        """

        if self.ser is not None and self.ser.is_open : 
            try : 
                self.off()
                time.sleep(0.1)
            finally : 
                self.ser.close()
                print("Laser relay closed")