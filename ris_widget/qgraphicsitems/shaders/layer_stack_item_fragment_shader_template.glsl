#version 120
#line 3
// This code is licensed under the MIT License (see LICENSE file for details)

uniform float layer_stack_item_opacity;
uniform float viewport_height;
uniform mat3 frag_to_tex;
$uniforms

vec2 transform_frag_to_tex()
{
    vec3 tex_coord_h = frag_to_tex * vec3(gl_FragCoord.x, viewport_height - gl_FragCoord.y, gl_FragCoord.w);
    return tex_coord_h.xy / tex_coord_h.z;
}

$color_transforms

void main()
{
    vec2 tex_coord = transform_frag_to_tex();
    vec4 s;
    vec3 channel_mapping;
    mat3 channel_mappings;
    float da;
    vec3 sca, dca;
    int i;
    float isa, ida, osa, oda, sada;

    if(tex_coord.x < 0.0f || tex_coord.x > 1.0f || tex_coord.y < 0.0f || tex_coord.y > 1.0f) discard;

$main
    gl_FragColor = vec4(dca / da, da * layer_stack_item_opacity);
}
