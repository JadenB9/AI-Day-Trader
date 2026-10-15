from src.ai.prompt_templates import parse_ai_response


def test_parses_a_well_formed_answer():
    text = "DECISION: APPROVE\nCONFIDENCE: 82%\nREASONING: Strong volume on the breakout."
    out = parse_ai_response(text)
    assert out["decision"] == "APPROVE"
    assert out["confidence"] == 82
    assert out["reasoning"] == "Strong volume on the breakout."
    assert out["raw_response"] == text


def test_unknown_decision_defaults_to_reject():
    out = parse_ai_response("DECISION: MAYBE\nCONFIDENCE: 50\nREASONING: unsure")
    assert out["decision"] == "REJECT"


def test_garbage_confidence_is_zero():
    out = parse_ai_response("DECISION: APPROVE\nCONFIDENCE: high\nREASONING: fine")
    assert out["decision"] == "APPROVE"
    assert out["confidence"] == 0


def test_empty_response_is_a_safe_reject():
    out = parse_ai_response("")
    assert out["decision"] == "REJECT"
    assert out["confidence"] == 0
    assert out["modifications"] == {}
