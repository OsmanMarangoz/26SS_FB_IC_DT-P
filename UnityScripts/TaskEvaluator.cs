using UnityEngine;
using System.IO;
using System.Collections;
using System;
public class TaskEvaluator : MonoBehaviour
{
    [Header("GameObjects & Colliders")]
    [Tooltip("The Lego brick (must have a Rigidbody and Collider)")]
    public GameObject targetObject;
    
    [Tooltip("The collider of the table")]
    public Collider tableCollider;
    
    [Tooltip("The trigger collider of the gripper (FakeGrabber)")]
    public Collider gripperCollider;
    
    [Tooltip("The trigger collider of the target box")]
    public Collider targetBoxTrigger;

    [Header("Evaluation Settings")]
    [Tooltip("How high off the table the object must be to count as 'picked'")]
    public float liftThreshold = 0.05f;

    [Tooltip("Optional: The script that randomizes the Lego brick's position")]
    public RandomPositionMover randomMover;
    // State Tracking
    private int currentEpisodeId = -1;
    private bool is_picked = false;
    private bool is_dropped = false;
    private bool is_placed = false;
    private string csvFilePath;
    void Start()
    {
        // Set CSV path to the Unity project root (one folder above the Assets folder)
        csvFilePath = Path.Combine(Application.dataPath, "../lerobot_eval_metrics.csv");
        
        // Write headers if the file doesn't exist
        if (!File.Exists(csvFilePath))
        {
            File.WriteAllText(csvFilePath, "episode_id,is_picked,is_dropped,is_placed,is_success\n");
        }
        // Automatically attach the physics reporter to the target object so we don't 
        // have to manually configure the Lego brick in the editor.
        if (targetObject != null)
        {
            PhysicsReporter reporter = targetObject.AddComponent<PhysicsReporter>();
            reporter.evaluator = this;
        }
        else
        {
            Debug.LogError("TaskEvaluator: Target Object is not assigned!");
        }

        // Connect to RosBridge for episode triggers
        StartCoroutine(SubscribeToEpisodeTopic());
    }

    private IEnumerator SubscribeToEpisodeTopic()
    {
        while (RosConnector.Instance == null || !RosConnector.Instance.IsConnected)
        {
            yield return new WaitForSeconds(0.5f);
        }
        
        Debug.Log("[Evaluator] Connected to ROS. Subscribing to /lerobot/episode...");
        RosConnector.Instance.Subscribe("/lerobot/episode", "std_msgs/msg/Int32", OnEpisodeMessageReceived);
    }

    private void OnEpisodeMessageReceived(string jsonString)
    {
        try
        {
            EpisodeRosMessage packet = JsonUtility.FromJson<EpisodeRosMessage>(jsonString);
            if (packet != null && packet.msg != null)
            {
                int epId = packet.msg.data;
                if (epId >= 0)
                {
                    StartEpisode(epId);
                }
                else
                {
                    EndEpisode();
                }
            }
        }
        catch (Exception e)
        {
            Debug.LogWarning("[Evaluator] Error parsing episode message: " + e.Message);
        }
    }

    void Update()
    {
        if (currentEpisodeId == -1) return;

        // Grasp Success (is_picked) via Hierarchy Check
        if (!is_picked && targetObject != null && gripperCollider != null)
        {
            if (targetObject.transform.IsChildOf(gripperCollider.transform))
            {
                is_picked = true;
            }
        }
    }

    /// <summary>
    /// Resets the tracking variables at the beginning of a new run.
    /// Call this from your robot reset/rollout script.
    /// </summary>
    public void StartEpisode(int episodeId)
    {
        if (currentEpisodeId != -1 && currentEpisodeId != episodeId)
        {
            EndEpisode();
        }

        currentEpisodeId = episodeId;
        is_picked = false;
        is_dropped = false;
        is_placed = false;
        Debug.Log($"[Evaluator] Started Episode {episodeId}");
    }
    /// <summary>
    /// Evaluates the final conditions and appends to the CSV.
    /// Call this when the rollout duration is over or task is complete.
    /// </summary>
    public void EndEpisode()
    {
        if (currentEpisodeId == -1) return; // Episode never started
        bool is_success = is_placed && !is_dropped;
        
        string row = $"{currentEpisodeId},{is_picked},{is_dropped},{is_placed},{is_success}\n";
        File.AppendAllText(csvFilePath, row);
        
        Debug.Log($"[Evaluator] Ended Episode {currentEpisodeId} | Success: {is_success}");
        currentEpisodeId = -1; // Lock until next start

        // Trigger delayed randomization
        if (randomMover != null)
        {
            StartCoroutine(DelayRandomMove(2f));
        }
    }

    private IEnumerator DelayRandomMove(float delay)
    {
        yield return new WaitForSeconds(delay);
        if (randomMover != null)
        {
            randomMover.MoveToRandomArea();
        }
    }

    // --- Physics Event Handlers called by the Reporter ---
    public void HandleCollisionEnter(Collision collision)
    {
        if (currentEpisodeId == -1) return;
        // Transit Loss (is_dropped): Was picked, isn't placed yet, and hit the table.
        if (is_picked && !is_placed && collision.collider == tableCollider)
        {
            is_dropped = true;
        }
    }
    public void HandleTriggerStay(Collider other)
    {
        if (currentEpisodeId == -1) return;
        
        // Place Success (is_placed)
        if (!is_placed && other == targetBoxTrigger)
        {
            // True if the object's center is inside the target box's trigger collider.
            if (targetBoxTrigger.bounds.Contains(targetObject.transform.position))
            {
                is_placed = true;
            }
        }
    }
}

[Serializable]
public class EpisodeMsgData
{
    public int data;
}

[Serializable]
public class EpisodeRosMessage
{
    public string op;
    public string topic;
    public EpisodeMsgData msg;
}

/// <summary>
/// A lightweight helper class attached to the target object at runtime.
/// It catches physics events and forwards them to the evaluator.
/// </summary>
public class PhysicsReporter : MonoBehaviour
{
    public TaskEvaluator evaluator;
    private void OnCollisionEnter(Collision collision)
    {
        if (evaluator != null) evaluator.HandleCollisionEnter(collision);
    }
    private void OnTriggerStay(Collider other)
    {
        if (evaluator != null) evaluator.HandleTriggerStay(other);
    }
}

