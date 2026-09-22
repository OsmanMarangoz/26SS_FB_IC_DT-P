using UnityEngine;

public class RandomPositionMover : MonoBehaviour
{
    [Header("Movement Settings")]
    [Tooltip("The object that will be moved. If left empty, this script will move the GameObject it's attached to.")]
    public Transform objectToMove;

    [Header("Area Settings")]
    [Tooltip("The BoxCollider defining the movement area. Make sure to check 'Is Trigger' so it doesn't interfere with physics.")]
    public BoxCollider movementArea;

    private void Start()
    {
        // Default to moving the object this script is attached to if nothing is assigned
        if (objectToMove == null)
        {
            objectToMove = transform;
        }

        if (movementArea == null)
        {
            Debug.LogWarning("RandomPositionMover: No BoxCollider assigned for the movement area!", this);
        }
    }

    /// <summary>
    /// Moves the target object to a random position within the assigned BoxCollider.
    /// Hook this method up to your Button's OnClick event in the inspector.
    /// </summary>
    public void MoveToRandomArea()
    {
        if (movementArea == null) 
        {
            Debug.LogError("Cannot move to random position. No movement area assigned.");
            return;
        }

        // Get the world-space boundaries of the BoxCollider
        Bounds bounds = movementArea.bounds;

        // Pick a random point between the minimum and maximum extents of the box
        float randomX = Random.Range(bounds.min.x, bounds.max.x);
        float randomY = Random.Range(bounds.min.y, bounds.max.y);
        float randomZ = Random.Range(bounds.min.z, bounds.max.z);

        Vector3 randomPosition = new Vector3(randomX, randomY, randomZ);

        // Apply the new position
        objectToMove.position = randomPosition;
        objectToMove.rotation = Quaternion.identity;
    }
}

