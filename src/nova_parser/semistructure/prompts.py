"""半構造化LLM推定のプロンプト契約。"""

STRUCTURE_CLASSIFICATION_RULES = """\
- 本文、要約、訂正文を生成しない。
- 出力できる block_id は入力に存在するものだけとする。
- block_id の順序を変更しない。
- GMを継承した範囲を player/shared に変更したい場合も audience は gm のままとし、
  review_reasons に audience_downgrade_candidate を追加する。
- entities は入力本文に完全一致する文字列だけを返す。
"""

STRUCTURE_CLASSIFICATION_PROMPT = f"""\
あなたはTRPG書籍の構造を、提示されたブロックへの参照だけで分類します。
次の規則を厳守してください。

{STRUCTURE_CLASSIFICATION_RULES}
前後ページのブロックは文脈専用です。segments には中心ページの block_id だけを返してください。
"""

OUTLINE_INFERENCE_PROMPT = """\
TRPG書籍のページ別サンプルから、書籍全体の粗い章構成を推定してください。
各章について title、start_page、end_page、default_content_type、section_path、confidence
だけを返してください。提示されていない本文を生成しないでください。
"""
