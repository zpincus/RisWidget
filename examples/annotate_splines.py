# This code is licensed under the MIT License (see LICENSE file for details)

from ris_widget import ris_widget; rw = ris_widget.RisWidget()
import pathlib
rw.add_image_files_to_flipbook(pathlib.Path('/Users/zpincus/Documents/Research/Pincus Lab/Data/raw_image_demo/').glob('*.png'))
from ris_widget import split_view
split_view.split_view_rw(rw)
from ris_widget.overlay import free_spline
fs = free_spline.FreeSpline(rw)
from ris_widget.qwidgets import annotator
spline_field = annotator.OverlayAnnotation('centerline', fs)
rw.add_annotator(fields=[spline_field])
# load tcks into tck_list
annotations = [{'centerline':tck} for tck in tck_list]
rw.annotator.all_annotations = annotations