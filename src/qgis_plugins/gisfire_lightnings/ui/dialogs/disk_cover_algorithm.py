#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os.path

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt.QtWidgets import QWidget
from qgis.PyQt.QtWidgets import QLabel
from qgis.PyQt.QtWidgets import QComboBox
from qgis.PyQt.QtWidgets import QCheckBox
from qgis.PyQt.QtWidgets import QLineEdit
from qgis.PyQt.QtGui import QIntValidator

from typing import Union

class DlgDiskCoverAlgorithm(QDialog):
    """
    Dialog to select the disk cover algorithm
    """
    ALGORITHM_HAS_TIME_LIMIT = [
        False,
        False
    ]

    def __init__(self, parent: QWidget = None) -> None:
        """
        Constructor.
        """
        # Parent init
        super().__init__(parent)
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'disk_cover_algorithm.ui'), self)
        # Objects type hinting
        self.label_algorithm: QLabel
        self.label_use_time_limit: QLabel
        self.label_time_limit: QLabel
        self.combo_box_algorithm: QComboBox
        self.check_box_use_time_limit: QCheckBox
        self.line_edit_time_limit: QLineEdit
        # Objects init
        self.label_use_time_limit.setEnabled(False)
        self.label_time_limit.setEnabled(False)
        self.check_box_use_time_limit.setEnabled(False)
        self.line_edit_time_limit.setEnabled(False)
        only_int = QIntValidator()
        only_int.setRange(1, 360000)
        self.line_edit_time_limit.setValidator(only_int)

    def _on_combo_box_algorithm_changed(self):
        index = self.combo_box_algorithm.currentIndex()
        self.label_use_time_limit.setEnabled(DlgDiskCoverAlgorithm.ALGORITHM_HAS_TIME_LIMIT[index])
        self.label_time_limit.setEnabled(DlgDiskCoverAlgorithm.ALGORITHM_HAS_TIME_LIMIT[index])
        self.check_box_use_time_limit.setEnabled(DlgDiskCoverAlgorithm.ALGORITHM_HAS_TIME_LIMIT[index])
        self.line_edit_time_limit.setEnabled(DlgDiskCoverAlgorithm.ALGORITHM_HAS_TIME_LIMIT[index])

    @property
    def algorithm(self) -> int:
        return self.combo_box_algorithm.currentIndex()

    @property
    def use_time_limit(self) -> bool:
        return self.check_box_use_time_limit.isChecked()

    @property
    def time_limit(self) -> Union[int, None]:
        if self.check_box_use_time_limit.isChecked():
            return int(self.line_edit_time_limit.text())
        return None