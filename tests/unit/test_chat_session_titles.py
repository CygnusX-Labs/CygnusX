from omichub.application.services.chat_service import ChatService


def test_clean_session_title_removes_wrappers_and_limits_length():
    title = ChatService._clean_session_title('  「RNA-seq\n差异表达分析与可视化工作流优化方案」  ')

    assert title == "RNA-seq差异表达分析与可视化工作流优化方案"
    assert len(title) <= 30


def test_fallback_session_title_truncates_long_message():
    title = ChatService._fallback_session_title("请帮我分析这个项目中的所有RNA测序样本并绘制火山图")

    assert title.endswith("…")
    assert len(title) == 21


def test_escape_like_treats_wildcards_as_text():
    assert ChatService._escape_like(r"RNA_100%\done") == r"RNA\_100\%\\done"


def test_search_snippet_centers_keyword_and_marks_truncation():
    content = "前文" * 40 + "差异表达" + "后文" * 40

    snippet = ChatService._build_search_snippet(content, "差异表达")

    assert "差异表达" in snippet
    assert snippet.startswith("…")
    assert snippet.endswith("…")
