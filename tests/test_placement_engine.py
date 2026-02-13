from ibp.placement.engine import decision_as_jsonable, place_chunk


def test_place_chunk_assigns_high_confidence_topic():
    decision = place_chunk(
        chunk_heading="باب النحو",
        chunk_body="هذا باب في قواعد النحو والإعراب",
        topics=[
            {
                "topic_id": "topic_nahw",
                "title": "النحو",
                "aliases": ["الإعراب"],
                "exemplars": [{"heading": "النحو", "body": "قواعد الإعراب"}],
            },
            {
                "topic_id": "topic_fiqh",
                "title": "الفقه",
                "exemplars": [{"heading": "الفقه", "body": "أحكام الطهارة"}],
            },
        ],
        min_confidence=0.3,
    )

    assert decision.status == "assigned"
    assert decision.chosen_topic_id == "topic_nahw"
    jsonable = decision_as_jsonable(decision)
    assert jsonable["candidate_alternatives"][0]["topic_id"] == "topic_nahw"
    assert "evidence" in jsonable["candidate_alternatives"][0]


def test_place_chunk_routes_low_confidence_to_review_with_evidence():
    decision = place_chunk(
        chunk_heading="عنوان بعيد",
        chunk_body="محتوى غير مطابق",
        topics=[
            {
                "topic_id": "topic_logic",
                "title": "علم المنطق",
                "exemplars": [{"heading": "القياس", "body": "البرهان والحد"}],
            }
        ],
        min_confidence=0.7,
    )

    assert decision.status == "review"
    assert decision.chosen_topic_id is None
    assert "confidence_below_threshold" in decision.reasons

    jsonable = decision_as_jsonable(decision)
    assert jsonable["candidate_alternatives"][0]["topic_id"] == "topic_logic"
    assert jsonable["candidate_alternatives"][0]["evidence"]


def test_place_chunk_ambiguity_triggers_review():
    decision = place_chunk(
        chunk_heading="الأصول",
        chunk_body="أدلة وقواعد",
        topics=[
            {
                "topic_id": "topic_a",
                "title": "أصول",
                "exemplars": [{"heading": "أصول", "body": "أدلة"}],
            },
            {
                "topic_id": "topic_b",
                "title": "أصول",
                "exemplars": [{"heading": "أصول", "body": "قواعد"}],
            },
        ],
        min_confidence=0.1,
        ambiguity_margin=0.2,
    )

    assert decision.status == "review"
    assert "ambiguous_top_candidates" in decision.reasons
