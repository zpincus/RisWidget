#version 120
#line 3
// This code is licensed under the MIT License (see LICENSE file for details)

attribute vec2 vert_coord;

void main()
{
    gl_Position = vec4(vert_coord, 0.5, 1.0);
}
