import QtQuick
import QtQuick.Window

Window {
    id: root

    visible: true

    flags: Qt.FramelessWindowHint
         | Qt.WindowStaysOnTopHint
         | Qt.Tool

    color: "transparent"

    width: 500
    height: 500

    minimumWidth: width
    minimumHeight: height
    maximumWidth: width
    maximumHeight: height

    x: (Screen.width - width) / 2
    y: (Screen.height - height) / 2

    Orb {
        anchors.centerIn: parent
    }
}