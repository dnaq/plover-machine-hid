from copy import copy

from PyQt5.QtCore import QVariant, pyqtSignal
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QVBoxLayout,
    QCheckBox,
    QLabel,
    QLineEdit,
)


class HidOption(QGroupBox):

    valueChanged = pyqtSignal(QVariant)

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
        self.setters = []
        self._value = {}
        vbox = QVBoxLayout()
        vbox.addWidget(
            self.checkbox(
                name="first_up_chord_send",
                label="Send chord on first key release",
                tooltip="When the first key in a chord is released, the chord is sent.\n"
                "If the key is pressed and released again, another chord is sent.",
            )
        )
        vbox.addWidget(
            self.checkbox(
                name="double_tap_repeat",
                label="Double tap to repeat",
                tooltip="Tap and then hold a chord to send it repeatedly.",
            )
        )
        vbox.addLayout(
            self.number(
                name="repeat_delay_ms",
                label="Repeat delay (ms)",
                tooltip="Delay before chord starts repeating.",
                minimum=10,
                maximum=10000,
            )
        )
        vbox.addLayout(
            self.number(
                name="repeat_interval_ms",
                label="Repeat interval (ms)",
                tooltip="Interval between chord repetitions.",
                minimum=10,
                maximum=10000,
            )
        )
        self.setLayout(vbox)

    def setValue(self, value):
        self._value = copy(value)
        for setter in self.setters:
            setter(value)
