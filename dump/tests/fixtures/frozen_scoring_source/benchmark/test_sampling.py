import numpy as np

from benchmark.sampling import sample_nested_roles, role_manifest


def test_nested_roles_are_exact_disjoint_and_repeatable():
    y = np.repeat(np.arange(7), [500, 300, 200, 150, 100, 80, 70])
    ids = np.arange(len(y))
    first = sample_nested_roles(y, [100, 300, 1_000], 42, ids)
    again = sample_nested_roles(y, [100, 300, 1_000], 42, ids)
    for budget, role in first.items():
        assert (len(role.fit), len(role.tune), len(role.calibration)) == (
            int(.8 * budget), int(.1 * budget), budget - int(.8 * budget) - int(.1 * budget))
        all_ids = np.concatenate((role.fit, role.tune, role.calibration))
        assert len(np.unique(all_ids)) == budget
        assert np.array_equal(role.fit, again[budget].fit)
        assert np.array_equal(role.tune, again[budget].tune)
        assert np.array_equal(role.calibration, again[budget].calibration)
    small, large = first[100], first[300]
    assert set(small.fit).issubset(large.fit)
    assert set(small.tune).issubset(large.tune)
    assert set(small.calibration).issubset(large.calibration)


def test_role_manifest_contains_counts_and_digests():
    y = np.tile(np.arange(7), 30)
    role = sample_nested_roles(y, [70], 7)[70]
    manifest = role_manifest(role, y)
    assert manifest["status"] == "ok"
    assert sum(manifest["roles"]["fit"]["counts"]) == 56
    assert len(manifest["roles"]["fit"]["ids_sha256"]) == 64


def test_budget_over_pool_is_explicitly_capped():
    y = np.tile(np.arange(7), 10)
    role = sample_nested_roles(y, [500], 3)[500]
    assert role.budget == len(y)
    assert role.status == f"capped_to_available_{len(y)}"
