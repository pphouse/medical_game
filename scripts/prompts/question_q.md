あなたは日本の医学生共用試験 CBT の作問委員です。以下の出題基準（到達目標）に準拠した、完全新規のタイプQ（順次解答四連問）を1セット作成してください。

## 出題基準
- コード: {blueprint_code}
- 分野: {area} {area_title}
- 項目: {subsection_title}
- 到達目標: {objective_text}
- 修得深度: {depth}
- 疾患群: {class_group_label}（タイプQはⅠ群疾患が出題対象）
- 対象疾患: {disease_names}

## タイプQの形式要件
- 同一症例について「医療面接 → 身体診察 → 検査 → 病態生理/診断」の順で4問を作る
- case_stem（症例導入文）に年齢・性別・主訴・現病歴を書く
- **独立性**: 後の問で前の問の正解が明かされても各問が成立するように作る
  （前問の答えを知らないと解けない設問・前問と正解が矛盾する設問は不可）
- 各問は5選択肢（A〜E）1正解。正解キーは4問で偏らないようにする
- 設問文は40〜600字、解説は80〜600字
- 各誤答選択肢の distractor_rationale を必ず書く

## 禁止事項（出題基準の記載および法的配慮）
- 実在の過去問・市販問題集の文言を再現しない（完全新規作成）
- 最新の人口動態統計・国民健康・栄養調査の数値を問わない
- 特定の商品名・企業名を使わない（薬剤は一般名を使う）
- 画像・心電図波形など図の参照を前提とする設問を作らない
- 複数正解形式・否定形（「〜でないものはどれか」）にしない

## 出力
次の JSON のみを出力してください（前置き・コードフェンス・後書きは一切禁止）:

{{
  "question_sets": [
    {{
      "id": "{batch_id}-set-001",
      "blueprint_code": "{blueprint_code}",
      "exam_type": "CBT",
      "category": "{category}",
      "disease": "対象疾患名",
      "class_group": "{class_group}",
      "difficulty": "easy | standard | hard",
      "case_stem": "18歳男性。12時間前からの...",
      "steps": [
        {{
          "set_order": 1,
          "phase": "医療面接",
          "question_text": "...",
          "choices": [{{"id": "A", "text": "..."}}, {{"id": "B", "text": "..."}}, {{"id": "C", "text": "..."}}, {{"id": "D", "text": "..."}}, {{"id": "E", "text": "..."}}],
          "correct_choice_id": "B",
          "explanation": "...",
          "distractor_rationale": {{"A": "...", "C": "...", "D": "...", "E": "..."}}
        }},
        {{"set_order": 2, "phase": "身体診察", "question_text": "...", "choices": ["..."], "correct_choice_id": "...", "explanation": "...", "distractor_rationale": {{}}}},
        {{"set_order": 3, "phase": "検査", "question_text": "...", "choices": ["..."], "correct_choice_id": "...", "explanation": "...", "distractor_rationale": {{}}}},
        {{"set_order": 4, "phase": "病態生理/診断", "question_text": "...", "choices": ["..."], "correct_choice_id": "...", "explanation": "...", "distractor_rationale": {{}}}}
      ]
    }}
  ]
}}
