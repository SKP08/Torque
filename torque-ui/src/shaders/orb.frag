uniform float time;

varying vec3 vPosition;
varying vec3 vWorldPosition;
varying vec3 vNormal;

// ------------------------------------------------------------
// Random
// ------------------------------------------------------------

float hash(vec3 p)
{
    p = fract(p * 0.3183099 + 0.1);
    p *= 17.0;

    return fract(
        p.x *
        p.y *
        p.z *
        (p.x + p.y + p.z)
    );
}

// ------------------------------------------------------------
// 3D Noise
// ------------------------------------------------------------

float noise(vec3 p)
{
    vec3 i = floor(p);
    vec3 f = fract(p);

    f = f * f * (3.0 - 2.0 * f);

    float n000 = hash(i + vec3(0.0,0.0,0.0));
    float n100 = hash(i + vec3(1.0,0.0,0.0));
    float n010 = hash(i + vec3(0.0,1.0,0.0));
    float n110 = hash(i + vec3(1.0,1.0,0.0));

    float n001 = hash(i + vec3(0.0,0.0,1.0));
    float n101 = hash(i + vec3(1.0,0.0,1.0));
    float n011 = hash(i + vec3(0.0,1.0,1.0));
    float n111 = hash(i + vec3(1.0,1.0,1.0));

    float nx00 = mix(n000,n100,f.x);
    float nx10 = mix(n010,n110,f.x);
    float nx01 = mix(n001,n101,f.x);
    float nx11 = mix(n011,n111,f.x);

    float nxy0 = mix(nx00,nx10,f.y);
    float nxy1 = mix(nx01,nx11,f.y);

    return mix(nxy0,nxy1,f.z);
}

// ------------------------------------------------------------
// FBM
// ------------------------------------------------------------

float fbm(vec3 p)
{
    float value = 0.0;
    float amp = 0.5;

    for(int i=0;i<6;i++)
    {
        value += amp * noise(p);

        p *= 2.0;

        amp *= 0.5;
    }

    return value;
}

// ------------------------------------------------------------

void main()
{
    vec3 p = normalize(vPosition);

    float n1 = fbm(
    p * 3.5 +
    vec3(
        time * 0.22,
        time * 0.18,
        time * 0.12
    )
);

float n2 = fbm(
    p.yzx * 4.2 -
    vec3(
        time * 0.17,
        time * 0.23,
        time * 0.14
    )
);

float n3 = fbm(
    p.zxy * 5.1 +
    vec3(
        time * 0.10,
        time * 0.16,
        time * 0.25
    )
);

float n =
    (n1 * 0.55) +
    (n2 * 0.30) +
    (n3 * 0.15);
   

vec3 deep = vec3(0.02,0.06,0.55);

vec3 blue = vec3(0.05,0.45,1.0);

vec3 cyan = vec3(0.15,0.95,1.0);

vec3 purple = vec3(0.72,0.25,1.0);

vec3 white = vec3(1.0);

float plasma =
    smoothstep(0.20,0.85,n);

vec3 color =
    mix(
        deep,
        blue,
        plasma
    );

color =
    mix(
        color,
        cyan,
        smoothstep(0.45,0.72,n)
    );

color =
    mix(
        color,
        purple,
        smoothstep(0.70,0.90,n)
    );

color =
    mix(
        color,
        white,
        pow(n,6.0)
    );

//----------------------------------
// Glass Fresnel
//----------------------------------

float fresnel =
    pow(
        1.0 -
        max(
            dot(
                normalize(vNormal),
                normalize(vec3(0.0,0.0,1.0))
            ),
            0.0
        ),
        2.8
    );

color += fresnel * vec3(0.25,0.65,1.35);

gl_FragColor = vec4(color,1.0);
}