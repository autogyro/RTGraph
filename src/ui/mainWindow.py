import multiprocessing
import logging as log

from common.ringBuffer import RingBuffer
from processors.Serial import SerialProcess
from ui.mainWindow_ui import *
from ui.popUp import PopUp

JOIN_TIMEOUT_MS = 1000
PLOT_UPDATE_TIME_MS = 16  # 60 fps
""" http://www.gnuplotting.org/tag/palette/ """
COLORS = ['#0072bd', '#d95319', '#edb120', '#7e2f8e', '#77ac30', '#4dbeee', '#a2142f']


class MainWindow(QtGui.QMainWindow):
    def __init__(self, port=None, bd=115200, samples=500):
        QtGui.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # Shared variables, initial values
        self._plt = None
        self._timer_plot = None
        self._data_buffers = None
        self._time_buffer = None
        self._adquisition_process = None
        self.lines = 0
        self.queue = multiprocessing.Queue()

        # configures
        self._configure_plot()
        self._configure_timers()
        self._configure_signals()

        # populate combo box for serial ports
        speeds = SerialProcess.get_serial_ports_speeds()
        self.ui.cBox_Speed.addItems(speeds)
        try:
            self.ui.cBox_Speed.setCurrentIndex(speeds.index(str(bd)))
        except:
            log.warning("Adding rare speed value to the list")
            self.ui.cBox_Speed.addItem(str(bd))
            self.ui.cBox_Speed.setCurrentIndex(len(speeds))

        if port is None:
            ports = SerialProcess.get_serial_ports()
            if len(ports) > 0:
                self.ui.cBox_Port.addItems(ports)

        else:
            log.info("Setting user specified port {}".format(port))
            self.ui.cBox_Port.addItem(port)

        self.ui.sBox_Samples.setValue(samples)

        # enable ui
        self._enable_ui(True)

    def start(self):
        log.info("Clicked start")
        self._reset_buffers()
        port = self.ui.cBox_Port.currentText()
        self._adquisition_process = SerialProcess(self.queue)
        if self._adquisition_process.open_port(port=port, bd=int(self.ui.cBox_Speed.currentText())):
            self._adquisition_process.start()
            self._timer_plot.start(PLOT_UPDATE_TIME_MS)
            self._enable_ui(False)
        else:
            log.info("Port is not available")
            PopUp.warning(self, "RTGraph", "Selected port \"{}\" is not available"
                          .format(self.ui.cBox_Port.currentText()))

    def stop(self):
        log.info("Clicked stop")
        self._timer_plot.stop()
        self._enable_ui(True)
        if self._adquisition_process is not None and self._adquisition_process.is_alive():
            self._adquisition_process.stop()
            self._adquisition_process.join(JOIN_TIMEOUT_MS)
            self._reset_buffers()

    def closeEvent(self, evnt):
        if self._adquisition_process is not None and self._adquisition_process.is_alive():
            log.info("Window closed without stopping capture, stopping it")
            self.stop()

    def _enable_ui(self, enabled):
        self.ui.cBox_Port.setEnabled(enabled)
        self.ui.cBox_Speed.setEnabled(enabled)
        self.ui.pButton_Start.setEnabled(enabled)
        # self.ui.chBox_export.setEnabled(enabled)
        self.ui.pButton_Stop.setEnabled(not enabled)

    def _configure_plot(self):
        self.ui.plt.setBackground(background=None)
        self.ui.plt.setAntialiasing(True)
        self._plt = self.ui.plt.addPlot(row=1, col=1)
        self._plt.setLabel('bottom', 'Time', 's')

    def _configure_timers(self):
        self._timer_plot = QtCore.QTimer(self)
        self._timer_plot.timeout.connect(self._update_plot)

    def _configure_signals(self):
        self.ui.pButton_Start.clicked.connect(self.start)
        self.ui.pButton_Stop.clicked.connect(self.stop)
        self.ui.sBox_Samples.valueChanged.connect(self._update_sample_size)

    def _reset_buffers(self):
        samples = self.ui.sBox_Samples.value()
        self._data_buffers = []
        for tmp in COLORS:
            self._data_buffers.append(RingBuffer(samples))
        self._time_buffer = RingBuffer(samples)
        while not self.queue.empty():
            self.queue.get()
        log.info("Buffers cleared")

    def _update_sample_size(self):
        log.info("Changing sample size")
        self._reset_buffers()

    def _update_plot(self):
        while not self.queue.empty():
            data = self.queue.get(False)

            # add timestamp
            self._time_buffer.append(data[0])
            value = data[1]

            # detect how many lines are present to plot
            size = len(value)
            if self.lines < size:
                if size > len(COLORS):
                    self.lines = len(COLORS)
                else:
                    self.lines = size

            # store the data in respective buffers
            for idx in range(self.lines):
                self._data_buffers[idx].append(value[idx])

        # plot data
        self._plt.clear()
        for idx in range(self.lines):
            self._plt.plot(x=self._time_buffer.get_all(), y=self._data_buffers[idx].get_all(), pen=COLORS[idx])
