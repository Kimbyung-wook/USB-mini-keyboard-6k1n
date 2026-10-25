import pytest

from gui import macro


@pytest.mark.parametrize("text", [
    "",
    "Hello world",
    "Hello{ENTER}",
    "line1\nline2",
    "{{literal}}",
    "{{ENTER}}",
    "{CTRL+C}",
    "{ctrl+c}",
    "{CTRL+SHIFT+ESC}",
    "{ALT+F4}",
    "{WIN+R}{DELAY:300}notepad{ENTER}",
    "{DELAY:1}{DELAY:10000}",
    "{F1}{F12}{PGUP}{pgdn}{Ins}",
    "{SHIFT+1}",
    "{CTRL++}",
    "~!@#$%^&*()_+-=[]\\|;:'\",.<>/?` ",
])
def test_valid(text):
    result = macro.parse(text)
    assert result.ok, result.errors


def test_tokens():
    toks = macro.parse("a{{b}}\n{ctrl+shift+esc}{DELAY:50}{alt+f4}").tokens
    assert [(t.kind, t.value) for t in toks] == [
        ("char", "a"), ("char", "{"), ("char", "b"), ("char", "}"),
        ("key", "ENTER"), ("combo", "CTRL+SHIFT+ESC"), ("delay", "50"), ("combo", "ALT+F4"),
    ]


def _single_error(text):
    errors = macro.parse(text).errors
    assert len(errors) == 1, errors
    return errors[0]


def test_korean_rejected_with_position():
    err = _single_error("abc한글def")
    assert (err.start, err.end) == (3, 5)
    assert "ASCII" in err.message


def test_korean_inside_braces_rejected():
    err = _single_error("{CTRL+한}")
    assert err.start == 6


def test_unknown_key():
    err = _single_error("xx{FOO}")
    assert (err.start, err.end) == (2, 7)
    assert "FOO" in err.message


def test_unknown_modifier():
    assert "META" in _single_error("{META+C}").message


def test_unclosed_brace():
    err = _single_error("ab{ENTER")
    assert err.start == 2
    assert "닫히지" in err.message


def test_unclosed_brace_before_newline():
    err = _single_error("{ENTER\n{TAB}")
    assert err.start == 0


def test_stray_closing_brace():
    err = _single_error("a}b")
    assert (err.start, err.end) == (1, 2)


def test_empty_braces():
    _single_error("{}")


@pytest.mark.parametrize("text", ["{DELAY:0}", "{DELAY:10001}", "{DELAY:}", "{DELAY:abc}",
                                  "{DELAY}", "{DELAY:-5}"])
def test_delay_bounds(text):
    _single_error(text)


@pytest.mark.parametrize("text", ["{CTRL}", "{CTRL+}", "{+C}", "{CTRL+SHIFT}", "{CTRL+AB}"])
def test_bad_combos(text):
    _single_error(text)


def test_control_chars_rejected():
    assert "제어" in _single_error("a\tb").message


def test_multiple_errors_reported():
    assert len(macro.parse("{FOO} 한 }").errors) == 3


def test_byte_length():
    assert macro.parse("ab\n{ENTER}").byte_length == 10
    assert macro.stored_length("{{") == 2


def test_normalize_newlines():
    assert macro.normalize_newlines("a\r\nb\rc") == "a\nb\nc"
