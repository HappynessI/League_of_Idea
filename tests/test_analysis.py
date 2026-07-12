from league_of_idea.analysis import creator_attribution
from league_of_idea.models import Idea, Session


def test_creator_attribution_groups_and_sorts_models():
    session = Session(
        goal="goal", num_ideas=3, rounds=1,
        judge_model="openai:judge", generator_model="openai:a",
        ideas=[
            Idea(content="a1", created_by="openai:a", elo=1300, wins=2),
            Idea(content="a2", created_by="openai:a", elo=1100, losses=1),
            Idea(content="b1", created_by="anthropic:b", elo=1250, draws=1),
        ],
    )
    rows = creator_attribution(session)
    assert [row.model for row in rows] == ["anthropic:b", "openai:a"]
    assert rows[1].ideas == 2
    assert rows[1].average_elo == 1200
    assert (rows[1].wins, rows[1].losses) == (2, 1)
