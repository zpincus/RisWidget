# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

def basic_auto_advance(old_value, value):
    """Advance to next if the value was changed in any way."""
    return old_value != value

class AnnotationField:
    ENABLABLE = True
    def __init__(self, name, default=None):
        self.name = name
        self.default = default
        self.flipbook = None
        self.init_widget()
        self.widget.setEnabled(False)

    def init_widget(self):
        """Overrride in subclass to initialize widget."""
        raise NotImplementedError

    def set_annotation_page(self, page):
        """Receive a new annotation dictionary, which may be None to indicate
        an invalid state where the widget should be disabled."""
        self.page = page
        if page is None:
            self.widget.setEnabled(False)
            annotation = None
        else:
            if self.ENABLABLE:
                self.widget.setEnabled(True)
            annotation = self.get_annotation(page, setdefault=True)
        self.update_widget(annotation)

    def update_annotation(self, value):
        """Call this function from each subclass when there is a new value from the GUI."""
        if self.page is None:
            return
        old_value = self.page.annotations.get(self.name, None)
        self.page.annotations[self.name] = value
        if self.auto_advance(old_value, value) and self.flipbook is not None:
            if self.flipbook.current_page_idx < len(self.flipbook.pages) - 1:
                self.flipbook.current_page_idx += 1

    def get_annotation(self, page=None, setdefault=False):
        """Get the current annotation for the page, or return the default (and
        also set that default as the current annotation)"""
        if page is None:
            page = self.page
        if self.name not in page.annotations:
            default = self.default_annotation_for_page(page)
            if setdefault:
                page.annotations[self.name] = default
            return default
        else:
            return page.annotations[self.name]

    def default_annotation_for_page(self, page):
        """Return the default value. Subclasses may override to choose an appropriate
        default based on the page."""
        return self.default

    def auto_advance(self, old_value, new_value):
        """Subclasses may override to provide auto-advancing behavior based on the
        annotation (e.g. if the user has clicked three points, move to the next flipbook
        page)"""
        return False

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
        self.update_annotation(state == Qt.Qt.Checked)

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
        self.update_annotation(value)

    def update_widget(self, value):
        super().update_widget(value)
        self.overlay.geometry = value


class StringField(AnnotationField):
    def init_widget(self):
        self.widget = Qt.QLineEdit()
        self.widget.textEdited.connect(self._on_widget_change)

    def _on_widget_change(self):
        self.update_annotation(self.widget.text())

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
        self.widget.currentTextChanged.connect(self.update_annotation)

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
            if not hasattr(page, 'annotations'):
                page.annotations = {}
        else:
            page = None
        for field in self.fields:
            label = self.layout().labelForField(field.widget)
            if label is not None:
                label.setEnabled(page is not None)
            field.set_annotation_page(page)

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
            page_annotations = {}
            for field in self.fields:
                # the below will return either the current annotation or the default
                page_annotations[field.name] = field.get_annotation(page)
            all_annotations.append(page_annotations)
        return all_annotations

    @all_annotations.setter
    def all_annotations(self, all_annotations):
        # Replace relevant values in annotations of corresponding pages.  In the situation where an incomplete
        # dict is supplied for a page also missing the omitted values, defaults are assigned.
        for new_annotations, page in zip(all_annotations, self.flipbook.pages):
            if not hasattr(page, 'annotations'):
                page.annotations = {}
            page.annotations.update(new_annotations)
            for field in self.fields:
                # the below will set the field's annotation to the default value if it's not present
                field.get_annotation(page, setdefault=True)
        self.update_fields()