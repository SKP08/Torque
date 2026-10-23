import pytest

from torque.conversation.conversation_policy import ConversationPolicy, is_stop_phrase
from torque.conversation.speech_analyzer import SpeechAnalyzer

analyzer = SpeechAnalyzer()
policy = ConversationPolicy()


@pytest.mark.parametrize("text,expected", [
    ("open edge actually open chrome", "open chrome"),
    ("open edge wait open file explorer", "open file explorer"),
    ("open microsoft edge umm no sorry open file explorer", "open file explorer"),
    ("Open Edge, actually, open Chrome.", "open chrome"),
    ("open final explainer yeah", "open final explainer"),
    ("open chrome please", "open chrome"),
    ("Torque, open chrome", "open chrome"),
    ("hey torque open spotify", "open spotify"),
])
def test_commands_are_corrected_and_cleaned(text, expected):
    assert analyzer.extract_corrected_text(text) == expected


@pytest.mark.parametrize("text", [
    "what's the difference between tcp and udp, actually explain it simply",
    "i'd rather use python for this project",
    "tell me about the wait time for lines",
    "sorry i'm late, what's the plan",
    "is that right",
    "do you think that's right",
])
def test_normal_sentences_are_never_cut(text):
    assert analyzer.extract_corrected_text(text) == analyzer.normalize(text).rstrip(" ,.!?")


def test_incomplete_detection_is_narrow():
    assert analyzer.appears_incomplete("open chrome and")
    assert analyzer.appears_incomplete("what is the difference between tcp and")
    assert not analyzer.appears_incomplete("what is that")
    assert not analyzer.appears_incomplete("what is it for")
    assert not analyzer.appears_incomplete("and")


def test_policy_intents():
    assert policy.analyze_input("")["intent"] == "empty"
    assert policy.analyze_input("okay")["intent"] == "acknowledgement"
    assert policy.analyze_input("open chrome and")["intent"] == "incomplete"
    assert policy.analyze_input("what's a prime number")["intent"] == "request"


@pytest.mark.parametrize("text", [
    "bye", "Bye!", "bye bye", "goodbye", "goodbye for now", "see you later",
    "Thank you, bye.", "okay thanks bye", "that's all", "good night", "stop listening",
])
def test_stop_phrases(text):
    assert is_stop_phrase(text), text


@pytest.mark.parametrize("text", [
    "say goodbye to my friend in french", "what does bye mean", "open chrome", "",
])
def test_not_stop_phrases(text):
    assert not is_stop_phrase(text), text
