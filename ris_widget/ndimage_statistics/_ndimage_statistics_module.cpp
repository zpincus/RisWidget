// The MIT License (MIT)
//
// Copyright (c) 2016 WUSTL ZPLAB
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.
//
// Authors: Erik Hvatum <ice.rikh@gmail.com>

#include <stdexcept>
#include <sstream>
#include <pybind11/pybind11.h>
#include "_ndimage_statistics.h"
#include "resampling_lut.h"

namespace py = pybind11;

// It would be nice to use distinct py::array_t</*element type*/> overload definitions rather than dispatching from a 
// single frontend, but this does not work as py::array_t attempts to cast.  That is, supplied with an numpy array of dtype 
// numpy.uint64, m.def("min_max", [](py::array_t<float>...) would be called with temporary arguments holding inputs 
// converted to float arrays.  This is never something we want. 
void py_min_max(py::buffer im, py::buffer min_max)
{
    py::buffer_info im_info{im.request()}, min_max_info{min_max.request()};
    if(im_info.ndim != 2)
        throw std::invalid_argument("im argument must be a 2 dimensional buffer object (such as a numpy array).");
    if(min_max_info.ndim != 1)
        throw std::invalid_argument("min_max arugment must be a 1 dimensional buffer object (such as a numpy array).");
    if(min_max_info.shape[0] != 2)
        throw std::invalid_argument("min_max argument must contain exactly 2 elements.");
    if(im_info.format != min_max_info.format)
        throw std::invalid_argument(
            "im and min_max arguments must be the same format (or dtype, in the case where they are numpy arays).");
    if(im_info.format == py::format_descriptor<float>::value())
        ::min_max((float*)im_info.ptr, im_info.shape.data(), im_info.strides.data(), (float*)min_max_info.ptr, min_max_info.strides[0]);
    else if(im_info.format == py::format_descriptor<std::uint8_t>::value())
        ::min_max((std::uint8_t*)im_info.ptr, im_info.shape.data(), im_info.strides.data(), (std::uint8_t*)min_max_info.ptr, min_max_info.strides[0]);
    else if(im_info.format == py::format_descriptor<std::uint16_t>::value())
        ::min_max((std::uint16_t*)im_info.ptr, im_info.shape.data(), im_info.strides.data(), (std::uint16_t*)min_max_info.ptr, min_max_info.strides[0]);
    else if(im_info.format == py::format_descriptor<std::uint32_t>::value())
        ::min_max((std::uint32_t*)im_info.ptr, im_info.shape.data(), im_info.strides.data(), (std::uint32_t*)min_max_info.ptr, min_max_info.strides[0]);
    else if(im_info.format == py::format_descriptor<std::uint64_t>::value())
        ::min_max((std::uint64_t*)im_info.ptr, im_info.shape.data(), im_info.strides.data(), (std::uint64_t*)min_max_info.ptr, min_max_info.strides[0]);
    else if(im_info.format == py::format_descriptor<double>::value())
        ::min_max((double*)im_info.ptr, im_info.shape.data(), im_info.strides.data(), (double*)min_max_info.ptr, min_max_info.strides[0]);
    else
        throw std::invalid_argument("Only uint8, uint16, uint32, uint64, float32, and float64 buffers are supported.");
}

void py_masked_min_max(py::buffer im, py::buffer mask, py::buffer min_max)
{
    py::buffer_info im_info{im.request()}, min_max_info{min_max.request()}, mask_info{mask.request()};
    if(im_info.ndim != 2)
        throw std::invalid_argument("im argument must be a 2 dimensional buffer object (such as a numpy array).");
    if(min_max_info.ndim != 1)
        throw std::invalid_argument("min_max arugment must be a 1 dimensional buffer object (such as a numpy array).");
    if(min_max_info.shape[0] != 2)
        throw std::invalid_argument("min_max argument must contain exactly 2 elements.");
    if(im_info.format != min_max_info.format)
        throw std::invalid_argument(
            "im and min_max arguments must be the same format (or dtype, in the case where they are numpy arays).");
    if(mask_info.ndim != 2)
        throw std::invalid_argument("mask argument must be a 2 dimensionsal buffer object (such as a numpy array).");
    if(mask_info.format != py::format_descriptor<std::uint8_t>::value())
        throw std::invalid_argument("mask argument format must be uint8 or bool.");
    if(im_info.format == py::format_descriptor<float>::value())
        masked_min_max((float*)im_info.ptr,
                       im_info.shape.data(),
                       im_info.strides.data(),
                       (std::uint8_t*)mask_info.ptr,
                       mask_info.shape.data(),
                       mask_info.strides.data(),
                       (float*)min_max_info.ptr,
                       min_max_info.strides[0]);
    else if(im_info.format == py::format_descriptor<std::uint8_t>::value())
        masked_min_max((std::uint8_t*)im_info.ptr,
                       im_info.shape.data(),
                       im_info.strides.data(),
                       (std::uint8_t*)mask_info.ptr,
                       mask_info.shape.data(),
                       mask_info.strides.data(),
                       (std::uint8_t*)min_max_info.ptr,
                       min_max_info.strides[0]);
    else if(im_info.format == py::format_descriptor<std::uint16_t>::value())
        masked_min_max((std::uint16_t*)im_info.ptr,
                       im_info.shape.data(),
                       im_info.strides.data(),
                       (std::uint8_t*)mask_info.ptr,
                       mask_info.shape.data(),
                       mask_info.strides.data(),
                       (std::uint16_t*)min_max_info.ptr,
                       min_max_info.strides[0]);
    else if(im_info.format == py::format_descriptor<std::uint32_t>::value())
        masked_min_max((std::uint32_t*)im_info.ptr,
                       im_info.shape.data(),
                       im_info.strides.data(),
                       (std::uint8_t*)mask_info.ptr,
                       mask_info.shape.data(),
                       mask_info.strides.data(),
                       (std::uint32_t*)min_max_info.ptr,
                       min_max_info.strides[0]);
    else if(im_info.format == py::format_descriptor<std::uint64_t>::value())
        masked_min_max((std::uint64_t*)im_info.ptr,
                       im_info.shape.data(),
                       im_info.strides.data(),
                       (std::uint8_t*)mask_info.ptr,
                       mask_info.shape.data(),
                       mask_info.strides.data(),
                       (std::uint64_t*)min_max_info.ptr,
                       min_max_info.strides[0]);
    else if(im_info.format == py::format_descriptor<double>::value())
        masked_min_max((double*)im_info.ptr,
                       im_info.shape.data(),
                       im_info.strides.data(),
                       (std::uint8_t*)mask_info.ptr,
                       mask_info.shape.data(),
                       mask_info.strides.data(),
                       (double*)min_max_info.ptr,
                       min_max_info.strides[0]);
    else
        throw std::invalid_argument("Only uint8, uint16, uint32, uint64, float32, and float64 im and min_max buffers are supported.");
}

void py_ranged_hist(py::buffer im, py::buffer range, py::buffer hist, bool with_overflow_bins)
{
    py::buffer_info im_info{im.request()}, range_info{range.request()}, hist_info{hist.request()};
    if(im_info.ndim != 2)
        throw std::invalid_argument("im argument must be a 2 dimensional buffer object (such as a numpy array).");
    if(im_info.format != range_info.format)
        throw std::invalid_argument(
            "im and range arguments must be the same format (or dtype, in the case where they are numpy arays).");
    if(hist_info.ndim != 1)
        throw std::invalid_argument("hist argument must be a 1 dimensional buffer object (such as a numpy array).");
    if(hist_info.format != py::format_descriptor<std::uint32_t>::value())
        throw std::invalid_argument("hist argument format must be uint32.");
    if(with_overflow_bins)
    {
        if(im_info.format == py::format_descriptor<float>::value())
            ranged_hist<float, true>((float*)im_info.ptr,
                                     im_info.shape.data(),
                                     im_info.strides.data(),
                                     (float*)range_info.ptr,
                                     range_info.strides[0],
                                     hist_info.shape[0],
                                     (std::uint32_t*)hist_info.ptr,
                                     hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint8_t>::value())
            ranged_hist<std::uint8_t, true>((std::uint8_t*)im_info.ptr,
                                            im_info.shape.data(),
                                            im_info.strides.data(),
                                            (std::uint8_t*)range_info.ptr,
                                            range_info.strides[0],
                                            hist_info.shape[0],
                                            (std::uint32_t*)hist_info.ptr,
                                            hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint16_t>::value())
            ranged_hist<std::uint16_t, true>((std::uint16_t*)im_info.ptr,
                                             im_info.shape.data(),
                                             im_info.strides.data(),
                                             (std::uint16_t*)range_info.ptr,
                                             range_info.strides[0],
                                             hist_info.shape[0],
                                             (std::uint32_t*)hist_info.ptr,
                                             hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint32_t>::value())
            ranged_hist<std::uint32_t, true>((std::uint32_t*)im_info.ptr,
                                             im_info.shape.data(),
                                             im_info.strides.data(),
                                             (std::uint32_t*)range_info.ptr,
                                             range_info.strides[0],
                                             hist_info.shape[0],
                                             (std::uint32_t*)hist_info.ptr,
                                             hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint64_t>::value())
            ranged_hist<std::uint64_t, true>((std::uint64_t*)im_info.ptr,
                                             im_info.shape.data(),
                                             im_info.strides.data(),
                                             (std::uint64_t*)range_info.ptr,
                                             range_info.strides[0],
                                             hist_info.shape[0],
                                             (std::uint32_t*)hist_info.ptr,
                                             hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<double>::value())
            ranged_hist<double, true>((double*)im_info.ptr,
                                      im_info.shape.data(),
                                      im_info.strides.data(),
                                      (double*)range_info.ptr,
                                      range_info.strides[0],
                                      hist_info.shape[0],
                                      (std::uint32_t*)hist_info.ptr,
                                      hist_info.strides[0]);
        else
            throw std::invalid_argument("Only uint8, uint16, uint32, uint64, float32, and float64 im buffers are supported.");
    }
    else
    {
        if(im_info.format == py::format_descriptor<float>::value())
            ranged_hist<float, false>((float*)im_info.ptr,
                                      im_info.shape.data(),
                                      im_info.strides.data(),
                                      (float*)range_info.ptr,
                                      range_info.strides[0],
                                      hist_info.shape[0],
                                      (std::uint32_t*)hist_info.ptr,
                                      hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint8_t>::value())
            ranged_hist<std::uint8_t, false>((std::uint8_t*)im_info.ptr,
                                             im_info.shape.data(),
                                             im_info.strides.data(),
                                             (std::uint8_t*)range_info.ptr,
                                             range_info.strides[0],
                                             hist_info.shape[0],
                                             (std::uint32_t*)hist_info.ptr,
                                             hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint16_t>::value())
            ranged_hist<std::uint16_t, false>((std::uint16_t*)im_info.ptr,
                                              im_info.shape.data(),
                                              im_info.strides.data(),
                                              (std::uint16_t*)range_info.ptr,
                                              range_info.strides[0],
                                              hist_info.shape[0],
                                              (std::uint32_t*)hist_info.ptr,
                                              hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint32_t>::value())
            ranged_hist<std::uint32_t, false>((std::uint32_t*)im_info.ptr,
                                              im_info.shape.data(),
                                              im_info.strides.data(),
                                              (std::uint32_t*)range_info.ptr,
                                              range_info.strides[0],
                                              hist_info.shape[0],
                                              (std::uint32_t*)hist_info.ptr,
                                              hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint64_t>::value())
            ranged_hist<std::uint64_t, false>((std::uint64_t*)im_info.ptr,
                                              im_info.shape.data(),
                                              im_info.strides.data(),
                                              (std::uint64_t*)range_info.ptr,
                                              range_info.strides[0],
                                              hist_info.shape[0],
                                              (std::uint32_t*)hist_info.ptr,
                                              hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<double>::value())
            ranged_hist<double, false>((double*)im_info.ptr,
                                       im_info.shape.data(),
                                       im_info.strides.data(),
                                       (double*)range_info.ptr,
                                       range_info.strides[0],
                                       hist_info.shape[0],
                                       (std::uint32_t*)hist_info.ptr,
                                       hist_info.strides[0]);
        else
            throw std::invalid_argument("Only uint8, uint16, uint32, uint64, float32, and float64 im buffers are supported.");
    }
}

void py_masked_ranged_hist(py::buffer im, py::buffer mask, py::buffer range, py::buffer hist, bool with_overflow_bins)
{
    py::buffer_info im_info{im.request()}, mask_info{mask.request()}, range_info{range.request()}, hist_info{hist.request()};
    if(im_info.ndim != 2)
        throw std::invalid_argument("im argument must be a 2 dimensional buffer object (such as a numpy array).");
    if(im_info.format != range_info.format)
        throw std::invalid_argument(
            "im and range arguments must be the same format (or dtype, in the case where they are numpy arays).");
    if(hist_info.ndim != 1)
        throw std::invalid_argument("hist argument must be a 1 dimensional buffer object (such as a numpy array).");
    if(hist_info.format != py::format_descriptor<std::uint32_t>::value())
        throw std::invalid_argument("hist argument format must be uint32.");
    if(with_overflow_bins)
    {
        if(im_info.format == py::format_descriptor<float>::value())
            masked_ranged_hist<float, true>((float*)im_info.ptr,
                                            im_info.shape.data(),
                                            im_info.strides.data(),
                                            (std::uint8_t*)mask_info.ptr,
                                            mask_info.shape.data(),
                                            mask_info.strides.data(),
                                            (float*)range_info.ptr,
                                            range_info.strides[0],
                                            hist_info.shape[0],
                                            (std::uint32_t*)hist_info.ptr,
                                            hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint8_t>::value())
            masked_ranged_hist<std::uint8_t, true>((std::uint8_t*)im_info.ptr,
                                                   im_info.shape.data(),
                                                   im_info.strides.data(),
                                                   (std::uint8_t*)mask_info.ptr,
                                                   mask_info.shape.data(),
                                                   mask_info.strides.data(),
                                                   (std::uint8_t*)range_info.ptr,
                                                   range_info.strides[0],
                                                   hist_info.shape[0],
                                                   (std::uint32_t*)hist_info.ptr,
                                                   hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint16_t>::value())
            masked_ranged_hist<std::uint16_t, true>((std::uint16_t*)im_info.ptr,
                                                    im_info.shape.data(),
                                                    im_info.strides.data(),
                                                    (std::uint8_t*)mask_info.ptr,
                                                    mask_info.shape.data(),
                                                    mask_info.strides.data(),
                                                    (std::uint16_t*)range_info.ptr,
                                                    range_info.strides[0],
                                                    hist_info.shape[0],
                                                    (std::uint32_t*)hist_info.ptr,
                                                    hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint32_t>::value())
            masked_ranged_hist<std::uint32_t, true>((std::uint32_t*)im_info.ptr,
                                                    im_info.shape.data(),
                                                    im_info.strides.data(),
                                                    (std::uint8_t*)mask_info.ptr,
                                                    mask_info.shape.data(),
                                                    mask_info.strides.data(),
                                                    (std::uint32_t*)range_info.ptr,
                                                    range_info.strides[0],
                                                    hist_info.shape[0],
                                                    (std::uint32_t*)hist_info.ptr,
                                                    hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint64_t>::value())
            masked_ranged_hist<std::uint64_t, true>((std::uint64_t*)im_info.ptr,
                                                    im_info.shape.data(),
                                                    im_info.strides.data(),
                                                    (std::uint8_t*)mask_info.ptr,
                                                    mask_info.shape.data(),
                                                    mask_info.strides.data(),
                                                    (std::uint64_t*)range_info.ptr,
                                                    range_info.strides[0],
                                                    hist_info.shape[0],
                                                    (std::uint32_t*)hist_info.ptr,
                                                    hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<double>::value())
            masked_ranged_hist<double, true>((double*)im_info.ptr,
                                             im_info.shape.data(),
                                             im_info.strides.data(),
                                             (std::uint8_t*)mask_info.ptr,
                                             mask_info.shape.data(),
                                             mask_info.strides.data(),
                                             (double*)range_info.ptr,
                                             range_info.strides[0],
                                             hist_info.shape[0],
                                             (std::uint32_t*)hist_info.ptr,
                                             hist_info.strides[0]);
        else
            throw std::invalid_argument("Only uint8, uint16, uint32, uint64, float32, and float64 im buffers are supported.");
    }
    else
    {
        if(im_info.format == py::format_descriptor<float>::value())
            masked_ranged_hist<float, false>((float*)im_info.ptr,
                                             im_info.shape.data(),
                                             im_info.strides.data(),
                                             (std::uint8_t*)mask_info.ptr,
                                             mask_info.shape.data(),
                                             mask_info.strides.data(),
                                             (float*)range_info.ptr,
                                             range_info.strides[0],
                                             hist_info.shape[0],
                                             (std::uint32_t*)hist_info.ptr,
                                             hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint8_t>::value())
            masked_ranged_hist<std::uint8_t, false>((std::uint8_t*)im_info.ptr,
                                                    im_info.shape.data(),
                                                    im_info.strides.data(),
                                                    (std::uint8_t*)mask_info.ptr,
                                                    mask_info.shape.data(),
                                                    mask_info.strides.data(),
                                                    (std::uint8_t*)range_info.ptr,
                                                    range_info.strides[0],
                                                    hist_info.shape[0],
                                                    (std::uint32_t*)hist_info.ptr,
                                                    hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint16_t>::value())
            masked_ranged_hist<std::uint16_t, false>((std::uint16_t*)im_info.ptr,
                                                     im_info.shape.data(),
                                                     im_info.strides.data(),
                                                     (std::uint8_t*)mask_info.ptr,
                                                     mask_info.shape.data(),
                                                     mask_info.strides.data(),
                                                     (std::uint16_t*)range_info.ptr,
                                                     range_info.strides[0],
                                                     hist_info.shape[0],
                                                     (std::uint32_t*)hist_info.ptr,
                                                     hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint32_t>::value())
            masked_ranged_hist<std::uint32_t, false>((std::uint32_t*)im_info.ptr,
                                                     im_info.shape.data(),
                                                     im_info.strides.data(),
                                                     (std::uint8_t*)mask_info.ptr,
                                                     mask_info.shape.data(),
                                                     mask_info.strides.data(),
                                                     (std::uint32_t*)range_info.ptr,
                                                     range_info.strides[0],
                                                     hist_info.shape[0],
                                                     (std::uint32_t*)hist_info.ptr,
                                                     hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<std::uint64_t>::value())
            masked_ranged_hist<std::uint64_t, false>((std::uint64_t*)im_info.ptr,
                                                     im_info.shape.data(),
                                                     im_info.strides.data(),
                                                     (std::uint8_t*)mask_info.ptr,
                                                     mask_info.shape.data(),
                                                     mask_info.strides.data(),
                                                     (std::uint64_t*)range_info.ptr,
                                                     range_info.strides[0],
                                                     hist_info.shape[0],
                                                     (std::uint32_t*)hist_info.ptr,
                                                     hist_info.strides[0]);
        else if(im_info.format == py::format_descriptor<double>::value())
            masked_ranged_hist<double, false>((double*)im_info.ptr,
                                              im_info.shape.data(),
                                              im_info.strides.data(),
                                              (std::uint8_t*)mask_info.ptr,
                                              mask_info.shape.data(),
                                              mask_info.strides.data(),
                                              (double*)range_info.ptr,
                                              range_info.strides[0],
                                              hist_info.shape[0],
                                              (std::uint32_t*)hist_info.ptr,
                                              hist_info.strides[0]);
        else
            throw std::invalid_argument("Only uint8, uint16, uint32, uint64, float32, and float64 im buffers are supported.");
    }
}

void py_hist_min_max(py::buffer im, py::buffer hist, py::buffer min_max, bool is_twelve_bit)
{
    py::buffer_info im_info{im.request()}, hist_info{hist.request()}, min_max_info{min_max.request()};
    if(im_info.ndim != 2)
        throw std::invalid_argument("im argument must be a 2 dimensional buffer object (such as a numpy array).");
    if(hist_info.ndim != 1)
        throw std::invalid_argument("hist argument must be a 1 dimensional buffer object (such as a numpy array).");
    if(hist_info.format != py::format_descriptor<std::uint32_t>::value())
        throw std::invalid_argument("hist argument format must be uint32.");
    if(min_max_info.ndim != 1)
        throw std::invalid_argument("min_max arugment must be a 1 dimensional buffer object (such as a numpy array).");
    if(min_max_info.shape[0] != 2)
        throw std::invalid_argument("min_max argument must contain exactly 2 elements.");
    if(im_info.format != min_max_info.format)
        throw std::invalid_argument(
            "im and min_max arguments must be the same format (or dtype, in the case where they are numpy arays).");
    if(is_twelve_bit)
    {
        if(im_info.format == py::format_descriptor<std::uint16_t>::value())
        {
            if(hist_info.shape[0] != bin_count<std::uint16_t>())
            {
                std::ostringstream o;
                o << "hist argument must contain " << bin_count<std::uint16_t>() << " elements for uint16 im.";
                throw std::invalid_argument(o.str());
            }
            hist_min_max<std::uint16_t, true>((std::uint16_t*)im_info.ptr,
                                              im_info.shape.data(),
                                              im_info.strides.data(),
                                              (std::uint32_t*)hist_info.ptr,
                                              hist_info.strides[0],
                                              (std::uint16_t*)min_max_info.ptr,
                                              min_max_info.strides[0]);
        }
        else
            throw std::invalid_argument("is_twelve_bit may be True only if im is uint16.");
    }
    else
    {
        if(im_info.format == py::format_descriptor<std::uint8_t>::value())
        {
            if(hist_info.shape[0] != bin_count<std::uint8_t>())
            {
                std::ostringstream o;
                o << "hist argument must contain " << bin_count<std::uint8_t>() << " elements for uint8 im.";
                throw std::invalid_argument(o.str());
            }
            hist_min_max<std::uint8_t, false>((std::uint8_t*)im_info.ptr,
                                              im_info.shape.data(),
                                              im_info.strides.data(),
                                              (std::uint32_t*)hist_info.ptr,
                                              hist_info.strides[0],
                                              (std::uint8_t*)min_max_info.ptr,
                                              min_max_info.strides[0]);
        }
        else if(im_info.format == py::format_descriptor<std::uint16_t>::value())
        {
            if(hist_info.shape[0] != bin_count<std::uint16_t>())
            {
                std::ostringstream o;
                o << "hist argument must contain " << bin_count<std::uint16_t>() << " elements for uint16 im.";
                throw std::invalid_argument(o.str());
            }
            hist_min_max<std::uint16_t, false>((std::uint16_t*)im_info.ptr,
                                               im_info.shape.data(),
                                               im_info.strides.data(),
                                               (std::uint32_t*)hist_info.ptr,
                                               hist_info.strides[0],
                                               (std::uint16_t*)min_max_info.ptr,
                                               min_max_info.strides[0]);
        }
        else if(im_info.format == py::format_descriptor<std::uint32_t>::value())
        {
            if(hist_info.shape[0] != bin_count<std::uint32_t>())
            {
                std::ostringstream o;
                o << "hist argument must contain " << bin_count<std::uint32_t>() << " elements for uint32 im.";
                throw std::invalid_argument(o.str());
            }
            hist_min_max<std::uint32_t, false>((std::uint32_t*)im_info.ptr,
                                               im_info.shape.data(),
                                               im_info.strides.data(),
                                               (std::uint32_t*)hist_info.ptr,
                                               hist_info.strides[0],
                                               (std::uint32_t*)min_max_info.ptr,
                                               min_max_info.strides[0]);
        }
        else if(im_info.format == py::format_descriptor<std::uint64_t>::value())
        {
            if(hist_info.shape[0] != bin_count<std::uint64_t>())
            {
                std::ostringstream o;
                o << "hist argument must contain " << bin_count<std::uint64_t>() << " elements for uint64 im.";
                throw std::invalid_argument(o.str());
            }
            hist_min_max<std::uint64_t, false>((std::uint64_t*)im_info.ptr,
                                               im_info.shape.data(),
                                               im_info.strides.data(),
                                               (std::uint32_t*)hist_info.ptr,
                                               hist_info.strides[0],
                                               (std::uint64_t*)min_max_info.ptr,
                                               min_max_info.strides[0]);
        }
        else
            throw std::invalid_argument("Only uint8, uint16, uint32, and uint64 im buffers are supported.");
    }
}

void py_masked_hist_min_max(py::buffer im, py::buffer mask, py::buffer hist, py::buffer min_max, bool is_twelve_bit)
{
    py::buffer_info im_info{im.request()}, mask_info{mask.request()}, hist_info{hist.request()}, min_max_info{min_max.request()};
    if(im_info.ndim != 2)
        throw std::invalid_argument("im argument must be a 2 dimensional buffer object (such as a numpy array).");
    if(mask_info.ndim != 2)
        throw std::invalid_argument("mask argument must be a 2 dimensionsal buffer object (such as a numpy array).");
    if(mask_info.format != py::format_descriptor<std::uint8_t>::value())
        throw std::invalid_argument("mask argument format must be uint8 or bool.");
    if(hist_info.ndim != 1)
        throw std::invalid_argument("hist argument must be a 1 dimensional buffer object (such as a numpy array).");
    if(hist_info.format != py::format_descriptor<std::uint32_t>::value())
        throw std::invalid_argument("hist argument format must be uint32.");
    if(min_max_info.ndim != 1)
        throw std::invalid_argument("min_max arugment must be a 1 dimensional buffer object (such as a numpy array).");
    if(min_max_info.shape[0] != 2)
        throw std::invalid_argument("min_max argument must contain exactly 2 elements.");
    if(im_info.format != min_max_info.format)
        throw std::invalid_argument(
            "im and min_max arguments must be the same format (or dtype, in the case where they are numpy arays).");
    if(is_twelve_bit)
    {
        if(im_info.format == py::format_descriptor<std::uint16_t>::value())
        {
            if(hist_info.shape[0] != bin_count<std::uint16_t>())
            {
                std::ostringstream o;
                o << "hist argument must contain " << bin_count<std::uint16_t>() << " elements for uint16 im.";
                throw std::invalid_argument(o.str());
            }
            masked_hist_min_max<std::uint16_t, true>((std::uint16_t*)im_info.ptr,
                                                     im_info.shape.data(),
                                                     im_info.strides.data(),
                                                     (std::uint8_t*)mask_info.ptr,
                                                     mask_info.shape.data(),
                                                     mask_info.strides.data(),
                                                     (std::uint32_t*)hist_info.ptr,
                                                     hist_info.strides[0],
                                                     (std::uint16_t*)min_max_info.ptr,
                                                     min_max_info.strides[0]);
        }
        else
            throw std::invalid_argument("is_twelve_bit may be True only if im is uint16.");
    }
    else
    {
        if(im_info.format == py::format_descriptor<std::uint8_t>::value())
        {
            if(hist_info.shape[0] != bin_count<std::uint8_t>())
            {
                std::ostringstream o;
                o << "hist argument must contain " << bin_count<std::uint8_t>() << " elements for uint8 im.";
                throw std::invalid_argument(o.str());
            }
            masked_hist_min_max<std::uint8_t, false>((std::uint8_t*)im_info.ptr,
                                                     im_info.shape.data(),
                                                     im_info.strides.data(),
                                                     (std::uint8_t*)mask_info.ptr,
                                                     mask_info.shape.data(),
                                                     mask_info.strides.data(),
                                                     (std::uint32_t*)hist_info.ptr,
                                                     hist_info.strides[0],
                                                     (std::uint8_t*)min_max_info.ptr,
                                                     min_max_info.strides[0]);
        }
        else if(im_info.format == py::format_descriptor<std::uint16_t>::value())
        {
            if(hist_info.shape[0] != bin_count<std::uint8_t>())
            {
                std::ostringstream o;
                o << "hist argument must contain " << bin_count<std::uint16_t>() << " elements for uint16 im.";
                throw std::invalid_argument(o.str());
            }
            masked_hist_min_max<std::uint16_t, false>((std::uint16_t*)im_info.ptr,
                                                      im_info.shape.data(),
                                                      im_info.strides.data(),
                                                      (std::uint8_t*)mask_info.ptr,
                                                      mask_info.shape.data(),
                                                      mask_info.strides.data(),
                                                      (std::uint32_t*)hist_info.ptr,
                                                      hist_info.strides[0],
                                                      (std::uint16_t*)min_max_info.ptr,
                                                      min_max_info.strides[0]);
        }
        else if(im_info.format == py::format_descriptor<std::uint32_t>::value())
        {
            if(hist_info.shape[0] != bin_count<std::uint32_t>())
            {
                std::ostringstream o;
                o << "hist argument must contain " << bin_count<std::uint32_t>() << " elements for uint32 im.";
                throw std::invalid_argument(o.str());
            }
            masked_hist_min_max<std::uint32_t, false>((std::uint32_t*)im_info.ptr,
                                                      im_info.shape.data(),
                                                      im_info.strides.data(),
                                                      (std::uint8_t*)mask_info.ptr,
                                                      mask_info.shape.data(),
                                                      mask_info.strides.data(),
                                                      (std::uint32_t*)hist_info.ptr,
                                                      hist_info.strides[0],
                                                      (std::uint32_t*)min_max_info.ptr,
                                                      min_max_info.strides[0]);
        }
        else if(im_info.format == py::format_descriptor<std::uint64_t>::value())
        {
            if(hist_info.shape[0] != bin_count<std::uint64_t>())
            {
                std::ostringstream o;
                o << "hist argument must contain " << bin_count<std::uint64_t>() << " elements for uint64 im.";
                throw std::invalid_argument(o.str());
            }
            masked_hist_min_max<std::uint64_t, false>((std::uint64_t*)im_info.ptr,
                                                      im_info.shape.data(),
                                                      im_info.strides.data(),
                                                      (std::uint8_t*)mask_info.ptr,
                                                      mask_info.shape.data(),
                                                      mask_info.strides.data(),
                                                      (std::uint32_t*)hist_info.ptr,
                                                      hist_info.strides[0],
                                                      (std::uint64_t*)min_max_info.ptr,
                                                      min_max_info.strides[0]);
        }
        else
            throw std::invalid_argument("Only uint8, uint16, uint32, and uint64 im buffers are supported.");
    }
}

PYBIND11_PLUGIN(_ndimage_statistics)
{
    py::module m("_ndimage_statistics", "ris_widget.ndimage_statistics._ndimage_statistics module");

    m.def("min_max", &py_min_max);
    m.def("masked_min_max", &py_masked_min_max);
    m.def("ranged_hist", &py_ranged_hist);
    m.def("masked_ranged_hist", &py_masked_ranged_hist);
    m.def("hist_min_max", &py_hist_min_max);
    m.def("masked_hist_min_max", &py_masked_hist_min_max);

//  py::class_<Luts>(m, "Luts")
//      .def(py::init<const std::size_t&>())
//      .def("getLut", [](Luts& luts, const std::uint32_t& fromSamples, const std::uint32_t& toSamples){
//          luts.getLut(fromSamples, toSamples);
//      });

    return m.ptr();
}