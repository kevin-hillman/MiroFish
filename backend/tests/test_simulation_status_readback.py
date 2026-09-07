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
@pytest.mark.parametrize('old_runner_status', [RunnerStatus.COMPLETED, RunnerStatus.FAILED, RunnerStatus.STOPPED])
def test_previous_runner_does_not_override_a_new_preparation(simulation_client, endpoint, metadata_status, old_runner_status):
    client, folder, manager, state = simulation_client
    state.status = metadata_status
    state.error = 'Vorbereitung fehlgeschlagen' if metadata_status == SimulationStatus.FAILED else None
    manager._save_simulation_state(state)
    SimulationRunner._save_run_state(SimulationRunState(
        simulation_id=state.simulation_id, runner_status=old_runner_status,
        current_round=4, total_rounds=4, error='Alter Lauf fehlgeschlagen',
        twitter_completed=True, reddit_completed=True, twitter_current_round=4, reddit_current_round=4,
    ))
    before = {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}
    response = client.get(endpoint)
    assert response.status_code == 200
    data = response.get_json()['data']
    item = data[0] if isinstance(data, list) else data
    assert item['status'] == metadata_status.value
    assert item['error'] == state.error
    assert {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()} == before


@pytest.mark.parametrize('endpoint', ['/api/simulation/sim_status_test', '/api/simulation/list', '/api/simulation/history'])
@pytest.mark.parametrize('twitter_enabled,reddit_enabled,twitter_done,reddit_done,expected', [
    (False, True, False, True, 'completed'),
    (True, False, True, False, 'completed'),
    (True, True, True, True, 'completed'),
    (True, True, False, True, 'stopped'),
    (False, True, False, False, 'stopped'),
    (False, False, True, True, 'stopped'),
    (True, False, False, True, 'stopped'),
])
def test_finished_rounds_remain_completed_after_interaction_process_shutdown(
    simulation_client, endpoint, twitter_enabled, reddit_enabled, twitter_done, reddit_done, expected,
):
    client, folder, manager, state = simulation_client
    state.status = SimulationStatus.STOPPED
    state.enable_twitter = twitter_enabled
    state.enable_reddit = reddit_enabled
    manager._save_simulation_state(state)
    shutdown_reason = 'Server heruntergefahren, Simulation wurde beendet'
    SimulationRunner._save_run_state(SimulationRunState(
        simulation_id=state.simulation_id, runner_status=RunnerStatus.STOPPED,
        current_round=4, total_rounds=4, twitter_completed=twitter_done, reddit_completed=reddit_done,
        twitter_current_round=4, reddit_current_round=4,
        error=shutdown_reason,
    ))
    before = {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}
    response = client.get(endpoint)
    assert response.status_code == 200
    data = response.get_json()['data']
    item = data[0] if isinstance(data, list) else data
    assert item['status'] == expected
    assert item['runner_status'] == 'stopped'
    if expected == 'completed':
        assert item['error'] is None
        assert item['runner_error'] == shutdown_reason
    else:
        assert item['error'] == shutdown_reason
    assert {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()} == before


@pytest.mark.parametrize('endpoint', ['/api/simulation/sim_status_test', '/api/simulation/list', '/api/simulation/history'])
@pytest.mark.parametrize('twitter_round,reddit_round,total_rounds', [(4, 3, 4), (3, 4, 4), (0, 0, 4), (4, 4, 0)])
def test_shutdown_completion_events_do_not_prove_all_rounds_finished(
    simulation_client, endpoint, twitter_round, reddit_round, total_rounds,
):
    client, folder, manager, state = simulation_client
    state.status = SimulationStatus.STOPPED
    state.enable_twitter = True
    state.enable_reddit = True
    manager._save_simulation_state(state)
    SimulationRunner._save_run_state(SimulationRunState(
        simulation_id=state.simulation_id, runner_status=RunnerStatus.STOPPED,
        current_round=4, total_rounds=total_rounds, twitter_completed=True, reddit_completed=True,
        twitter_current_round=twitter_round, reddit_current_round=reddit_round, error='Lauf vorzeitig beendet',
    ))
    before = {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}
    response = client.get(endpoint)
    assert response.status_code == 200
    data = response.get_json()['data']
    item = data[0] if isinstance(data, list) else data
    assert item['status'] == 'stopped'
    assert item['runner_status'] == 'stopped'
    assert item['error'] == 'Lauf vorzeitig beendet'
    assert {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()} == before


@pytest.mark.parametrize('endpoint', ['/api/simulation/sim_status_test', '/api/simulation/list', '/api/simulation/history'])
def test_failed_runner_is_not_hidden_by_completed_rounds(simulation_client, endpoint):
    client, _, _, state = simulation_client
    SimulationRunner._save_run_state(SimulationRunState(
        simulation_id=state.simulation_id, runner_status=RunnerStatus.FAILED,
        current_round=4, total_rounds=4, twitter_completed=True, reddit_completed=True,
        twitter_current_round=4, reddit_current_round=4, error='Lauf fehlgeschlagen',
    ))
    response = client.get(endpoint)
    assert response.status_code == 200
    data = response.get_json()['data']
    item = data[0] if isinstance(data, list) else data
    assert item['status'] == 'failed'
    assert item['runner_status'] == 'failed'
    assert item['error'] == 'Lauf fehlgeschlagen'
