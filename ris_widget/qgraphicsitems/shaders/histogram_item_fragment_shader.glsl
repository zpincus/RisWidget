#version 120
#line 3
// This code is licensed under the MIT License (see LICENSE file for details)

uniform sampler1D tex;
uniform vec2 inv_view_size;
uniform float inv_max_transformed_bin_val;
uniform float gamma_gamma;
uniform float opacity;

void main()
{
    float bin_value = texture1D(tex, gl_FragCoord.x * inv_view_size.x).r * 4294967295.0f;
    float bin_height = pow(bin_value, gamma_gamma) * inv_max_transformed_bin_val;
    float intensity = 1.0f - clamp(floor((gl_FragCoord.y * inv_view_size.y) / bin_height), 0, 1);

    gl_FragColor = vec4(intensity, intensity, intensity, intensity * opacity);
}
