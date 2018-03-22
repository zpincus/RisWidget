# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

def basic_auto_advance(old_value, value):
    """Advance to next if the value was changed in any way."""
    return old_value != value

class AnnotationField:
    ENABLABLE = True
    def __init__(self, name, default=None, auto_advance=None):
        self.name = name
        self.default = default
        self.auto_advance = auto_advance
        self.flipbook = None
        self.init_widget()
        self.widget.setEnabled(False)

    def init_widget(self):
        """Overrride in subclass to initialize widget."""
        raise NotImplementedError

    def set_annotations(self, page, annotations):
        """Receive a new annotation dictionary, which may be None to indicate
        an invalid state where the widget should be disabled."""
        self.annotations = annotations
        self.current_page = page
        if annotations is None:
            self.widget.setEnabled(False)
            self.update_widget(None)
        else:
            if self.ENABLABLE:
                self.widget.setEnabled(True)
            self.update_widget(self.get_annotation_for_page(page, annotations))

    def update_annotation_data(self, value):
        """Call this function from each subclass when there is a new value from the GUI."""
        if self.annotations is not None:
            old_value = self.annotations.get(self.name, None)
            self.annotations[self.name] = value
        else:
            old_value = None
        if self.auto_advance is not None:
            if self.auto_advance(old_value, value) and self.flipbook is not None:
                if self.flipbook.current_page_idx < len(self.flipbook.pages) - 1:
                    self.flipbook.current_page_idx += 1

    def get_annotation_for_page(self, page, annotations):
        """If self.default is a function, call it with the current flipbook page to
        calculate an appropriate default."""
        if self.name not in annotations:
            if callable(self.default):
                default = self.default(page)
            else:
                default = self.default
            annotations[self.name] = default
        return annotations[self.name]


    def update_widget(self, value):
        """Override in subclasses to give widget new data on page change. Must accept None."""
        raise NotImplementedError


class BoolField(AnnotationField):
    def __init__(self, name, default=False):
        super().__init__(name, default)

    def init_widget(self):
        self.widget = Qt.QCheckBox()
        self.widget.setChecked(False)
        self.widget.stateChanged.connect(self._on_widget_change)

    def _on_widget_change(self, state):
        self.update_annotation_data(state == Qt.Qt.Checked)

    def update_widget(self, value):
        self.widget.setChecked(bool(value))


class NonWidgetAnnotation(AnnotationField):
    """Annotation 'field' that presents a checkbox about whether some other
    data source has provided annotation data. This source could be an overlay
    for drawing on the image, e.g."""
    ENABLABLE = False

    def init_widget(self):
        self.widget = Qt.QCheckBox()
        self.widget.setChecked(False)

    def update_widget(self, value):
        self.widget.setChecked(value is not None)


class OverlayAnnotation(NonWidgetAnnotation):
    def __init__(self, name, overlay, default=None, auto_advance=None):
        """
        Parameters:
            overlay: item from ris_widget.overlay
        """
        super().__init__(name, default, auto_advance)
        self.overlay = overlay
        self.overlay.geometry_change_callbacks.append(self.on_geometry_change)

    def on_geometry_change(self, value):
        # don't call our overridden update_widget because that will set the geometry again...
        super().update_widget(value)
        self.update_annotation_data(value)

    def update_widget(self, value):
        super().update_widget(value)
        self.overlay.geometry = value


class StringField(AnnotationField):
    def init_widget(self):
        self.widget = Qt.QLineEdit()
        self.widget.textEdited.connect(self._on_widget_change)

    def _on_widget_change(self):
        self.update_annotation_data(self.widget.text())

    def update_widget(self, value):
        self.widget.setText(value)


class ChoicesField(AnnotationField):
    def __init__(self, name, choices, default=None):
        self.choices = choices
        super().__init__(name, default)

    def init_widget(self):
        self.widget = Qt.QComboBox()
        for choice in self.choices:
            self.widget.addItem(choice)
        self.widget.currentTextChanged.connect(self.update_annotation_data)

    def update_widget(self, value):
        if value is None:
            self.widget.setCurrentIndex(-1)
        elif value not in self.choices:
            raise ValueError('Value {} not in list of choices.'.format(value))
        else:
            self.widget.setCurrentText(value)


class Annotator(Qt.QWidget):
    """Widget to annotate flipbook pages with notes or geometry from the GUI.

    Each flipbook page will be provided with an 'annotations' attribute after
    visiting that page with the annotator widget open. These annotations can be
    accessed directly, or via the 'all_annotations' property of this class,
    which has the advantage of filling in default values for unseen pages.

    Example:
    fields = [BoolField('alive', default=True), ChoicesField('stage', ['L1', 'L2'])]
    annotator = Annotator(rw, fields)
    # make annotations in the GUI
    data = annotator.all_annotations

    # how to make GUI reflect python-level changes to the annotations
    rw.flipbook.current_page.annotations['alive'] = False
    # or
    annotator.current_annotations['alive'] = False
    # then to make an update occur:
    annotator.update_fields()
    """
    def __init__(self, rw, fields, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.Qt.WA_DeleteOnClose)
        layout = Qt.QFormLayout()
        layout.setFieldGrowthPolicy(layout.ExpandingFieldsGrow)
        self.setLayout(layout)
        self.fields = fields
        for field in self.fields:
            if isinstance(field.widget, Qt.QGroupBox):
                layout.addWidget(field.widget)
            else:
                layout.addRow(field.name, field.widget)
            field.flipbook = rw.flipbook
        self.flipbook = rw.flipbook
        self.flipbook.current_page_changed.connect(self.update_fields)
        self.update_fields()

    def update_fields(self):
        if self.isVisible() and len(self.flipbook.selected_pages) == 1:
            page = self.flipbook.current_page
            try:
                self.current_annotations = page.annotations
            except AttributeError:
                self.current_annotations = page.annotations = {}
        else:
            page = self.current_annotations = None
        for field in self.fields:
            label = self.layout().labelForField(field.widget)
            if label is not None:
                label.setEnabled(self.current_annotations is not None)
            field.set_annotations(page, self.current_annotations)

    def showEvent(self, event):
        if not event.spontaneous(): # event is from Qt and widget became visible
            self.update_fields()

    def hideEvent(self, event):
        if not event.spontaneous(): # event is from Qt and widget became invisible
            # tell widgets to deactivate -- especially important for annotators
            # that also show an overlay
            self.update_fields()

    @property
    def all_annotations(self):
        all_annotations = []
        for page in self.flipbook.pages:
            try:
                page_annotations = dict(page.annotations)
            except AttributeError:
                page_annotations = {}
            for field in self.fields:
                # the below will set the field's annotation to the default value if it's not present
                field.get_annotation_for_page(page, page_annotations)
            all_annotations.append(page_annotations)
        return all_annotations

    @all_annotations.setter
    def all_annotations(self, all_annotations):
        # Replace relevant values in annotations of corresponding pages.  In the situation where an incomplete
        # dict is supplied for a page also missing the omitted values, defaults are assigned.
        for new_annotations, page in zip(all_annotations, self.flipbook.pages):
            try:
                page_annotations = page.annotations
            except AttributeError:
                page_annotations = page.annotations = {}
            page_annotations.update(new_annotations)
            for field in self.fields:
                # the below will set the field's annotation to the default value if it's not present
                field.get_annotation_for_page(page, page_annotations)
        self.update_fields()