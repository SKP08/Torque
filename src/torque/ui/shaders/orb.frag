#version 440

layout(location = 0) out vec4 fragColor;

layout(location = 0) uniform float time;

void main()
{
    vec2 uv = gl_FragCoord.xy / vec2(180.0,180.0);

    uv = uv * 2.0 - 1.0;

    float d = length(uv);

    if(d > 1.0)
        discard;

    vec3 c1 = vec3(0.1,0.7,1.0);
    vec3 c2 = vec3(0.9,0.95,1.0);

    float wave =
        sin(uv.x*6.0 + time*1.8) *
        cos(uv.y*6.0 - time*1.4);

    wave = wave*0.5+0.5;

    vec3 color = mix(c1,c2,wave);

    float alpha = smoothstep(1.0,0.7,d);

    fragColor = vec4(color,alpha);
}