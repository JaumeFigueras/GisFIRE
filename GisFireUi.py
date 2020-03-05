from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt.QtWidgets import QDockWidget
from qgis.PyQt import uic

from PyQt5.QtCore import Qt
from PyQt5.QtCore import pyqtSignal
from PyQt5 import QtGui

import os.path
import os
from datetime import datetime

def get_ui_class(plugin_dir, ui_file_name):
    """ Get UI Python class from @ui_file_name """

    ui_file_path = plugin_dir + '/ui/' + ui_file_name
    if os.path.exists(ui_file_path):
        print("ignition point UI created")
        return uic.loadUiType(ui_file_path)[0]
    else:
        print ("File not found: " + ui_file_path)
        return None


FORM_CLASS = get_ui_class(os.path.dirname(__file__), 'ignition_point.ui')
class DlgIgnitionPoint(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setupUi(self)

    def getDateTime(self):
        qDate = self.mDateTimeEdit.dateTime()
        return qDate.toString(Qt.ISODate)

FORM_CLASS = get_ui_class(os.path.dirname(__file__), 'dock_control.ui')
class DockControl(QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    def __init__(self, parent=None):
        """Constructor."""
        super(DockControl, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://doc.qt.io/qt-5/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

    def closeEvent(self, event):
        event.accept()
