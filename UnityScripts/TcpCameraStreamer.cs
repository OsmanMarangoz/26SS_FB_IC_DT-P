using UnityEngine;
using System.Net.Sockets;
using System.IO;

[RequireComponent(typeof(Camera))]
public class TcpCameraStreamer : MonoBehaviour
{
    [Header("Network Settings")]
    public string targetIP = "192.168.1.111"; // IP address of the Raspberry Pi
    public int targetPort = 5000;
    
    [Header("Image Settings")]
    public int width = 640;
    public int height = 480;
    [Range(10, 100)] public int jpgQuality = 50;
    public float targetFPS = 15f;
    
    private TcpClient _client;
    private NetworkStream _stream;
    private float _nextFrameTime;
    private Camera _cam;
    private RenderTexture _rt;
    private Texture2D _tex;

    void Start()
    {
        _cam = GetComponent<Camera>();
        _rt = new RenderTexture(width, height, 24);
        _tex = new Texture2D(width, height, TextureFormat.RGB24, false);
        _nextFrameTime = Time.time;
        
        Connect();
    }

    void Connect()
    {
        try {
            _client = new TcpClient();
            _client.Connect(targetIP, targetPort);
            _stream = _client.GetStream();
            Debug.Log("<color=green>[TcpCameraStreamer] Connected to ROS2 Image Node!</color>");
        } catch (System.Exception e) {
            Debug.LogWarning("[TcpCameraStreamer] Connection failed: " + e.Message);
        }
    }

    void Update()
    {
        if (Time.time < _nextFrameTime) return;
        
        if (_client == null || !_client.Connected)
        {
            Connect();
            if (_client == null || !_client.Connected) return; // Still not connected
        }

        _nextFrameTime = Time.time + (1f / targetFPS);
        
        // Render current camera view to texture
        var prevTarget = _cam.targetTexture;
        var prevActive = RenderTexture.active;
        
        _cam.targetTexture = _rt;
        _cam.Render();
        
        RenderTexture.active = _rt;
        _tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
        _tex.Apply();
        
        _cam.targetTexture = prevTarget;
        RenderTexture.active = prevActive;
        
        // Compress to JPG (much smaller payload than raw pixels)
        byte[] jpgBytes = _tex.EncodeToJPG(jpgQuality);
        
        try {
            // Write length (4 bytes, Little Endian)
            byte[] lengthBytes = System.BitConverter.GetBytes(jpgBytes.Length);
            if (!System.BitConverter.IsLittleEndian) System.Array.Reverse(lengthBytes); // ensure little endian
            
            _stream.Write(lengthBytes, 0, 4);
            
            // Write JPG payload
            _stream.Write(jpgBytes, 0, jpgBytes.Length);
        } catch {
            Debug.LogWarning("[TcpCameraStreamer] Connection lost. Reconnecting...");
            if (_stream != null) _stream.Close();
            if (_client != null) _client.Close();
            _client = null;
        }
    }

    void OnDestroy()
    {
        if (_stream != null) _stream.Close();
        if (_client != null) _client.Close();
        if (_rt != null) _rt.Release();
        Destroy(_tex);
    }
}
