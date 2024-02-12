'''
A plover machine plugin for supporting the Plover HID protocol.

This protocol is a simple HID-based protocol that sends the current state
of the steno machine every time that state changes.

See the README for more details on the protocol.

The order of the buttons (from left to right) is the same as in `KEYS_LAYOUT`.
Most buttons have the same names as in GeminiPR, except for the extra buttons
which are called X1-X26.
'''

from copy import copy
from PyQt5.QtCore import QVariant, pyqtSignal
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import QGroupBox, QHBoxLayout, QVBoxLayout, QCheckBox, QLabel, QLineEdit

from plover.machine.base import ThreadedStenotypeBase
from plover import log
from plover.misc import boolean

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

    def send(self, keystate):
        steno_actions = self.keymap.keys_to_actions(
            [key for i, key in enumerate(STENO_KEY_CHART) if keystate >> (63 - i) & 1]
        )
        if steno_actions:
            self._notify(steno_actions)

    def run(self):
        self._ready()
        keystate = 0
        current = 0
        last_sent = 0
        repeat_timer = 0
        sent_first_up = False
        while not self.finished.wait(0):
            interval_ms = self._params["repeat_interval_ms"]
            try:
                report = self._hid.read(65536, timeout=interval_ms)
            except hid.HIDException:
                self._error()
                return
            if not report:
                # The set of keys pressed down hasn't changed. Figure out if we need to be sending repeats:
                if self._params["double_tap_repeat"] and 0 != current == last_sent:
                    if repeat_timer < self._params["repeat_delay_ms"]:
                        repeat_timer += interval_ms
                    else:
                        self.send(current)
                        # Avoid sending an extra chord when the repeated chord is released.
                        sent_first_up = True
                continue
            try:
                current = self._parse(report)
            except InvalidReport:
                continue

            repeat_timer = 0
            if self._params["first_up_chord_send"]:
                if keystate & ~current and not sent_first_up:
                    # A finger went up: send a first-up chord and remember it.
                    self.send(keystate)
                    last_sent = keystate
                    sent_first_up = True
                if current & ~keystate:
                    # A finger went down: get ready to send a new first-up chord.
                    sent_first_up = False
                keystate = current
            else:
                keystate |= current
                if current == 0:
                    # All fingers are up: send the "total" chord and reset it.
                    self.send(keystate)
                    last_sent = keystate
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
        return {
            "first_up_chord_send": (False, boolean),
            "double_tap_repeat": (False, boolean),
            "repeat_delay_ms": (200, int),
            "repeat_interval_ms": (50, int),
        }

class HidOption(QGroupBox):

    valueChanged = pyqtSignal(QVariant)
    setters = []

    def checkbox(self, name, label, tooltip):
        checkbox = QCheckBox(label)
        checkbox.setToolTip(tooltip)
        def on_changed(value):
            self._value[name] = value
            self.valueChanged.emit(self._value)
        checkbox.stateChanged.connect(on_changed)
        self.setters.append(lambda value: checkbox.setChecked(value[name]))
        return checkbox

    def number(self, name, label, tooltip, minimum, maximum):
        edit = QLineEdit("")
        edit.setToolTip(tooltip)
        edit.setValidator(QIntValidator(minimum, maximum, edit))
        def on_changed(value):
            self._value[name] = int(value)
            self.valueChanged.emit(self._value)
        edit.textChanged.connect(on_changed)
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addWidget(edit)
        self.setters.append(lambda value: edit.setText(str(value[name])))
        return row

    def __init__(self):
        super().__init__()
        self._value = {}
        vbox = QVBoxLayout()
        vbox.addWidget(self.checkbox("first_up_chord_send", "Send chord on first key release", "When the first key in a chord is released, the chord is sent.\nIf the key is pressed and released again, another chord is sent."))
        vbox.addWidget(self.checkbox("double_tap_repeat", "Double tap to repeat", "Tap and then hold a chord to send it repeatedly."))
        vbox.addLayout(self.number("repeat_delay_ms", "Repeat delay (ms)", "Delay before chord starts repeating.", 10, 10000))
        vbox.addLayout(self.number("repeat_interval_ms", "Repeat delay (ms)", "Interval between chord repetitions.", 10, 10000))
        self.setLayout(vbox)

    def setValue(self, value):
        self._value = copy(value)
        for setter in self.setters:
            setter(value)
