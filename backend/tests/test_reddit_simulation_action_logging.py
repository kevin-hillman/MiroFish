import json
import sqlite3
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BACKEND_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import run_reddit_simulation as reddit_simulation
from app.services.simulation_runner import (
    RunnerStatus,
    SimulationRunner,
    SimulationRunState,
)


class FakeAgentGraph:
    def __init__(self):
        self.agent = object()

    def get_agent(self, agent_id):
        assert agent_id == 0
        return self.agent


class FakeRedditEnvironment:
    def __init__(self, database_path, agent_graph):
        self.database_path = database_path
        self.agent_graph = agent_graph

        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                CREATE TABLE trace (
                    user_id INTEGER,
                    action TEXT,
                    info TEXT,
                    created_at TEXT
                )
                """
            )

    async def reset(self):
        pass

    async def step(self, actions):
        assert actions
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO trace (user_id, action, info, created_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (0, "create_post", json.dumps({"content": "Testbeitrag"})),
            )

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_standalone_reddit_runner_reports_rounds_actions_and_completion(
    tmp_path,
    monkeypatch,
):
    simulations_dir = tmp_path / "simulations"
    simulation_dir = simulations_dir / "sim_test"
    simulation_dir.mkdir(parents=True)

    config_path = simulation_dir / "simulation_config.json"
    config_path.write_text(
        json.dumps(
            {
                "simulation_id": "sim_test",
                "time_config": {
                    "total_simulation_hours": 2,
                    "minutes_per_round": 60,
                },
                "agent_configs": [
                    {"agent_id": 0, "entity_name": "Haendler"},
                ],
                "event_config": {"initial_posts": []},
            }
        ),
        encoding="utf-8",
    )
    (simulation_dir / "reddit_profiles.json").write_text("[]", encoding="utf-8")

    agent_graph = FakeAgentGraph()

    async def fake_generate_agent_graph(**kwargs):
        return agent_graph

    monkeypatch.setattr(
        reddit_simulation,
        "generate_reddit_agent_graph",
        fake_generate_agent_graph,
    )
    monkeypatch.setattr(
        reddit_simulation.oasis,
        "make",
        lambda **kwargs: FakeRedditEnvironment(
            kwargs["database_path"],
            kwargs["agent_graph"],
        ),
    )

    runner = reddit_simulation.RedditSimulationRunner(
        str(config_path),
        wait_for_commands=False,
    )
    monkeypatch.setattr(runner, "_create_model", lambda: object())
    monkeypatch.setattr(
        runner,
        "_get_active_agents_for_round",
        lambda env, current_hour, round_num: [(0, agent_graph.agent)],
    )

    await runner.run(max_rounds=2)

    action_log = simulation_dir / "reddit" / "actions.jsonl"
    assert action_log.exists()

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(simulations_dir))
    state = SimulationRunState(
        simulation_id="sim_test",
        total_rounds=2,
        reddit_running=True,
    )

    position = SimulationRunner._read_action_log(
        str(action_log),
        0,
        state,
        "reddit",
    )

    assert position == action_log.stat().st_size
    assert state.current_round == 2
    assert state.reddit_current_round == 2
    assert state.reddit_actions_count == 2
    assert state.reddit_completed is True
    assert state.runner_status == RunnerStatus.COMPLETED
