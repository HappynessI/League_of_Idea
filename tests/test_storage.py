from league_of_idea.models import Session
from league_of_idea.storage import load_session, save_session


def test_session_round_trip(tmp_path):
    session = Session(
        goal="test goal",
        num_ideas=2,
        rounds=1,
        judge_model="openai:judge",
        generator_model="openai:generator",
    )
    path = save_session(session, tmp_path)

    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()
    loaded = load_session(session.id, tmp_path)
    assert loaded.id == session.id
    assert loaded.goal == "test goal"
