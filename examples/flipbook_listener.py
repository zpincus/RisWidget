def page_changed(flipbook):
    print(flipbook.current_page_idx)
    if len(flipbook.current_page) > 0:
        base_image = flipbook.current_page[0]
        base_image_array = base_image.data
        print(base_image.name, base_image_array.shape, base_image_array.dtype)

def install_listener(rw, listener=page_changed):
    rw.flipbook.current_page_changed.connect(page_changed)