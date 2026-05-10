"""regional_ocr.markdown のユニットテスト（AC-15〜AC-20, AC-42, AC-47）。"""

from __future__ import annotations

from nova_parser.regional_ocr.markdown import render_markdown, write_markdown
from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_rect(rect_id: str, draw_order: int) -> Rectangle:
    """テスト用の Rectangle を生成するヘルパー。"""
    return Rectangle(rect_id=rect_id, draw_order=draw_order, x=0, y=0, width=100, height=100)


def _make_done_record(rect_id: str, draw_order: int, text: str) -> RegionRecord:
    """ocr_status='done' の RegionRecord を生成するヘルパー。"""
    return RegionRecord(rectangle=_make_rect(rect_id, draw_order), text=text, ocr_status="done")


def _make_session(records: list[RegionRecord]) -> ImageSession:
    """指定した RegionRecord リストを持つ ImageSession を生成するヘルパー。"""
    return ImageSession(image_name="test.png", image_width=800, image_height=600, regions=records)


# ---------------------------------------------------------------------------
# AC-15: draw_order 昇順・'---' 区切りの確認
# ---------------------------------------------------------------------------


def test_render_markdown_returns_text_in_draw_order_ascending_with_separator():
    """AC-15: render_markdown に ocr_status='done' の RegionRecord が draw_order=2,1,0 の順で格納された
    ImageSession を渡したとき、返却文字列が draw_order 昇順（0,1,2）のテキストを
    '\\n\\n---\\n\\n' で区切った内容になる。
    """
    records = [
        _make_done_record("r3", 2, "text_order_2"),
        _make_done_record("r2", 1, "text_order_1"),
        _make_done_record("r1", 0, "text_order_0"),
    ]
    session = _make_session(records)
    result = render_markdown(session)
    expected = "text_order_0\n\n---\n\ntext_order_1\n\n---\n\ntext_order_2"
    assert result == expected


# ---------------------------------------------------------------------------
# AC-16: 1 件のみの場合は '---' が含まれない
# ---------------------------------------------------------------------------


def test_render_markdown_no_separator_for_single_record():
    """AC-16: render_markdown に ocr_status='done' の RegionRecord が 1 件だけ含まれる ImageSession を渡したとき、
    返却文字列に '---' が含まれない（区切り文字は 2 件以上の間にのみ挿入される）。
    """
    records = [_make_done_record("r1", 0, "only_text")]
    session = _make_session(records)
    result = render_markdown(session)
    assert "---" not in result
    assert result == "only_text"


# ---------------------------------------------------------------------------
# AC-17: 'pending' と 'error' のみの場合は空文字列
# ---------------------------------------------------------------------------


def test_render_markdown_returns_empty_string_when_no_done_records():
    """AC-17: render_markdown に ocr_status='pending' と 'error' の RegionRecord のみが含まれる
    ImageSession を渡したとき、返却文字列が空文字列 '' となる。
    """
    records = [
        RegionRecord(rectangle=_make_rect("r1", 0), text=None, ocr_status="pending"),
        RegionRecord(rectangle=_make_rect("r2", 1), text="err", ocr_status="error"),
    ]
    session = _make_session(records)
    result = render_markdown(session)
    assert result == ""


# ---------------------------------------------------------------------------
# AC-18: 'done' と 'pending' が混在する場合、'pending' のテキストを含まない
# ---------------------------------------------------------------------------


def test_render_markdown_excludes_pending_records_text():
    """AC-18: render_markdown に ocr_status='done' と 'pending' が混在する ImageSession を渡したとき、
    返却文字列に 'pending' の RegionRecord の text が含まれない。
    """
    records = [
        _make_done_record("r1", 0, "done_text"),
        RegionRecord(rectangle=_make_rect("r2", 1), text="pending_text", ocr_status="pending"),
    ]
    session = _make_session(records)
    result = render_markdown(session)
    assert "done_text" in result
    assert "pending_text" not in result


# ---------------------------------------------------------------------------
# AC-19: write_markdown がファイルを作成し Path を返す
# ---------------------------------------------------------------------------


def test_write_markdown_creates_file_and_returns_path(tmp_path):
    """AC-19: write_markdown を呼び出したとき、output_dir 配下に '<image_stem>.regions.md' ファイルが作成され、
    返却値がそのファイルの Path となる。
    """
    records = [_make_done_record("r1", 0, "hello")]
    session = _make_session(records)
    result_path = write_markdown(session, tmp_path, "myimage")
    expected_path = tmp_path / "myimage.regions.md"
    assert result_path == expected_path
    assert expected_path.exists()


# ---------------------------------------------------------------------------
# AC-20: render_markdown が空文字を返す場合でもファイルが作成される
# ---------------------------------------------------------------------------


def test_write_markdown_creates_empty_file_when_no_done_records(tmp_path):
    """AC-20: write_markdown を render_markdown が空文字を返す ImageSession で呼び出したとき、
    ファイルが作成され、内容が空文字列（0 バイト）となる。
    """
    records = [
        RegionRecord(rectangle=_make_rect("r1", 0), text=None, ocr_status="pending"),
    ]
    session = _make_session(records)
    result_path = write_markdown(session, tmp_path, "myimage")
    assert result_path.exists()
    assert result_path.read_bytes() == b""


# ---------------------------------------------------------------------------
# AC-42: write_markdown の atomic 書き込み確認
# ---------------------------------------------------------------------------


def test_write_markdown_atomic_write_file_is_readable_after_completion(tmp_path):
    """AC-42: write_markdown が書き込みを行う際、最終ファイルへの rename 前に一時ファイルを経由する
    atomic 書き込みが行われる。テストでは tmp_path を output_dir として write_markdown を呼び出し、
    完了後に .regions.md ファイルが読み取れることで検証する。
    """
    records = [_make_done_record("r1", 0, "atomic_test")]
    session = _make_session(records)
    result_path = write_markdown(session, tmp_path, "atomic_image")
    # 完了後にファイルが存在し、読み取り可能であることを確認
    assert result_path.exists()
    content = result_path.read_text(encoding="utf-8")
    assert "atomic_test" in content


# ---------------------------------------------------------------------------
# AC-47: write_markdown 完了後に .tmp ファイルが残存しない
# ---------------------------------------------------------------------------


def test_write_markdown_no_tmp_file_remains_after_completion(tmp_path):
    """AC-47: write_markdown 完了後に tmp_path 配下に '*.tmp' サフィックスのファイルが残存しない
    （cleanup 確認）。
    """
    records = [_make_done_record("r1", 0, "cleanup_test")]
    session = _make_session(records)
    write_markdown(session, tmp_path, "cleanup_image")

    remaining_tmp_files = list(tmp_path.glob("*.tmp"))
    assert remaining_tmp_files == []
