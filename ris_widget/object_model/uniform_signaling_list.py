# This code is licensed under the MIT License (see LICENSE file for details)

from .signaling_list import SignalingList

class UniformSignalingList(SignalingList):
    """
    UniformSignalingList: A SignalingList whose elements are transformed and/or
    validated by the take_input_element method.

    take_input_element is called for every item to add to the list. The method
    can return the item, return a transformed version of the item, or raise an error.
    In the former cases, the returned value will be added to the list.

    In the following example, FloatList transforms anything that float() understands into a
    float and raises an exception otherwise:

    from ris_widget.signaling_list import UniformSignalingList

    class FloatList(UniformSignalingList):
        def take_input_element(self, obj):
            return float(obj)
    """

    def __init__(self, iterable=None, parent=None):
        if iterable is None:
            super().__init__(parent=parent)
        else:
            super().__init__(iterable=map(self.take_input_element, iterable), parent=parent)

    def take_input_element(self, obj):
        raise NotImplementedError()

    def __setitem__(self, idx_or_slice, srcs):
        if isinstance(idx_or_slice, slice):
            super().__setitem__(idx_or_slice, list(map(self.take_input_element, srcs)))
        else:
            super().__setitem__(idx_or_slice, self.take_input_element(srcs))
    __setitem__.__doc__ = SignalingList.__setitem__.__doc__

    def extend(self, srcs):
        super().extend(map(self.take_input_element, srcs))
    extend.__doc__ = SignalingList.extend.__doc__

    def insert(self, idx, obj):
        super().insert(idx, self.take_input_element(obj))
    insert.__doc__ = SignalingList.insert.__doc__

UniformSignalingList.__doc__ = UniformSignalingList.__doc__ + '\n\n' + SignalingList.__doc__
