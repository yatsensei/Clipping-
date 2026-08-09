"""API contract tests.

The two that matter most are the shared distance index — the frontend overlays traces
without re-interpolating, so a mismatch would silently misalign every chart — and the
provenance labelling, which is what keeps a modelled number from being read as a measured
one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import store
from api.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def circuit_id() -> str:
    resp = client.get("/circuits")
    assert resp.status_code == 200, resp.text
    circuits = [c for c in resp.json() if c["has_strategy"]]
    if not circuits:
        pytest.skip("no solved circuits available")
    return circuits[0]["circuit_id"]


def test_health_reports_circuit_count():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["circuits"] > 0


def test_circuit_list_is_in_calendar_order():
    r = client.get("/circuits")
    assert r.status_code == 200
    rounds = [c["round_number"] for c in r.json()]
    assert rounds == sorted(rounds)


def test_circuit_list_carries_the_metadata_the_brief_asks_for():
    c = client.get("/circuits").json()[0]
    for field in ("event_name", "country", "lap_distance_m", "corner_count",
                  "round_number"):
        assert field in c, field


def test_circuit_detail_returns_structured_provenance(circuit_id):
    """This endpoint had no test and raised on every request.

    CircuitDetail inherits a one-line `provenance` string from CircuitListItem and
    overrides it with the structured object, so spreading the summary unchanged passed
    the argument twice. Nothing caught it until the static export tried to snapshot it.
    """
    r = client.get(f"/circuits/{circuit_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["provenance"], dict)
    assert body["provenance"]["session"]
    assert body["circuit_id"] == circuit_id
    assert isinstance(body["segments"], list) and body["segments"]
    assert isinstance(body["official_corners"], list)


def test_unknown_circuit_is_a_404_not_a_crash():
    r = client.get("/circuits/nurburgring")
    assert r.status_code == 404
    assert "unknown circuit" in r.json()["detail"]


def test_unknown_strategy_mode_is_rejected(circuit_id):
    r = client.get(f"/circuits/{circuit_id}/strategy", params={"mode": "telepathy"})
    assert r.status_code == 422
    assert "unknown mode" in r.json()["detail"]


# -- the shared distance index -------------------------------------------------------


def test_geometry_and_every_strategy_share_one_distance_index(circuit_id):
    geo = client.get(f"/circuits/{circuit_id}/geometry").json()
    reference = geo["distance_m"]
    assert len(reference) > 100

    for mode in ("optimal", "naive", "greedy"):
        s = client.get(f"/circuits/{circuit_id}/strategy",
                       params={"mode": mode}).json()
        assert s["distance_m"] == reference, f"{mode} is on a different grid"
        for series in ("speed_kph", "deploy_kw", "harvest_kw", "soc_mj", "clipping"):
            assert len(s[series]) == len(reference), f"{mode}/{series} length mismatch"


def test_geometry_arrays_all_match_the_index_length(circuit_id):
    geo = client.get(f"/circuits/{circuit_id}/geometry").json()
    n = len(geo["distance_m"])
    for name in ("x_m", "y_m", "z_m", "curvature_1_per_m", "gradient"):
        assert len(geo[name]) == n, name


def test_naive_is_an_alias_for_uniform(circuit_id):
    naive = client.get(f"/circuits/{circuit_id}/strategy",
                       params={"mode": "naive"}).json()
    uniform = client.get(f"/circuits/{circuit_id}/strategy",
                         params={"mode": "uniform"}).json()
    assert naive["mode"] == "uniform"
    assert naive["requested_mode"] == "naive"
    assert naive["lap_time_s"] == uniform["lap_time_s"]


# -- provenance and labelling --------------------------------------------------------


def test_every_payload_states_whether_it_is_measured_or_modelled(circuit_id):
    geo = client.get(f"/circuits/{circuit_id}/geometry").json()
    assert geo["data_type"] == "measured_gps_derived"

    for endpoint in (f"/circuits/{circuit_id}/strategy",
                     f"/circuits/{circuit_id}/comparison"):
        payload = client.get(endpoint).json()
        assert payload["data_type"] == "model_output", endpoint
        assert "no energy channels" in payload["provenance"]["note"]


def test_provenance_names_the_session_and_driver(circuit_id):
    p = client.get(f"/circuits/{circuit_id}/strategy").json()["provenance"]
    assert p["session"]
    assert p["reference_driver"]
    assert p["reference_lap_time_s"] > 0
    assert isinstance(p["is_fallback"], bool)


def test_fallback_circuits_explain_themselves():
    circuits = client.get("/circuits").json()
    fallback = [c for c in circuits if c["is_fallback"] and c["has_strategy"]]
    if not fallback:
        pytest.skip("no fallback circuits solved")
    p = client.get(f"/circuits/{fallback[0]['circuit_id']}/strategy").json()["provenance"]
    assert p["fallback_note"], "a fallback circuit must say its geometry is borrowed"
    assert "speed trace is never used" in p["fallback_note"]


# -- comparison ----------------------------------------------------------------------


def test_comparison_names_its_baseline(circuit_id):
    c = client.get(f"/circuits/{circuit_id}/comparison").json()
    assert c["baseline"] == "uniform"
    assert "uniform" in c["baseline_statement"].lower()
    assert c["gain_vs_uniform_s"] != 0.0


def test_comparison_flags_greedy_as_unrepeatable(circuit_id):
    c = client.get(f"/circuits/{circuit_id}/comparison").json()
    greedy = next(s for s in c["strategies"] if s["mode"] == "greedy")
    optimal = next(s for s in c["strategies"] if s["mode"] == "optimal")
    assert not greedy["repeatable"]
    assert optimal["repeatable"]
    assert c["greedy_energy_debt_mj"] > 0
    assert "cannot be run again" in c["greedy_caveat"]


def test_optimal_beats_uniform_and_the_gain_matches_the_lap_times(circuit_id):
    c = client.get(f"/circuits/{circuit_id}/comparison").json()
    times = {s["mode"]: s["lap_time_s"] for s in c["strategies"]}
    assert times["optimal"] < times["uniform"]
    assert c["gain_vs_uniform_s"] == pytest.approx(
        times["uniform"] - times["optimal"], abs=0.01
    )


def test_strategy_marks_greedy_as_not_repeatable(circuit_id):
    g = client.get(f"/circuits/{circuit_id}/strategy",
                   params={"mode": "greedy"}).json()
    assert not g["repeatable"]
    assert g["repeatability_note"] and "cannot be repeated" in g["repeatability_note"]


# -- meta ----------------------------------------------------------------------------


def test_meta_separates_fitted_parameters_from_assumed_ones():
    m = client.get("/meta").json()
    assert m["vehicle"]["fitted"]["cd_a_m2"] > 0
    # P_ice could not be identified from telemetry, so it must appear as assumed.
    assert "p_ice_w" in m["vehicle"]["assumed"]
    assert m["vehicle"]["assumptions"]
    assert m["regulations"]["harvest_cap_mj"] == pytest.approx(7.0)
    assert "SECONDARY" in m["regulations"]["harvest_cap_basis"]


def test_meta_reports_how_far_the_model_sits_from_reality():
    m = client.get("/meta").json()
    acc = m["simulation_accuracy"]
    if acc is None:
        pytest.skip("simulation accuracy not computed")
    assert acc["mean_abs_lap_error_s"] > 0
    assert acc["circuits"] > 0


def test_store_rejects_an_unknown_mode_directly():
    with pytest.raises(KeyError):
        store.resolve_mode("wishful")
