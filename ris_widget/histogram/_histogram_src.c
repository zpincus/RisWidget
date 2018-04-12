// This code is licensed under the MIT License (see LICENSE file for details)

#include <inttypes.h>
#include <math.h>

void hist_uint8(const char *image, uint16_t rows, uint16_t cols, uint32_t r_stride, uint32_t c_stride,
    uint32_t *histogram, uint8_t *min, uint8_t *max) {
    uint8_t working_min = *(uint8_t *) image;
    uint8_t working_max = *(uint8_t *) image;
    const char *row_start, *pixel;
    for (row_start = image; row_start != image + rows*r_stride; row_start += r_stride) {
        for (pixel = row_start; pixel != row_start + cols*c_stride; pixel += c_stride) {
            uint8_t val = *(uint8_t *) pixel;
            histogram[val]++;
            if (val < working_min) working_min = val;
            else if (val > working_max) working_max = val;
        }
    }
    *min = working_min;
    *max = working_max;
}

void ranged_hist_uint8(const char *image, uint16_t rows, uint16_t cols, uint32_t r_stride, uint32_t c_stride,
    uint32_t *histogram, uint8_t hist_min, uint8_t hist_max, uint8_t *min, uint8_t *max) {
    uint8_t working_min = *(uint8_t *) image;
    uint8_t working_max = *(uint8_t *) image;
    const char *row_start, *pixel;
    for (row_start = image; row_start != image + rows*r_stride; row_start += r_stride) {
        for (pixel = row_start; pixel != row_start + cols*c_stride; pixel += c_stride) {
            uint8_t val = *(uint8_t *) pixel;
            if (val >= hist_min && val <= hist_max) histogram[val - hist_min]++;
            if (val < working_min) working_min = val;
            else if (val > working_max) working_max = val;
        }
    }
    *min = working_min;
    *max = working_max;
}

void masked_hist_uint8(const char *image, uint16_t rows, uint16_t cols, uint32_t r_stride, uint32_t c_stride,
    const uint16_t *starts, const uint16_t *ends, uint32_t *histogram, uint8_t *min, uint8_t *max) {
        // ends are exclusive bounds
    uint8_t working_min, working_max;
    working_min = working_max = *(uint8_t *) (image + (*starts)*c_stride);
    const char *row_start, *pixel;
    for (row_start = image; row_start != image + rows*r_stride; row_start += r_stride, starts++, ends++) {
        for (pixel = row_start + (*starts)*c_stride; pixel != row_start + (*ends)*c_stride; pixel += c_stride) {
            uint8_t val = *(uint8_t *) pixel;
            histogram[val]++;
            if (val < working_min) working_min = val;
            else if (val > working_max) working_max = val;
        }
    }
    *min = working_min;
    *max = working_max;
}

void masked_ranged_hist_uint8(const char *image, uint16_t rows, uint16_t cols, uint32_t r_stride, uint32_t c_stride,
    const uint16_t *starts, const uint16_t *ends, uint32_t *histogram, uint8_t hist_min, uint8_t hist_max, uint8_t *min, uint8_t *max) {
        // ends are exclusive bounds
    uint8_t working_min, working_max;
    working_min = working_max = *(uint8_t *) (image + (*starts)*c_stride);
    const char *row_start, *pixel;
    for (row_start = image; row_start != image + rows*r_stride; row_start += r_stride, starts++, ends++) {
        for (pixel = row_start + (*starts)*c_stride; pixel != row_start + (*ends)*c_stride; pixel += c_stride) {
            uint8_t val = *(uint8_t *) pixel;
            if (val >= hist_min && val <= hist_max) histogram[val - hist_min]++;
            if (val < working_min) working_min = val;
            else if (val > working_max) working_max = val;
        }
    }
    *min = working_min;
    *max = working_max;
}

void hist_uint16(const char *image, uint16_t rows, uint16_t cols, uint32_t r_stride, uint32_t c_stride,
    uint32_t *histogram, uint8_t shift, uint16_t *min, uint16_t *max) {
    uint16_t working_min = *(uint16_t *) image;
    uint16_t working_max = *(uint16_t *) image;
    const char *row_start, *pixel;
    for (row_start = image; row_start != image + rows*r_stride; row_start += r_stride) {
        for (pixel = row_start; pixel != row_start + cols*c_stride; pixel += c_stride) {
            uint16_t val = *(uint16_t *) pixel;
            histogram[val >> shift]++;
            if (val < working_min) working_min = val;
            else if (val > working_max) working_max = val;
        }
    }
    *min = working_min;
    *max = working_max;
}

void ranged_hist_uint16(const char *image, uint16_t rows, uint16_t cols, uint32_t r_stride, uint32_t c_stride,
    uint32_t *histogram, uint16_t n_bins, uint16_t hist_min, uint16_t hist_max, uint16_t *min, uint16_t *max) {
    uint16_t working_min = *(uint16_t *) image;
    uint16_t working_max = *(uint16_t *) image;
    const char *row_start, *pixel;
    float bin_factor = (float) n_bins / (hist_max - hist_min);
    uint32_t *last_bin = histogram + n_bins - 1;
    for (row_start = image; row_start != image + rows*r_stride; row_start += r_stride) {
        for (pixel = row_start; pixel != row_start + cols*c_stride; pixel += c_stride) {
            uint16_t val = *(uint16_t *) pixel;
            if (val >= hist_min && val < hist_max) histogram[(uint16_t) (bin_factor * (val - hist_min))]++;
            else if (val == hist_max) (*last_bin)++;

            if (val < working_min) working_min = val;
            else if (val > working_max) working_max = val;
        }
    }
    *min = working_min;
    *max = working_max;
}

void masked_hist_uint16(const char *image, uint16_t rows, uint16_t cols, uint32_t r_stride, uint32_t c_stride,
    const uint16_t *starts, const uint16_t *ends, uint32_t *histogram, uint8_t shift, uint16_t *min, uint16_t *max) {
    // ends are exclusive bounds
    uint16_t working_min, working_max;
    working_min = working_max = *(uint16_t *) (image + (*starts)*c_stride);
    const char *row_start, *pixel;
    for (row_start = image; row_start != image + rows*r_stride; row_start += r_stride, starts++, ends++) {
        for (pixel = row_start + (*starts)*c_stride; pixel != row_start + (*ends)*c_stride; pixel += c_stride) {
            uint16_t val = *(uint16_t *) pixel;
            histogram[val >> shift]++;
            if (val < working_min) working_min = val;
            else if (val > working_max) working_max = val;
        }
    }
    *min = working_min;
    *max = working_max;
}

void masked_ranged_hist_uint16(const char *image, uint16_t rows, uint16_t cols, uint32_t r_stride, uint32_t c_stride,
    const uint16_t *starts, const uint16_t *ends, uint32_t *histogram, uint16_t n_bins, uint16_t hist_min, uint16_t hist_max,
    uint16_t *min, uint16_t *max) {
    // ends are exclusive bounds
    uint16_t working_min, working_max;
    working_min = working_max = *(uint16_t *) (image + (*starts)*c_stride);
    const char *row_start, *pixel;
    float bin_factor = (float) n_bins / (hist_max - hist_min);
    uint32_t *last_bin = histogram + n_bins - 1;
    for (row_start = image; row_start != image + rows*r_stride; row_start += r_stride, starts++, ends++) {
        for (pixel = row_start + (*starts)*c_stride; pixel != row_start + (*ends)*c_stride; pixel += c_stride) {
            uint16_t val = *(uint16_t *) pixel;
            if (val >= hist_min && val < hist_max) histogram[(uint16_t) (bin_factor * (val - hist_min))]++;
            else if (val == hist_max) (*last_bin)++;

            if (val < working_min) working_min = val;
            else if (val > working_max) working_max = val;
        }
    }
    *min = working_min;
    *max = working_max;
}

void minmax_float(const char *image, uint16_t rows, uint16_t cols, uint32_t r_stride, uint32_t c_stride,
    float *min, float *max) {
    float working_min = *(float *) image;
    float working_max = *(float *) image;
    const char *row_start, *pixel;
    for (row_start = image; row_start != image + rows*r_stride; row_start += r_stride) {
        for (pixel = row_start; pixel != row_start + cols*c_stride; pixel += c_stride) {
            float val = *(float *) pixel;
            if (val < working_min) working_min = val;
            else if (val > working_max) working_max = val;
        }
    }
    *min = working_min;
    *max = working_max;
}

void masked_minmax_float(const char *image, uint16_t rows, uint16_t cols, uint32_t r_stride, uint32_t c_stride,
    const uint16_t *starts, const uint16_t *ends, float *min, float *max) {
    // ends are exclusive bounds
    float working_min, working_max;
    working_min = working_max = *(float *) (image + (*starts)*c_stride);
    const char *row_start, *pixel;
    for (row_start = image; row_start != image + rows*r_stride; row_start += r_stride, starts++, ends++) {
        for (pixel = row_start + (*starts)*c_stride; pixel != row_start + (*ends)*c_stride; pixel += c_stride) {
            float val = *(float *) pixel;
            if (val < working_min) working_min = val;
            else if (val > working_max) working_max = val;
        }
    }
    *min = working_min;
    *max = working_max;
}

void ranged_hist_float(const char *image, uint16_t rows, uint16_t cols, uint32_t r_stride, uint32_t c_stride,
    uint32_t *histogram, uint16_t n_bins, float hist_min, float hist_max) {
    const char *row_start, *pixel;
    float bin_factor = (float) n_bins / (hist_max - hist_min);
    uint32_t *last_bin = histogram + n_bins - 1;
    for (row_start = image; row_start != image + rows*r_stride; row_start += r_stride) {
        for (pixel = row_start; pixel != row_start + cols*c_stride; pixel += c_stride) {
            float val = *(float *) pixel;
            if (val >= hist_min && val < hist_max)
                histogram[(uint16_t) (bin_factor * (val - hist_min))]++;
            else if (val == hist_max) (*last_bin)++;
        }
    }
}

void masked_ranged_hist_float(const char *image, uint16_t rows, uint16_t cols, uint32_t r_stride, uint32_t c_stride,
    const uint16_t *starts, const uint16_t *ends, uint32_t *histogram, uint16_t n_bins, float hist_min, float hist_max) {
    // ends are exclusive bounds
    const char *row_start, *pixel;
    float bin_factor = (float) n_bins / (hist_max - hist_min);
    uint32_t *last_bin = histogram + n_bins - 1;
    for (row_start = image; row_start != image + rows*r_stride; row_start += r_stride, starts++, ends++) {
        for (pixel = row_start + (*starts)*c_stride; pixel != row_start + (*ends)*c_stride; pixel += c_stride) {
            float val = *(float *) pixel;
            if (val >= hist_min && val < hist_max)
                histogram[(uint16_t) (bin_factor * (val - hist_min))]++;
            else if (val == hist_max) (*last_bin)++;
        }
    }
}