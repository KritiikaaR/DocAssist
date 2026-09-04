"""
Tests for _parse_quiz_response — cleaning and validating the model's quiz JSON.

The model is asked for raw JSON but sometimes wraps it in markdown fences or
returns something malformed, so this is the defensive layer between the model
and the user.
"""

import json

import pytest

from rag import RAGPipeline

VALID_QUIZ = {
    "questions": [
        {
            "id": "q1",
            "type": "true_false",
            "question": "Is this a test?",
            "correct_answer": "true",
            "explanation": "It is.",
        }
    ]
}


def test_parses_plain_json():
    result = RAGPipeline._parse_quiz_response(json.dumps(VALID_QUIZ))
    assert result["questions"][0]["id"] == "q1"


def test_strips_json_code_fence():
    """The model often wraps output in ```json ... ``` despite being told not to."""
    raw = "```json\n" + json.dumps(VALID_QUIZ) + "\n```"
    result = RAGPipeline._parse_quiz_response(raw)
    assert len(result["questions"]) == 1


def test_strips_bare_code_fence():
    raw = "```\n" + json.dumps(VALID_QUIZ) + "\n```"
    result = RAGPipeline._parse_quiz_response(raw)
    assert len(result["questions"]) == 1


def test_tolerates_surrounding_whitespace():
    raw = "\n\n  " + json.dumps(VALID_QUIZ) + "  \n\n"
    result = RAGPipeline._parse_quiz_response(raw)
    assert len(result["questions"]) == 1


def test_malformed_json_raises_value_error():
    with pytest.raises(ValueError):
        RAGPipeline._parse_quiz_response("{ this is not valid json")


def test_missing_questions_key_raises():
    with pytest.raises(ValueError):
        RAGPipeline._parse_quiz_response(json.dumps({"quiz": []}))


def test_empty_questions_list_raises():
    """An empty quiz would render as a blank screen, so reject it here."""
    with pytest.raises(ValueError):
        RAGPipeline._parse_quiz_response(json.dumps({"questions": []}))


def test_questions_not_a_list_raises():
    with pytest.raises(ValueError):
        RAGPipeline._parse_quiz_response(json.dumps({"questions": "q1, q2"}))


def test_top_level_list_raises():
    """A bare array is valid JSON but the wrong shape for the frontend."""
    with pytest.raises(ValueError):
        RAGPipeline._parse_quiz_response(json.dumps([VALID_QUIZ]))
