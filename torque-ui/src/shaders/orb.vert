varying vec3 vPosition;
varying vec3 vWorldPosition;
varying vec3 vNormal;

void main()
{
    vPosition = position;

    vNormal = normalize(normalMatrix * normal);

    vec4 worldPosition = modelMatrix * vec4(position, 1.0);

    vWorldPosition = worldPosition.xyz;

    gl_Position =
        projectionMatrix *
        viewMatrix *
        worldPosition;
}