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
from plover import log

import hid
import platform

# This is a hack to not open the hid device in exclusive mode on
# darwin, if the version of hidapi installed is current enough
if platform.system() == "Darwin":
    import ctypes
    try:
        hid.hidapi.hid_darwin_set_open_exclusive.argtypes = (ctypes.c_int, )
        hid.hidapi.hid_darwin_set_open_exclusive.restype = None
        hid.hidapi.hid_darwin_set_open_exclusive(0)
    except AttributeError as e:
        log.error("hidapi < 0.12 in use, plover-hid will not work correctly")

USAGE_PAGE: int = 0xFF50
USAGE: int = 0x4C56

N_LEVERS: int = 64

# A simple report contains the report id 1 and one bit
# for each of the 64 buttons in the report.
SIMPLE_REPORT_TYPE: int = 0x01
SIMPLE_REPORT_LEN: int = N_LEVERS // 8

class InvalidReport(Exception):
    pass

STENO_KEY_CHART = ("S-", "T-", "K-", "P-", "W-", "H-",
                   "R-", "A-", "O-", "*", "-E", "-U",
                   "-F", "-R", "-P", "-B", "-L", "-G",
                   "-T", "-S", "-D", "-Z", "#",
                   "X1", "X2", "X3", "X4", "X5", "X6",
                   "X7", "X8", "X9", "X10", "X11", "X12",
                   "X13", "X14", "X15", "X16", "X17", "X18",
                   "X19", "X20", "X21", "X22", "X23", "X24",
                   "X25", "X26", "X27", "X28", "X29", "X30",
                   "X31", "X32", "X33", "X34", "X35", "X36",
                   "X37", "X38", "X39", "X40", "X41")

class HidMachine(ThreadedStenotypeBase):
    KEYS_LAYOUT: str = '''
        #  #  #  #  #  #  #  #  #  #
        S- T- P- H- *  -F -P -L -T -D
        S- K- W- R- *  -R -B -G -S -Z
              A- O-    -E -U
     X1  X2  X3  X4  X5  X6  X7  X8  X9  X10
     X11 X12 X13 X14 X15 X16 X17 X18 X19 X20
     X21 X22 X23 X24 X25 X26 X27 X28 X29 X30
     X31 X32 X33 X34 X35 X36 X37 X38 X39 X40
     X41
    '''
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
            return int.from_bytes(report[1:SIMPLE_REPORT_LEN+1], 'big')
        else:
            raise InvalidReport()

    def run(self):
        self._ready()
        keystate = 0
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
            if report == 0:
                steno_actions = self.keymap.keys_to_actions(
                    [key for i, key in enumerate(STENO_KEY_CHART) if keystate >> (63 - i) & 1]
                )
                if steno_actions:
                    self._notify(steno_actions)
                keystate = 0

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
