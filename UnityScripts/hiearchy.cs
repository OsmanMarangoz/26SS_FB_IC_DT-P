#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

public sealed class RobotArmHierarchyCopyTool : EditorWindow
{
    private string robotArmName = "Roboterarm";
    private Transform destinationParent;
    private bool appendCopySuffix = true;
    private GameObject foundRobotArm;

    [MenuItem("Window/Robot Arm/Hierarchy Copy Tool")]
    private static void Open()
    {
        GetWindow<RobotArmHierarchyCopyTool>("Robot Arm Copy");
    }

    private void OnGUI()
    {
        EditorGUILayout.LabelField("Robot-Arm-Hierarchie", EditorStyles.boldLabel);
        EditorGUILayout.HelpBox(
            "Dupliziert das gefundene GameObject mit allen Kindern und allen " +
            "serialisierten Inspector-Werten. Komponenten und interne Referenzen " +
            "werden dabei ebenfalls dupliziert. Nicht serialisierte Laufzeitwerte " +
            "werden nicht kopiert.",
            MessageType.Info);

        robotArmName = EditorGUILayout.TextField("Root-Name", robotArmName);
        destinationParent = (Transform)EditorGUILayout.ObjectField(
            "Ziel-Parent",
            destinationParent,
            typeof(Transform),
            true);
        appendCopySuffix = EditorGUILayout.ToggleLeft(
            "Name mit _Copy ergänzen",
            appendCopySuffix);

        EditorGUILayout.Space(8);

        if (GUILayout.Button("Roboterarm in Hierarchy suchen"))
        {
            foundRobotArm = FindInActiveScene(robotArmName);
            SelectFoundObject();
        }

        using (new EditorGUI.DisabledScope(foundRobotArm == null))
        {
            EditorGUILayout.ObjectField("Gefunden", foundRobotArm, typeof(GameObject), true);

            if (GUILayout.Button("Komplette Hierarchie kopieren"))
            {
                CopyHierarchy();
            }

            if (GUILayout.Button("Inspector-Report in Zwischenablage kopieren"))
            {
                CopyInspectorReport();
            }
        }

        if (Selection.activeGameObject != null &&
            GUILayout.Button("Ausgewähltes GameObject als Root verwenden"))
        {
            foundRobotArm = Selection.activeGameObject;
            robotArmName = foundRobotArm.name;
        }
    }

    private void SelectFoundObject()
    {
        if (foundRobotArm == null)
        {
            Debug.LogWarning("RobotArm wurde in der aktiven Scene nicht gefunden: " + robotArmName);
            return;
        }

        Selection.activeGameObject = foundRobotArm;
        EditorGUIUtility.PingObject(foundRobotArm);
    }

    private void CopyHierarchy()
    {
        if (foundRobotArm == null)
        {
            return;
        }

        GameObject copy = Instantiate(foundRobotArm, destinationParent);
        copy.name = appendCopySuffix ? foundRobotArm.name + "_Copy" : foundRobotArm.name;
        Undo.RegisterCreatedObjectUndo(copy, "Copy RobotArm hierarchy");
        EditorSceneManager.MarkSceneDirty(copy.scene);

        Selection.activeGameObject = copy;
        EditorGUIUtility.PingObject(copy);
        Debug.Log("RobotArm-Hierarchie kopiert: " + GetHierarchyPath(copy.transform));
    }

    private void CopyInspectorReport()
    {
        if (foundRobotArm == null)
        {
            return;
        }

        StringBuilder report = new StringBuilder();
        report.AppendLine("RobotArm Inspector Report");
        report.AppendLine("Scene: " + foundRobotArm.scene.name);
        report.AppendLine();
        AppendGameObjectReport(foundRobotArm.transform, report);

        GUIUtility.systemCopyBuffer = report.ToString();
        Debug.Log("Inspector-Report wurde in die Zwischenablage kopiert.");
    }

    private static void AppendGameObjectReport(Transform current, StringBuilder report)
    {
        report.AppendLine("GameObject: " + GetHierarchyPath(current));
        report.AppendLine("  Active: " + current.gameObject.activeSelf);

        Component[] components = current.GetComponents<Component>();
        foreach (Component component in components)
        {
            if (component == null)
            {
                report.AppendLine("  Component: <Missing Script>");
                continue;
            }

            report.AppendLine("  Component: " + component.GetType().FullName);
            SerializedObject serializedObject = new SerializedObject(component);
            SerializedProperty property = serializedObject.GetIterator();
            bool enterChildren = true;

            while (property.NextVisible(enterChildren))
            {
                if (property.name == "m_Script")
                {
                    enterChildren = false;
                    continue;
                }

                report.AppendLine("    " + property.propertyPath + " = " +
                                 SerializedPropertyValue(property));
                enterChildren = false;
            }
        }

        for (int index = 0; index < current.childCount; index++)
        {
            AppendGameObjectReport(current.GetChild(index), report);
        }
    }

    private static string SerializedPropertyValue(SerializedProperty property)
    {
        switch (property.propertyType)
        {
            case SerializedPropertyType.Boolean:
                return property.boolValue.ToString();
            case SerializedPropertyType.Integer:
                return property.longValue.ToString();
            case SerializedPropertyType.Float:
                return property.doubleValue.ToString("R");
            case SerializedPropertyType.String:
                return property.stringValue;
            case SerializedPropertyType.ObjectReference:
                return property.objectReferenceValue == null
                    ? "null"
                    : property.objectReferenceValue.name;
            case SerializedPropertyType.Enum:
                return property.enumDisplayNames[property.enumValueIndex];
            case SerializedPropertyType.Vector2:
                return property.vector2Value.ToString();
            case SerializedPropertyType.Vector3:
                return property.vector3Value.ToString();
            case SerializedPropertyType.Vector4:
                return property.vector4Value.ToString();
            case SerializedPropertyType.Quaternion:
                return property.quaternionValue.eulerAngles.ToString();
            default:
                return property.ToString();
        }
    }

    private static GameObject FindInActiveScene(string objectName)
    {
        if (string.IsNullOrWhiteSpace(objectName))
        {
            return null;
        }

        Scene activeScene = SceneManager.GetActiveScene();
        foreach (GameObject root in activeScene.GetRootGameObjects())
        {
            Transform match = FindRecursive(root.transform, objectName);
            if (match != null)
            {
                return match.gameObject;
            }
        }

        return null;
    }

    private static Transform FindRecursive(Transform current, string objectName)
    {
        if (current.name.Equals(objectName, StringComparison.OrdinalIgnoreCase))
        {
            return current;
        }

        foreach (Transform child in current)
        {
            Transform match = FindRecursive(child, objectName);
            if (match != null)
            {
                return match;
            }
        }

        return null;
    }

    private static string GetHierarchyPath(Transform current)
    {
        List<string> names = new List<string>();
        Transform cursor = current;
        while (cursor != null)
        {
            names.Add(cursor.name);
            cursor = cursor.parent;
        }

        names.Reverse();
        return string.Join("/", names);
    }

}
#endif
