'''
A plover machine plugin for supporting the Plover HID protocol.

This protocol is a simple HID-based protocol that sends the current state
of the steno machine every time that state changes.

See the README for more details on the protocol.

The order of the buttons (from left to right) is the same as in `KEYS_LAYOUT`.
Most buttons have the same names as in GeminiPR, except for the extra buttons
which are called X1-X26.
'''
from plover.machine.base import ThreadedStenotypeBase

from bitstring import BitString
import hid

USAGE_PAGE: int = 0xFF50
USAGE: int = 0x4C56

N_LEVERS: int = 64

# A simple report contains the report id 1 and one bit
# for each of the 64 buttons in the report.
SIMPLE_REPORT_TYPE: int = 0x01
SIMPLE_REPORT_LEN: int = N_LEVERS // 8

class InvalidReport(Exception):
    pass

class HidMachine(ThreadedStenotypeBase):
    KEYS_LAYOUT: str = """
        #1  #2 #3 #4 #5 #6 #7 #8 #9 #A #B #C
        X1 S1- T- P- H- *1 *3 -F -P -L -T -D
        X2 S2- K- W- R- *2 *4 -R -B -G -S -Z
               X3 A- O-       -E -U X4

     X5  X6  X7  X8  X9  X10 X11 X12 X13 X14 X15
     X16 X17 X18 X19 X20 X21 X22 X23 X24 X25 X26
    """
    STENO_KEY_MAP: [str] = KEYS_LAYOUT.split()

    def __init__(self, params):
        super().__init__()
        self._params = params
        self._hid = None

    def _parse(self, report):
        # The first byte is the report id, and due to idiosynchrasies
        # in how HID-apis work on different operating system we can't
        # map the report id to the contents in a good way, so we force
        # compliant devices to always use a report id of 0x50 ('P').
        if len(report) > SIMPLE_REPORT_LEN and report[0] == 0x50:
            return BitString(report[1:SIMPLE_REPORT_LEN+1])
        else:
            raise InvalidReport()

    def run(self):
        self._ready()
        keystate = BitString(N_LEVERS)
        while not self.finished.wait(0):
            try:
                report = self._hid.read(65536, timeout=1000)
            except hid.HIDException:
                self._error()
                return
            if not report:
                continue
            try:
                report = self._parse(report)
            except InvalidReport:
                continue
            keystate |= report
            if not report:
                steno_actions = self.keymap.keys_to_actions(
                    [self.STENO_KEY_MAP[i] for (i, x) in enumerate(keystate) if x]
                )
                if steno_actions:
                    self._notify(steno_actions)
                keystate = BitString(N_LEVERS)

    def start_capture(self):
        self.finished.clear()
        self._initializing()
        # Enumerate all hid devices on the machine and if we find one with our
        # usage page and usage we try to connect to it.
        try:
            devices = [
                device["path"]
                for device in hid.enumerate()
                if device["usage_page"] == USAGE_PAGE and device["usage"] == USAGE
            ]
            if not devices:
                self._error()
                return
            # FIXME: if multiple compatible devices are found we should either
            # let the end user configure which one they want, or support reading
            # from all connected plover hid devices at the same time.
            self._hid = hid.Device(path=devices[0])
        except hid.HIDException:
            self._error()
            return
        self.start()

    def stop_capture(self):
        super().stop_capture()
        if self._hid:
            self._hid.close()
            self._hid = None

    @classmethod
    def get_option_info(cls):
        return {}
