from utils.text_processing import string_to_float, string_to_json, strip_json_fence


def test_strip_json_fence():
    test_string: str = "```json test ```"
    assert len(strip_json_fence(test_string)) == 4


def test_string_to_json():
    test_string: str = """{'test_key':'test_value'}"""
    test_dict: dict[str, str] = string_to_json(test_string)
    assert test_dict["test_key"] == "test_value"


def test_string_to_float():
    test_string: str = "ksh. 100.00"
    assert string_to_float(test_string) == 100.0
