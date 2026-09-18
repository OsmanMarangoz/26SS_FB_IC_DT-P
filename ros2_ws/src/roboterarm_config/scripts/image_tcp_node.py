#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
import socket
import threading
import struct
import io
from PIL import Image as PILImage

class ImageTcpReceiver(Node):
    def __init__(self):
        super().__init__('image_tcp_receiver')
        self.declare_parameter('port', 5000)
        self.declare_parameter('topic', '/unity/camera_top/image_raw')
        
        port = self.get_parameter('port').value
        topic = self.get_parameter('topic').value
        
        self.pub = self.create_publisher(Image, topic, 10)
        
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(('0.0.0.0', port))
        self.server_sock.listen(1)
        
        self.get_logger().info(f"Listening for Unity TCP images on port {port}, publishing to {topic}")
        
        self.thread = threading.Thread(target=self.accept_loop, daemon=True)
        self.thread.start()

    def accept_loop(self):
        while True:
            conn, addr = self.server_sock.accept()
            self.get_logger().info(f"Unity connected from {addr}")
            self.receive_loop(conn)

    def receive_loop(self, conn):
        try:
            while True:
                length_bytes = self.recvall(conn, 4)
                if not length_bytes: break
                msg_len = struct.unpack('<I', length_bytes)[0]
                
                img_bytes = self.recvall(conn, msg_len)
                if not img_bytes: break
                
                # Decode JPG using Pillow instead of OpenCV (Headless-safe!)
                img = PILImage.open(io.BytesIO(img_bytes)).convert('RGB')
                
                # Create ROS2 Image message manually (No cv_bridge needed!)
                img_msg = Image()
                img_msg.header.stamp = self.get_clock().now().to_msg()
                img_msg.header.frame_id = "unity_camera"
                img_msg.height = img.height
                img_msg.width = img.width
                img_msg.encoding = "rgb8"
                img_msg.is_bigendian = 0
                img_msg.step = img.width * 3
                img_msg.data = img.tobytes()
                
                self.pub.publish(img_msg)
        except Exception as e:
            self.get_logger().warn(f"Connection closed: {e}")
        finally:
            conn.close()

    def recvall(self, sock, n):
        data = bytearray()
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return data

def main(args=None):
    rclpy.init(args=args)
    node = ImageTcpReceiver()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
