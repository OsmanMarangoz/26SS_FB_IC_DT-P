using UnityEngine;
using UnityEngine.UI;

public class StatusMonitor : MonoBehaviour
{
    [Header("1. Physical Collision Tracking")]
    [Tooltip("Drag the Collider you want to physically touch here")]
    public Collider targetCollider; 
    public Image collisionStatusImage;

    [Header("2. Zone Tracking (Inside the Box)")]
    [Tooltip("Drag the Box Collider (the safe zone) here")]
    public BoxCollider targetZoneCollider;
    public Image zoneStatusImage;

    void Start()
    {
        // Initialize to red
        if (collisionStatusImage != null) collisionStatusImage.color = Color.red;
        if (zoneStatusImage != null) zoneStatusImage.color = Color.red;
    }

    void Update()
    {
        CheckIfInsideZone();
    }

    // --- 1. COLLISION LOGIC ---
    private void OnTriggerEnter(Collider other)
    {
        if (other == targetCollider && collisionStatusImage != null)
            collisionStatusImage.color = Color.green;
    }

    private void OnTriggerExit(Collider other)
    {
        if (other == targetCollider && collisionStatusImage != null)
            collisionStatusImage.color = Color.red;
    }

    private void OnCollisionEnter(Collision collision)
    {
        if (collision.collider == targetCollider && collisionStatusImage != null)
            collisionStatusImage.color = Color.green;
    }

    private void OnCollisionExit(Collision collision)
    {
        if (collision.collider == targetCollider && collisionStatusImage != null)
            collisionStatusImage.color = Color.red;
    }

    // --- 2. ZONE LOGIC ---
    private void CheckIfInsideZone()
    {
        if (targetZoneCollider != null && zoneStatusImage != null)
        {
            // 1. Get the world position center of our Sphere Collider
            SphereCollider mySphere = GetComponent<SphereCollider>();
            Vector3 myCenter = (mySphere != null) ? mySphere.bounds.center : transform.position;

            // 2. The absolute best way to check if a point is inside a rotated box in Unity:
            // ClosestPoint returns the exact same point if the point is already INSIDE the collider volume.
            Vector3 closestPoint = targetZoneCollider.ClosestPoint(myCenter);

            // 3. If the distance is basically zero, our sphere's center is inside the box!
            if (Vector3.Distance(myCenter, closestPoint) < 0.001f)
            {
                zoneStatusImage.color = Color.green;
            }
            else
            {
                zoneStatusImage.color = Color.red;
            }
        }
    }
}