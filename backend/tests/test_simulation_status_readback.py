import json

import pytest

from app import create_app
from app.api import simulation as simulation_api
from app.config import Config
from app.services.simulation_manager import SimulationManager, SimulationState, SimulationStatus
from app.services.simulation_runner import RunnerStatus, SimulationRunner, SimulationRunState


@pytest.fixture
def simulation_client(tmp_path, monkeypatch):
    simulations_dir = tmp_path / 'simulations'
    monkeypatch.setattr(Config, 'AUTH_ENABLED', False)
    monkeypatch.setattr(SimulationManager, 'SIMULATION_DATA_DIR', str(simulations_dir))
    monkeypatch.setattr(SimulationRunner, 'RUN_STATE_DIR', str(simulations_dir))
    monkeypatch.setattr(SimulationRunner, '_run_states', {})
    monkeypatch.setattr(simulation_api.ProjectManager, 'get_project', lambda _: None)
    monkeypatch.setattr(simulation_api, '_get_report_id_for_simulation', lambda _: None)
    manager = SimulationManager()
    state = SimulationState('sim_status_test', 'proj_status_test', 'graph_status_test', status=SimulationStatus.RUNNING)
    manager._save_simulation_state(state)
    client = create_app().test_client()
    return client, simulations_dir / state.simulation_id, manager, state


@pytest.mark.parametrize('endpoint', ['/api/simulation/sim_status_test', '/api/simulation/list', '/api/simulation/history'])
@pytest.mark.parametrize('runner_status', [RunnerStatus.COMPLETED, RunnerStatus.STOPPED, RunnerStatus.FAILED, RunnerStatus.PAUSED])
def test_read_routes_use_actual_runner_status_without_rewriting_saved_inputs(simulation_client, endpoint, runner_status):
    client, folder, _, _ = simulation_client
    SimulationRunner._save_run_state(SimulationRunState(
        simulation_id='sim_status_test', runner_status=runner_status,
        current_round=4, total_rounds=4, error='Lauf fehlgeschlagen' if runner_status == RunnerStatus.FAILED else None,
    ))
    before = {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}
    response = client.get(endpoint)
    assert response.status_code == 200
    data = response.get_json()['data']
    item = data[0] if isinstance(data, list) else data
    assert item['status'] == runner_status.value
    assert item['runner_status'] == runner_status.value
    assert item['current_round'] == 4
    if runner_status == RunnerStatus.FAILED:
        assert item['error'] == 'Lauf fehlgeschlagen'
    assert {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()} == before


@pytest.mark.parametrize('runner_status', [None, RunnerStatus.IDLE])
def test_ready_simulation_is_not_misreported_as_running_or_completed(simulation_client, runner_status):
    client, folder, manager, state = simulation_client
    state.status = SimulationStatus.READY
    manager._save_simulation_state(state)
    if runner_status is not None:
        SimulationRunner._save_run_state(SimulationRunState(simulation_id=state.simulation_id, runner_status=runner_status))
    response = client.get('/api/simulation/' + state.simulation_id)
    assert response.status_code == 200
    assert response.get_json()['data']['status'] == 'ready'
    assert 'run_instructions' in response.get_json()['data']
    assert json.loads((folder / 'state.json').read_text())['status'] == 'ready'


@pytest.mark.parametrize('endpoint', ['/api/simulation/sim_status_test', '/api/simulation/list', '/api/simulation/history'])
@pytest.mark.parametrize('metadata_status', [SimulationStatus.CREATED, SimulationStatus.PREPARING, SimulationStatus.READY, SimulationStatus.FAILED])
@pytest.mark.parametrize('old_runner_status', [RunnerStatus.COMPLETED, RunnerStatus.FAILED])
def test_previous_runner_does_not_override_a_new_preparation(simulation_client, endpoint, metadata_status, old_runner_status):
    client, folder, manager, state = simulation_client
    state.status = metadata_status
    state.error = 'Vorbereitung fehlgeschlagen' if metadata_status == SimulationStatus.FAILED else None
    manager._save_simulation_state(state)
    SimulationRunner._save_run_state(SimulationRunState(
        simulation_id=state.simulation_id, runner_status=old_runner_status,
        current_round=4, total_rounds=4, error='Alter Lauf fehlgeschlagen',
    ))
    before = {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}
    response = client.get(endpoint)
    assert response.status_code == 200
    data = response.get_json()['data']
    item = data[0] if isinstance(data, list) else data
    assert item['status'] == metadata_status.value
    assert item['error'] == state.error
    assert {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()} == before
