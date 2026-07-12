from league_of_idea import dedup


def test_similarity_detects_punctuation_and_case_variants():
    first = "Deploy Solar-Powered Pumps in Flood Zones."
    second = "deploy solar powered pumps in flood zones"

    assert dedup.similarity(first, second) > 0.9
    assert dedup.is_near_duplicate(second, [first])


def test_similarity_keeps_distinct_ideas():
    assert dedup.similarity(
        "Deploy solar pumps in flood zones.",
        "Create wetland parks to absorb storm water.",
    ) < 0.5
