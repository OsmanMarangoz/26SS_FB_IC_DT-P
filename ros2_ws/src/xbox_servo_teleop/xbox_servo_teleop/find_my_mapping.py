#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy

class JoyMapper(Node):
    def __init__(self):
        super().__init__('joy_mapper')
        # Subscribing zum Standard joy topic
        self.sub = self.create_subscription(Joy, '/joy', self.joy_callback, 10)

        self.last_buttons = []
        self.last_reported_axes = []

        self.get_logger().info("🎮 Joy Mapper gestartet!")
        self.get_logger().info("Drücke Knöpfe oder bewege Sticks, um dein Mapping zu sehen...")

    def joy_callback(self, msg):
        # Beim allerersten Signal speichern wir den "Ruhezustand" ab
        if not self.last_buttons:
            self.last_buttons = list(msg.buttons)
            self.last_reported_axes = list(msg.axes)
            return

        # 1. Knöpfe prüfen (nur Änderungen loggen)
        for i, (curr, prev) in enumerate(zip(msg.buttons, self.last_buttons)):
            if curr == 1 and prev == 0:
                self.get_logger().info(f"🟢 BUTTON gedrückt: Index [ {i} ]")
            elif curr == 0 and prev == 1:
                self.get_logger().info(f"⭕ BUTTON losgelassen: Index [ {i} ]")

        # 2. Achsen prüfen (Stick-Drift ignorieren)
        for i, (curr, prev) in enumerate(zip(msg.axes, self.last_reported_axes)):
            # Wir loggen nur, wenn sich die Achse um mehr als 0.2 ändert.
            # Das filtert das Rauschen (Stick-Drift) heraus.
            if abs(curr - prev) > 0.2:
                self.get_logger().info(f"🕹️ ACHSE bewegt: Index [ {i} ] | Neuer Wert: {curr:.2f}")
                # Update den zuletzt gemeldeten Wert
                self.last_reported_axes[i] = curr

        # Aktuellen Button-State für den nächsten Zyklus speichern
        self.last_buttons = list(msg.buttons)

def main(args=None):
    rclpy.init(args=args)
    node = JoyMapper()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()