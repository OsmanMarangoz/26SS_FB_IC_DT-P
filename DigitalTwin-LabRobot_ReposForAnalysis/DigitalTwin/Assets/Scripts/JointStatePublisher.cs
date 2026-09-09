using UnityEngine;
using System.Collections;
using System.Text;
using System.Globalization;

/// <summary>
/// Publishes /joint_states to ROS via rosbridge at a fixed rate.
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
    private const string TOPIC   = "/joint_states";
    private const string MSG_TYPE = "sensor_msgs/msg/JointState";

    [Header("Publish Settings")]
    [Tooltip("How many /joint_states messages to send per second")]
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

        RosConnector.Instance.Advertise(TOPIC, MSG_TYPE);
        _advertised = true;
        Debug.Log("[JointStatePublisher] Advertised " + TOPIC);
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
        RosConnector.Instance.Publish(TOPIC, MSG_TYPE, json);
    }

    // Builds the JointState msg body (the part that goes into "msg": {...}).
    // Uses manual string building — JsonUtility cannot serialize string[].
    static string BuildMsg(string[] names, float[] positions)
    {
        var sb = new StringBuilder(512);

        // header
        sb.Append("{\"header\":{\"stamp\":{\"sec\":0,\"nanosec\":0},\"frame_id\":\"\"},");

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
}
