from pms.agents.acp.codex import build_codex_args


def test_build_codex_args_with_model():
    args = build_codex_args(["--flag"], "gpt-5", "medium")

    assert args == [
        "--flag",
        "-c",
        'model="gpt-5"',
        "-c",
        'model_reasoning_effort="medium"',
    ]


def test_build_codex_args_without_overrides():
    args = build_codex_args(["--flag"], None, None)

    assert args == ["--flag"]
