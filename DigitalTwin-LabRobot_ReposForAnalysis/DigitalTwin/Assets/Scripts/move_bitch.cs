using UnityEngine;

public class MoveToPosition : MonoBehaviour
{
    [Header("Verknüpfungen")]
    public RobotAPIController apiController;
    public Transform robotBase;
    public Transform tcpBall; // Die Sphere/Ball die gedraggt wird

    [Header("Einstellungen")]
    public float unityToMmScale = 1000f;

    [Header("Positionen (World Space)")]
    public Vector3 positionA = new Vector3(0.1027654f, -0.02673045f, -0.2500109f);
    public Vector3 positionB = new Vector3(-0.1141903f, -0.04836801f, -0.2535665f);

    public void MoveToA()
    {
        MoveTo(positionA);
    }

    public void MoveToB()
    {
        MoveTo(positionB);
    }

    private void MoveTo(Vector3 worldPos)
    {
        // 1. Ball hinbewegen (genau wie beim Drag)
        tcpBall.position = worldPos;

        // 2. UI-Felder updaten
        UpdateUI(worldPos);

        // 3. Roboter-API triggern
        if (apiController != null)
        {
            apiController.OnMoveToPositionClicked();
        }
    }

    private void UpdateUI(Vector3 worldPos)
    {
        if (apiController == null || robotBase == null) return;

        Vector3 localPos = robotBase.InverseTransformPoint(worldPos);
        float x_mm = localPos.x * unityToMmScale;
        float y_mm = localPos.y * unityToMmScale;
        float z_mm = localPos.z * unityToMmScale;

        if (apiController.inputX) apiController.inputX.text = x_mm.ToString("F0");
        if (apiController.inputY) apiController.inputY.text = y_mm.ToString("F0");
        if (apiController.inputZ) apiController.inputZ.text = z_mm.ToString("F0");
    }
}