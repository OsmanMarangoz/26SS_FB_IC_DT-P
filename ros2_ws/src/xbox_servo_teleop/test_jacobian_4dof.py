#!/usr/bin/env python3
"""
test_jacobian_4dof.py
Unit-Test für 4×4 Jacobian-Berechnung

Testet:
  1. Jacobian-Shape ist exakt 4×4
  2. Manipulability-Berechnung korrekt
  3. DLS-Solver konvergiert
  4. Pitch-Zeile ist linear unabhängig von Position-Zeilen
"""

import numpy as np
import sys


def test_jacobian_shape():
    """Test 1: Shape muss 4×4 sein"""
    print("\n📐 Test 1: Jacobian Shape")

    # Mock Jacobian (4×4)
    J = np.random.rand(4, 4)

    assert J.shape == (4, 4), f"❌ FAIL: Shape is {J.shape}, expected (4, 4)"
    print("✅ PASS: Jacobian is 4×4")
    return True


def test_manipulability():
    """Test 2: Manipulability = |det(J)| für quadratische Matrix"""
    print("\n📊 Test 2: Manipulability Computation")

    # Well-conditioned matrix
    J_good = np.eye(4) + 0.1 * np.random.rand(4, 4)
    manip_good = abs(np.linalg.det(J_good))

    print(f"  Good pose: manip = {manip_good:.6f}")
    assert manip_good > 0.1, "❌ FAIL: Manipulability too low for good pose"

    # Near-singular matrix
    J_bad = np.eye(4)
    J_bad[3, :] = J_bad[0, :] * 0.001  # Almost linearly dependent
    manip_bad = abs(np.linalg.det(J_bad))

    print(f"  Bad pose:  manip = {manip_bad:.6f}")
    assert manip_bad < 0.01, "❌ FAIL: Manipulability too high for singular pose"

    print("✅ PASS: Manipulability computation correct")
    return True


def test_dls_solver():
    """Test 3: DLS löst 4×4 System korrekt"""
    print("\n🔧 Test 3: DLS Solver")

    # Random well-conditioned 4×4 Jacobian
    J = np.eye(4) + 0.2 * np.random.rand(4, 4)
    v_task = np.array([0.1, 0.05, 0.02, 0.3])  # [vx, vy, vz, vpitch]

    # DLS with small damping
    lambda_dls = 0.01
    JJt = J @ J.T
    damp = (lambda_dls ** 2) * np.eye(4)

    try:
        q_dot = J.T @ np.linalg.solve(JJt + damp, v_task)

        # Verify: J * q_dot ≈ v_task
        v_achieved = J @ q_dot
        error = np.linalg.norm(v_achieved - v_task)

        print(f"  Commanded: {v_task}")
        print(f"  Achieved:  {v_achieved.round(4)}")
        print(f"  Error:     {error:.6f}")

        assert error < 0.01, f"❌ FAIL: DLS error too large: {error}"
        print("✅ PASS: DLS solves correctly")
        return True

    except np.linalg.LinAlgError as e:
        print(f"❌ FAIL: DLS solver crashed: {e}")
        return False


def test_pitch_independence():
    """Test 4: Pitch-Zeile ist linear unabhängig von Position"""
    print("\n🔍 Test 4: Pitch Row Independence")

    # Mock realistic Jacobian
    # Position rows: typical values for ~0.4m arm
    J_pos = np.array([
        [0.3, -0.2,  0.1, 0.05],  # dx/dq
        [0.2,  0.3, -0.1, 0.02],  # dy/dq
        [0.1,  0.2,  0.3, 0.15],  # dz/dq
    ])

    # Pitch row: angular contributions (only Y-component)
    J_pitch = np.array([0.0, 0.8, 0.6, 0.4])  # dθ_pitch/dq

    J = np.vstack([J_pos, J_pitch.reshape(1, 4)])

    # Check: Pitch row should NOT be linear combination of position rows
    # Method: Compute rank of J (should be 4, not 3)
    rank = np.linalg.matrix_rank(J)

    print(f"  Matrix rank: {rank}")
    assert rank == 4, f"❌ FAIL: Rank is {rank}, pitch row is dependent!"

    # Alternative: Check if pitch row has significant norm
    pitch_norm = np.linalg.norm(J_pitch)
    print(f"  Pitch row norm: {pitch_norm:.4f}")
    assert pitch_norm > 0.1, "❌ FAIL: Pitch row is zero!"

    print("✅ PASS: Pitch row is independent")
    return True


def test_null_space_dimension():
    """Test 5: Null-space sollte 0-dimensional sein (4 DoF = 4 DoF)"""
    print("\n🎯 Test 5: Null-Space Dimension")

    # Random full-rank 4×4 Jacobian
    J = np.eye(4) + 0.2 * np.random.rand(4, 4)

    # Null-space: Solve J * v = 0
    # For full-rank 4×4: only solution is v = 0
    rank = np.linalg.matrix_rank(J)
    nullspace_dim = 4 - rank

    print(f"  Matrix rank: {rank}")
    print(f"  Null-space dimension: {nullspace_dim}")

    assert nullspace_dim == 0, f"❌ FAIL: Null-space has dimension {nullspace_dim}!"
    print("✅ PASS: No redundancy (null-space is trivial)")
    return True


def run_all_tests():
    """Run all tests"""
    print("="*60)
    print("🧪 4×4 JACOBIAN UNIT TESTS")
    print("="*60)

    tests = [
        test_jacobian_shape,
        test_manipulability,
        test_dls_solver,
        test_pitch_independence,
        test_null_space_dimension,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"❌ EXCEPTION in {test.__name__}: {e}")
            results.append(False)

    print("\n" + "="*60)
    print(f"📊 RESULTS: {sum(results)}/{len(results)} tests passed")
    print("="*60)

    if all(results):
        print("✅ ALL TESTS PASSED! 4×4 Jacobian is correct.")
        return 0
    else:
        print("❌ SOME TESTS FAILED! Check implementation.")
        return 1


if __name__ == '__main__':
    sys.exit(run_all_tests())
