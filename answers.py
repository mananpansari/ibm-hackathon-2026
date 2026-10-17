"""Structured customer questions (UI v2): the Q1 -> Q2 -> Q3 tree and a classifier for its answers.

The question tier asks up to three multiple-choice questions plus an optional free-text box. The
page walks QUESTIONS by each option's `next` and posts the whole answer once; the engine needs no
change, because StructuredClassifier is a drop-in for Engine(classifier=...):

    engine = Engine(..., classifier=StructuredClassifier(granite))
    engine.decide(w, answer={"why": "officer", "how": "phone", "asked": ["secret"], "text": "..."})

A plain string answer still goes straight to the free-text classifier (the old flow). The free-text
classifier is injected: granite (templates + keywords when Granite is off) now, B's NLP model when it
lands, as long as it has classify(text) -> {"scam_type", "confirms_script", "source"}.

The rules below are policy, not measurements: which answers count as a scam script is our judgement
from the advisories (advisories.txt), and is modelled wherever it feeds a result.

    python answers.py   # self-check
"""
import granite
from engine import TEMPLATE_QUESTION

QUESTIONS = {
    "start": "why",
    "questions": {
        "why": {
            "title": "Security check before your payment is sent",
            "intro": "Real police, bank or government officers never ask you to move your savings to a \"safe\" wallet.",
            "text": "Why are you sending this money?",
            "type": "single",
            "free_text": True,  # the optional box, labelled with the question answer_nlp was trained on
            "options": [
                {"id": "known", "text": "Paying someone I know and trust", "next": None},
                {"id": "own_platform", "text": "Investing on a platform I chose myself", "next": None},
                {"id": "contacted", "text": "Someone contacted me and told me to move my money", "next": "how"},
                {"id": "officer", "text": "An officer from the government, a bank or the police asked me to", "next": "how"},
                {"id": "other", "text": "Something else", "next": None},
            ],
        },
        "how": {
            "title": "Additional details needed",
            "text": "How did this person contact you?",
            "type": "single",
            "free_text": False,
            "options": [
                {"id": "phone", "text": "A phone call", "next": "asked"},
                {"id": "text_whatsapp", "text": "A text or WhatsApp message", "next": "asked"},
                {"id": "social_dating", "text": "Social media or a dating app", "next": "asked"},
                {"id": "email", "text": "An email", "next": "asked"},
                {"id": "in_person", "text": "In person", "next": "asked"},
                {"id": "not_sure", "text": "I'm not sure", "next": "asked"},
            ],
        },
        "asked": {
            "title": "Final security question",
            "text": "Did this person ask you to do any of these?",
            "hint": "Tick all that apply.",
            "type": "multi",
            "free_text": False,
            "options": [
                {"id": "secret", "text": "Keep this a secret from family or the bank", "next": None},
                {"id": "act_fast", "text": "Act quickly or today", "next": None},
                {"id": "new_account", "text": "Open a new crypto account", "next": None},
                {"id": "safe_wallet", "text": "Move savings to a \"safe\" wallet", "next": None},
                {"id": "install_app", "text": "Install an app or share your screen", "next": None},
                {"id": "none", "text": "None of these", "next": None},
            ],
        },
    },
}
# Options the page keeps last when it shuffles the rest.
FIXED_LAST = {"other", "not_sure", "none"}


def _options(qid):
    return {o["id"]: o for o in QUESTIONS["questions"][qid]["options"]}


def validate(answer):
    """The answered path, e.g. ["why", "how", "asked"]. ValueError if the answer doesn't follow the tree:
    unknown ids, a missing or extra question, a list for a single choice, or "none" ticked with others."""
    if not isinstance(answer, dict):
        raise ValueError("a structured answer is a dict")
    text = answer.get("text", "")
    if not isinstance(text, str) or len(text) > 2000:
        raise ValueError("text must be a string of at most 2,000 characters")
    path, qid = [], QUESTIONS["start"]
    while qid:
        q, got = QUESTIONS["questions"][qid], answer.get(qid)
        opts = _options(qid)
        if q["type"] == "single":
            if not isinstance(got, str) or got not in opts:
                raise ValueError(f"{qid}: expected one of {sorted(opts)}, got {got!r}")
            nxt = opts[got]["next"]
        else:
            if not isinstance(got, list) or not got or any(g not in opts for g in got) or len(set(got)) != len(got):
                raise ValueError(f"{qid}: expected a non-empty list from {sorted(opts)}, got {got!r}")
            if "none" in got and len(got) > 1:
                raise ValueError(f"{qid}: 'none' can't be ticked with anything else")
            nxt = None
        path.append(qid)
        qid = nxt
    extra = set(answer) - set(path) - {"text"}
    if extra:
        raise ValueError(f"answers to questions not on this path: {sorted(extra)}")
    return path


def _scam_type(a, free):
    """One of granite.SCAM_TYPES for the engine's reason text."""
    asked = set(a.get("asked", []))
    if a["why"] == "officer" or "safe_wallet" in asked:
        return "government_impersonation"  # the "safe wallet" script is the police/official one
    if free and free["confirms_script"] and free["scam_type"] != "none":
        return free["scam_type"]
    if a.get("how") == "social_dating":
        return "romance"
    if a["why"] == "own_platform" or "new_account" in asked:
        return "investment"
    if "install_app" in asked:
        return "tech_support"
    return "bank_impersonation" if a["why"] == "contacted" else "none"


class StructuredClassifier:
    """Engine classifier for structured answers; strings go to the injected free-text classifier."""

    def __init__(self, free_text=granite):
        self.free_text = free_text

    def ask(self, withdrawal, reasons):
        ask = getattr(self.free_text, "ask", None)
        return ask(withdrawal, reasons) if ask else TEMPLATE_QUESTION

    def classify(self, answer):
        if isinstance(answer, str):
            return self.free_text.classify(answer)
        validate(answer)
        text = answer.get("text", "").strip()
        free = self.free_text.classify(text) if text else None
        asked = set(answer.get("asked", [])) - {"none"}
        # Being told to pay by an "officer" is the script itself; so is any Q3 pressure tactic.
        # A clean structured answer never cancels a confirming free-text answer.
        confirms = answer["why"] == "officer" or bool(asked) or bool(free and free["confirms_script"])
        return {"scam_type": _scam_type(answer, free) if confirms else "none", "confirms_script": confirms,
                "source": "structured" + (f"+{free['source']}" if free else "")}


def _self_check():
    from decision_log import DecisionLog, verify
    from engine import Engine, FixedClock, Withdrawal
    from payee_memory import PayeeMemory
    import tempfile
    from pathlib import Path

    class Stub:  # free-text classifier: confirms when the text mentions police
        def classify(self, text):
            hit = "police" in text.lower()
            return {"scam_type": "government_impersonation" if hit else "none", "confirms_script": hit, "source": "stub"}

    c = StructuredClassifier(Stub())
    officer = {"why": "officer", "how": "phone", "asked": ["secret", "act_fast"]}
    assert validate(officer) == ["why", "how", "asked"]
    assert validate({"why": "known"}) == ["why"]
    for bad in ({"why": "nope"}, {"why": "known", "how": "phone"}, {"why": "contacted", "how": "phone"},
                {"why": "contacted", "how": "phone", "asked": ["none", "secret"]},
                {"why": "contacted", "how": "phone", "asked": "secret"}, {"why": ["known"]}, "x"):
        try:
            validate(bad)
            raise AssertionError(f"accepted {bad!r}")
        except ValueError:
            pass
    r = c.classify(officer)
    assert r == {"scam_type": "government_impersonation", "confirms_script": True, "source": "structured"}, r
    assert c.classify({"why": "officer", "how": "phone", "asked": ["none"]})["confirms_script"], "an officer asking is the script"
    assert c.classify({"why": "contacted", "how": "social_dating", "asked": ["act_fast"]})["scam_type"] == "romance"
    assert not c.classify({"why": "contacted", "how": "email", "asked": ["none"]})["confirms_script"]
    assert c.classify({"why": "known"}) == {"scam_type": "none", "confirms_script": False, "source": "structured"}
    r = c.classify({"why": "known", "text": "the police told me to"})
    assert r["confirms_script"] and r["source"] == "structured+stub", "a clean choice never cancels a confirming text"
    assert c.classify("the police said move it")["source"] == "stub", "plain strings still work"
    for o in QUESTIONS["questions"].values():
        for opt in o["options"]:
            assert opt["next"] is None or opt["next"] in QUESTIONS["questions"]
    real = StructuredClassifier()  # granite: templates + keywords without a model
    assert real.classify({"why": "known"})["confirms_script"] is False
    assert {real.classify(a)["scam_type"] for a in (officer, {"why": "own_platform", "text": "guaranteed returns"})} <= set(granite.SCAM_TYPES)

    with tempfile.TemporaryDirectory() as d:  # end to end through the unchanged engine
        clock = FixedClock(1_000_000)
        eng = Engine(lambda w, t: None, PayeeMemory(), clock, DecisionLog(Path(d) / "log.jsonl"), classifier=c)
        w = Withdrawal("alice", "0xscam", 5000, clock.now)
        assert eng.decide(w).tier == "question", "large first-time payee gets the questions"
        held = eng.decide(w, answer=officer)
        assert held.tier == "hold" and any(x.signal == "answer_confirms_script" for x in held.reasons), held
        clock.now += 3600
        bob = eng.decide(Withdrawal("bob", "0xscam", 200, clock.now))
        assert bob.tier == "hold", "the next customer is held by alice's answer"
        ok = Withdrawal("carol", "0xfriend", 5000, clock.now)
        assert eng.decide(ok, answer={"why": "known"}).tier == "release"
        demo = eng.decide(Withdrawal("dave", "0xother", 5000, clock.now), answer=officer, answer_kind="modelled")
        assert [x.kind for x in demo.reasons if x.signal == "answer_confirms_script"] == ["modelled"]
        assert verify(Path(d) / "log.jsonl") is None, "structured answers chain in the decision log"
    print("self-check passed: answers (tree, validation, classifier, engine end to end)")


if __name__ == "__main__":
    _self_check()
