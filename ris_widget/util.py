# This code is licensed under the MIT License (see LICENSE file for details)

from . import ris_widget
import warnings
warnings.warn('util.input() is deprecated: use the .input() method of ris_widget.RisWidget instances', FutureWarning)

input = ris_widget.RisWidget.input