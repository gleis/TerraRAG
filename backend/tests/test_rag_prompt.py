from app.rag import TEACHING_SYSTEM_PROMPT


def test_teaching_prompt_requires_grounded_explanations_and_examples() -> None:
    assert "Use only the supplied selected-corpus evidence" in TEACHING_SYSTEM_PROMPT
    assert "### Direct answer" in TEACHING_SYSTEM_PROMPT
    assert "### Example" in TEACHING_SYSTEM_PROMPT
    assert "Illustrative" in TEACHING_SYSTEM_PROMPT
    assert "### Check your understanding" in TEACHING_SYSTEM_PROMPT
    assert "Cite every factual paragraph and every example" in TEACHING_SYSTEM_PROMPT
