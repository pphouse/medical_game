あなたは日本の医学生共用試験 CBT の作問委員です。以下の出題基準（到達目標）に準拠した、完全新規のタイプM（多選択肢択一）問題を{count}問作成してください。

## 出題基準
- コード: {blueprint_code}
- 分野: {area} {area_title}
- 項目: {subsection_title}
- 到達目標: {objective_text}
- 修得深度: {depth}（「説明できる」= 標準〜難、「概説できる」= 易〜標準 を目安に難易度を設定）
- 疾患群: {class_group_label}
- 対象疾患: {disease_names}

## 形式要件
- 5選択肢（A〜E）から正解1つを選ぶ形式
- 設問文は40〜600字。臨床像を問う場合は年齢・性別・主訴・経過を含む簡潔な症例文にする
- 選択肢は互いに排他的で、長さ・具体度を揃える（正解だけが長い/詳しい、という偏りを作らない）
- 正解キーは A〜E に偏りなく割り当てる
- 解説（explanation）は80〜600字で、正解の根拠を病態生理から説明する
- 各誤答選択肢について「なぜ誤りか」を distractor_rationale に必ず書く

## 禁止事項（出題基準の記載および法的配慮）
- 実在の過去問・市販問題集の文言を再現しない（表現も含め完全新規に作成する）
- 最新の人口動態統計・国民健康・栄養調査の数値を問わない
- 特定の商品名・企業名を使わない（薬剤は一般名を使う）
- 画像・心電図波形など図の参照を前提とする設問を作らない
- 「すべて選べ」等の複数正解形式にしない
- 「〜でないものはどれか」等の否定形は原則使わない

## 出力
次の JSON のみを出力してください（前置き・コードフェンス・後書きは一切禁止）:

{{
  "questions": [
    {{
      "id": "{batch_id}-001",
      "question_type": "M",
      "exam_type": "CBT",
      "blueprint_code": "{blueprint_code}",
      "category": "{category}",
      "disease": "対象疾患名",
      "class_group": "{class_group}",
      "difficulty": "easy | standard | hard",
      "question_text": "...",
      "choices": [
        {{"id": "A", "text": "..."}},
        {{"id": "B", "text": "..."}},
        {{"id": "C", "text": "..."}},
        {{"id": "D", "text": "..."}},
        {{"id": "E", "text": "..."}}
      ],
      "correct_choice_id": "C",
      "explanation": "...",
      "distractor_rationale": {{"A": "なぜ誤りか", "B": "...", "D": "...", "E": "..."}}
    }}
  ]
}}
