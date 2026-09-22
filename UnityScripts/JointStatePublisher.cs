using UnityEngine;
using System.Collections;
using System.Text;
using System.Globalization;

/// <summary>
/// Publishes Unity's simulated joint state to ROS via rosbridge at a fixed rate.
///
/// Data flow:
///   Xbox → joy_to_tcp_jac_node → /servo_joint_target
///       → RobotStateReceiver (drives Unity joints, stores posRad)
///           → JointStatePublisher (reads posRad back, publishes /joint_states)
///               → robot_state_publisher (TF) + LeRobot NemaArm (observation)
///
/// Setup in Unity Inspector:
///   1. Add this component to the same GameObject as RobotStateReceiver
///      (or assign the Receiver field manually).
///   2. Verify jointNames matches your URDF (order does not matter for ROS).
/// </summary>
public class JointStatePublisher : MonoBehaviour
{
    private const string MSG_TYPE = "sensor_msgs/msg/JointState";
    private const string UNITY_TOPIC = "/joint_states";

    [Header("Publish Settings")]
    [Tooltip("How many Unity joint-state messages to send per second")]
    public float publishRateHz = 50f;

    [Header("Joint Source")]
    [Tooltip("The RobotStateReceiver on this robot. Auto-found if left empty.")]
    public RobotStateReceiver receiver;

    [Header("Joint Names (must match URDF exactly)")]
    public string[] jointNames = new string[]
    {
        "joint_basis_arm1",
        "joint_arm1_arm2",
        "joint_arm2_arm3",
        "joint_arm3_greifer",
        "joint_greifer_finger1",
        "joint_greifer_finger2",
        "joint_greifer_finger3",
    };

    // ── internals ──────────────────────────────────────────────────────────
    private bool  _advertised = false;
    private float _nextPublishTime;

    void Start()
    {
        if (receiver == null)
            receiver = GetComponent<RobotStateReceiver>();

        if (receiver == null)
            receiver = FindObjectOfType<RobotStateReceiver>();

        if (receiver == null)
            Debug.LogError("[JointStatePublisher] No RobotStateReceiver found! Assign it in the Inspector.");

        _nextPublishTime = Time.time + 1f; // 1 s startup grace period

        StartCoroutine(AdvertiseOnConnect());
    }

    IEnumerator AdvertiseOnConnect()
    {
        while (RosConnector.Instance == null)
            yield return new WaitForSeconds(0.5f);
        while (!RosConnector.Instance.IsConnected)
            yield return new WaitForSeconds(0.5f);

        RosConnector.Instance.Advertise(UNITY_TOPIC, MSG_TYPE);
        _advertised = true;
        // Debug.Log("[JointStatePublisher] Advertised " + UNITY_TOPIC);
    }

    void Update()
    {
        if (!_advertised) return;
        if (receiver == null) return;
        if (RosConnector.Instance == null || !RosConnector.Instance.IsConnected) return;

        if (Time.time < _nextPublishTime) return;
        _nextPublishTime = Time.time + (1f / publishRateHz);

        PublishJointStates();
    }

    void PublishJointStates()
    {
        float[] positions = new float[jointNames.Length];
        for (int i = 0; i < jointNames.Length; i++)
            positions[i] = receiver.GetPositionRad(jointNames[i]);

        string json = BuildMsg(jointNames, positions);
        RosConnector.Instance.Publish(UNITY_TOPIC, MSG_TYPE, json);
    }

    // Builds the JointState msg body (the part that goes into "msg": {...}).
    // Uses manual string building — JsonUtility cannot serialize string[].
    static string BuildMsg(string[] names, float[] positions)
    {
        var sb = new StringBuilder(512);

        // Calculate Unix timestamp
        long ticks = System.DateTime.UtcNow.Ticks - new System.DateTime(1970, 1, 1).Ticks;
        long sec = ticks / 10000000L;
        long nanosec = (ticks % 10000000L) * 100;

        // header
        sb.Append($"{{\"header\":{{\"stamp\":{{\"sec\":{sec},\"nanosec\":{nanosec}}},\"frame_id\":\"\"}},");

        // name array
        sb.Append("\"name\":[");
        for (int i = 0; i < names.Length; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append('"'); sb.Append(names[i]); sb.Append('"');
        }
        sb.Append("],");

        // position array
        sb.Append("\"position\":[");
        for (int i = 0; i < positions.Length; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append(positions[i].ToString("F6", CultureInfo.InvariantCulture));
        }
        sb.Append("],");

        // velocity and effort (empty — robot_state_publisher only needs position)
        sb.Append("\"velocity\":[],\"effort\":[]}");

        return sb.ToString();
    }

    /// <summary>
    /// Sets the joint states to a specific calibration pose on button press.
    /// You can link this method to a Unity UI Button's onClick event.
    /// </summary>
    public void SetCalibrationPose()
    {
        float[] calibPose = new float[] {
            -3.122357f,
            -0.039613f,
            -1.820313f,
            -1.284314f,
            0.0f,
            0.0f,
            0.0f
        };

        // 1. Update the visual robot state immediately
        if (receiver != null)
        {
            // Ignore incoming ROS messages for 0.5s to prevent race condition bounce-back
            receiver.IgnoreIncoming(0.5f);

            for (int i = 0; i < jointNames.Length && i < calibPose.Length; i++)
            {
                receiver.UpdateJoint(jointNames[i], calibPose[i]);
            }
        }

        // 2. Publish to /joint_states
        if (RosConnector.Instance != null && RosConnector.Instance.IsConnected && _advertised)
        {
            string json = BuildMsg(jointNames, calibPose);
            RosConnector.Instance.Publish(UNITY_TOPIC, MSG_TYPE, json);
            Debug.Log("[JointStatePublisher] SetCalibrationPose triggered. Published to /joint_states.");
        }
    }
}
