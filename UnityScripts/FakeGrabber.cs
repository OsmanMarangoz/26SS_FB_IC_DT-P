using UnityEngine;
using System.Collections.Generic;

[RequireComponent(typeof(SphereCollider))]
public class FakeGrabber : MonoBehaviour
{
    [Header("ROS 2 Integration (Recommended)")]
    [Tooltip("If assigned, reads the raw ROS joint state directly. This avoids Unity Transform axis quirks.")]
    public RobotStateReceiver robotStateReceiver;
    
    [Tooltip("The exact ROS joint name for the finger (e.g., joint_greifer_finger1)")]
    public string gripperJointName = "joint_greifer_finger1";

    [Header("Transform Fallback (If RobotStateReceiver is empty)")]
    public Transform gripperFinger;
    public bool monitorRotation = false;
    public enum Axis { X, Y, Z }
    public Axis monitorAxis = Axis.Z;

    [Header("Thresholds")]
    [Tooltip("Value at which the gripper is considered closed (e.g., 0.05)")]
    public float closedThreshold = 0.05f;
    [Tooltip("Value at which the gripper is considered open (e.g., 0.35)")]
    public float openThreshold = 0.35f;

    [Header("Grabbing Logic")]
    public string interactableTag = "Interactable";

    private bool isGripperClosed = false;
    private Rigidbody currentlyGrabbedObject = null;
    private HashSet<Rigidbody> objectsInRange = new HashSet<Rigidbody>();

    void Start()
    {
        // Ensure the collider is set to trigger
        GetComponent<Collider>().isTrigger = true;
    }

    void Update()
    {
        float currentValue = 0f;

        // 1. Get the current value of the gripper finger
        if (robotStateReceiver != null)
        {
            currentValue = robotStateReceiver.GetPositionRad(gripperJointName);
        }
        else if (gripperFinger != null)
        {
            Vector3 vec = monitorRotation ? gripperFinger.localEulerAngles : gripperFinger.localPosition;
            switch (monitorAxis)
            {
                case Axis.X: currentValue = vec.x; break;
                case Axis.Y: currentValue = vec.y; break;
                case Axis.Z: currentValue = vec.z; break;
            }
            
            // Handle Unity Euler angle wrap-around if monitoring rotation near 0
            if (monitorRotation && currentValue > 180f) currentValue -= 360f;
        }
        else
        {
            return; // No monitoring source assigned, do nothing
        }

        // 2. Check value against open/closed thresholds
        bool isNowClosed = false;
        bool isNowOpen = false;

        if (closedThreshold < openThreshold)
        {
            isNowClosed = currentValue <= closedThreshold;
            isNowOpen = currentValue >= openThreshold;
        }
        else
        {
            isNowClosed = currentValue >= closedThreshold;
            isNowOpen = currentValue <= openThreshold;
        }

        if (!isGripperClosed && isNowClosed)
        {
            isGripperClosed = true;
            GrabNearestObject();
        }
        else if (isGripperClosed && isNowOpen)
        {
            isGripperClosed = false;
            ReleaseObject();
        }
    }

    private void GrabNearestObject()
    {
        if (currentlyGrabbedObject != null) return;

        // Clean up any destroyed objects from the set
        objectsInRange.RemoveWhere(rb => rb == null);

        Rigidbody nearest = null;
        float minDistance = float.MaxValue;

        // Find the nearest Rigidbody in range
        foreach (Rigidbody rb in objectsInRange)
        {
            float dist = Vector3.Distance(transform.position, rb.transform.position);
            if (dist < minDistance)
            {
                minDistance = dist;
                nearest = rb;
            }
        }

        // Execute Grab
        if (nearest != null)
        {
            currentlyGrabbedObject = nearest;
            currentlyGrabbedObject.isKinematic = true;
            currentlyGrabbedObject.transform.SetParent(this.transform, true);
        }
    }

    private void ReleaseObject()
    {
        // Execute Release
        if (currentlyGrabbedObject != null)
        {
            currentlyGrabbedObject.transform.SetParent(null, true);
            currentlyGrabbedObject.isKinematic = false;
            currentlyGrabbedObject = null;
        }
    }

    private void OnTriggerEnter(Collider other)
    {
        if (other.CompareTag(interactableTag))
        {
            Rigidbody rb = other.GetComponentInParent<Rigidbody>();
            if (rb != null)
            {
                objectsInRange.Add(rb);
            }
        }
    }

    private void OnTriggerExit(Collider other)
    {
        if (other.CompareTag(interactableTag))
        {
            Rigidbody rb = other.GetComponentInParent<Rigidbody>();
            if (rb != null)
            {
                objectsInRange.Remove(rb);
            }
        }
    }
}

