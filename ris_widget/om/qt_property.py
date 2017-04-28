# The MIT License (MIT)
#
# Copyright (c) 2015 WUSTL ZPLAB
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Authors: Erik Hvatum <ice.rikh@gmail.com>

import numpy
from PyQt5 import Qt

def _equals(a, b):
    r = a == b
    if isinstance(r, (bool, numpy.bool_)):
        return bool(r)
    return all(r)

class Property(property):
    """A convenience class for making properties that have a default value and a change Qt-signal.

    NB: Property is derived from "property" for the sole reason that IPython's question-mark magic is special-cased for
    properties.  Deriving from property causes Property to receive the same treatment, providing useful output for
    something.prop? in IPython (where prop is a Property instance)."""
    def __init__(self, default_value, coerce_arg_fn=None, pre_set_callback=None, post_set_callback=None, doc=None):
        self.default_value = default_value
        self.coerce_arg_fn = coerce_arg_fn
        self.pre_set_callback = pre_set_callback
        self.post_set_callback = post_set_callback
        if doc is not None:
            self.__doc__ = doc

    def _init_names(self, name):
        self.var_name = '_' + name
        self.default_val_var_name = '_default_' + name
        self.changed_signal_name = name + '_changed'

    def _get_default_val(self, obj):
        if callable(self.default_value):
            return self.default_value(obj)
        else:
            return self.default_value

    def _attach(self, obj):
        default = self._get_default_val(obj)
        setattr(obj, self.default_val_var_name, default)
        if hasattr(obj, 'changed') and isinstance(obj.changed, Qt.pyqtBoundSignal):
            getattr(obj, self.changed_signal_name).connect(obj.changed)

    def _update_default(self, obj):
        if hasattr(obj, self.var_name):
            # An explicitly set value is overriding the default, so even if the default has changed, the apparent value of the property has not
            setattr(obj, self.default_val_var_name, self._get_default_val(obj))
        else:
            # The default value is the apparent value, meaning that we must check if the default has changed and signal an apparent value change
            # if it has
            old_default = getattr(obj, self.default_val_var_name)
            new_default = self._get_default_val(obj)
            if not _equals(new_default, old_default):
                setattr(obj, self.default_val_var_name, new_default)
                return getattr(obj, self.changed_signal_name)

    def __get__(self, obj, type=None):
        if obj is None:
            return self
        try:
            return getattr(obj, self.var_name)
        except AttributeError:
            return getattr(obj, self.default_val_var_name)

    def __set__(self, obj, v):
        if self.coerce_arg_fn is not None:
            v = self.coerce_arg_fn(v)
        if not hasattr(obj, self.var_name) or not _equals(v, getattr(obj, self.var_name)):
            if self.pre_set_callback is not None:
                if self.pre_set_callback(obj, v) == False:
                    return
            setattr(obj, self.var_name, v)
            if self.post_set_callback is not None:
                self.post_set_callback(obj, v)
            getattr(obj, self.changed_signal_name).emit(obj)

    def __delete__(self, obj):
        """Reset to default value by way of removing the explicitly set override, causing the apparent value to be default."""
        if not hasattr(obj, self.var_name):
            return
        old_value = getattr(obj, self.var_name)
        delattr(obj, self.var_name)
        default = getattr(obj, self.default_val_var_name)
        if not _equals(old_value, default):
            if self.post_set_callback is not None:
                self.post_set_callback(obj, default)
            getattr(obj, self.changed_signal_name).emit(obj)

    def is_default(self, obj):
        if not hasattr(obj, self.var_name):
            return True
        val = getattr(obj, self.var_name)
        def_val = getattr(obj, self.default_val_var_name)
        return _equals(val, def_val)

class QtPropertyOwnerMeta(type(Qt.QObject)):
    def __new__(mcs, name, bases, classdict):
        properties = {}
        for k, v in list(classdict.items()):
            if isinstance(v, Property):
                v._init_names(k)
                classdict[v.changed_signal_name] = Qt.pyqtSignal(object)
                properties[k] = v
        classdict['_properties'] = properties
        return super().__new__(mcs, name, bases, classdict)

class QtPropertyOwner(Qt.QObject, metaclass=QtPropertyOwnerMeta):
    def __init__(self, parent=None):
        super().__init__(parent)
        for prop in self._properties.values():
            prop._attach(self)

    def _update_property_defaults(self):
        signals_to_emit = []
        for prop in self._properties.values():
            signal = prop._update_default(self)
            if signal is not None:
                signals_to_emit.append(signal)
        # don't emit changed signals until all defaults are updated
        # in case of cross-dependencies
        for signal in signals_to_emit:
            signal.emit(self)
