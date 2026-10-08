import QtQuick

Item {
    id: root

    width: 180
    height: 180

    property real t: 0

    Timer {
        interval: 16
        running: true
        repeat: true

        onTriggered: {
            root.t += 0.016
        }
    }

    ShaderEffect {

        anchors.fill: parent

        property real time: root.t

        fragmentShader: "qrc:/shaders/orb.frag"
    }
}