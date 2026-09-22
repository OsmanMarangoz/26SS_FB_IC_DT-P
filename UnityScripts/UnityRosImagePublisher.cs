using UnityEngine;
using System;
using System.Collections;
using System.Text;

public class UnityRosImagePublisher : MonoBehaviour
{
    [Header("RenderTextures")]
    public RenderTexture topRenderTexture;
    public RenderTexture sideRenderTexture;

    [Header("Image Settings")]
    public int width = 640;
    public int height = 480;

    [Header("Publish Settings")]
    public float publishFps = 15f;
    public string topTopic = "/unity/camera_top/image_raw";
    public string sideTopic = "/unity/camera_side/image_raw";
    
    private const string MSG_TYPE = "sensor_msgs/msg/Image";
    
    private Texture2D _readTex;
    private Color32[] _pixelBuffer;
    private byte[] _rgbBuffer;
    private bool _advertised = false;
    private float _nextPublishTime;
    
    void Start()
    {
        if (topRenderTexture == null && sideRenderTexture == null)
            Debug.LogError("[ImagePublisher] No RenderTexture assigned! Please assign at least one RenderTexture.");
        if (topRenderTexture == null)
            Debug.LogWarning("[ImagePublisher] topRenderTexture not assigned. Top camera will not be published.");
        if (sideRenderTexture == null)
            Debug.LogWarning("[ImagePublisher] sideRenderTexture not assigned. Side camera will not be published.");
            
        // Pre-allocate arrays and texture
        _readTex = new Texture2D(width, height, TextureFormat.RGBA32, false);
        _pixelBuffer = new Color32[width * height];
        _rgbBuffer = new byte[width * height * 3];
        
        _nextPublishTime = Time.time + 1f;
        StartCoroutine(AdvertiseOnConnect());
    }
    
    IEnumerator AdvertiseOnConnect()
    {
        while (RosConnector.Instance == null)
            yield return new WaitForSeconds(0.5f);
        while (!RosConnector.Instance.IsConnected)
            yield return new WaitForSeconds(0.5f);
            
        if (topRenderTexture != null)
            RosConnector.Instance.Advertise(topTopic, MSG_TYPE);
        if (sideRenderTexture != null)
            RosConnector.Instance.Advertise(sideTopic, MSG_TYPE);
        
        _advertised = true;
        Debug.Log("[ImagePublisher] Advertised camera topics.");
    }
    
    void Update()
    {
        if (!_advertised) return;
        if (RosConnector.Instance == null || !RosConnector.Instance.IsConnected) return;
        if (Time.time < _nextPublishTime) return;
        _nextPublishTime = Time.time + (1f / publishFps);
        
        if (topRenderTexture != null)
            CaptureAndPublish(topRenderTexture, topTopic, "camera_top");
        if (sideRenderTexture != null)
            CaptureAndPublish(sideRenderTexture, sideTopic, "camera_side");
    }
    
    void CaptureAndPublish(RenderTexture rt, string topic, string frameId)
    {
        // Save and set active RT
        RenderTexture prev = RenderTexture.active;
        RenderTexture.active = rt;
        
        // Read pixels from RT into Texture2D
        _readTex.ReadPixels(new Rect(0, 0, width, height), 0, 0, false);
        _readTex.Apply(false);
        
        // Restore
        RenderTexture.active = prev;
        
        // Get pixels (bottom-up order from Unity)
        _pixelBuffer = _readTex.GetPixels32();
        
        // Convert RGBA32 -> RGB8, flipping vertically
        int rgbIdx = 0;
        for (int row = height - 1; row >= 0; row--)
        {
            int rowStart = row * width;
            for (int col = 0; col < width; col++)
            {
                Color32 c = _pixelBuffer[rowStart + col];
                _rgbBuffer[rgbIdx++] = c.r;
                _rgbBuffer[rgbIdx++] = c.g;
                _rgbBuffer[rgbIdx++] = c.b;
                // Alpha (c.a) is intentionally discarded
            }
        }
        
        // Build JSON message
        string base64Data = Convert.ToBase64String(_rgbBuffer);
        
        int step = width * 3;
        StringBuilder sb = new StringBuilder();
        sb.Append("{\"header\":{\"stamp\":{\"sec\":0,\"nanosec\":0},\"frame_id\":\"");
        sb.Append(frameId);
        sb.Append("\"},\"height\":");
        sb.Append(height);
        sb.Append(",\"width\":");
        sb.Append(width);
        sb.Append(",\"encoding\":\"rgb8\",\"is_bigendian\":0,\"step\":");
        sb.Append(step);
        sb.Append(",\"data\":\"");
        sb.Append(base64Data);
        sb.Append("\"}");
        
        // Publish
        RosConnector.Instance.Publish(topic, MSG_TYPE, sb.ToString());
    }
    
    void OnDestroy()
    {
        if (_readTex != null)
            Destroy(_readTex);
    }
}

