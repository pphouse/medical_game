# 国試の解説

取り込み時点の国試1153問には解説が無く、「詳しい解説は準備中です」という
プレースホルダが入っていた。ここはその中身を書き足すための置き場。

## ファイルの持ち方

回ごとに `114.json` … `119.json`。キーは `blueprint_code`（"114-A-1"）で、
国試データ側と 1:1 に対応する（1153件すべて一意であることを確認済み）。

```json
{
  "114-A-1": {
    "point": "正答の根拠と、この設問で問われている知識。",
    "distractors": {
      "A": "なぜ誤りか。",
      "B": "なぜ誤りか。"
    }
  }
}
```

書くのは `point` と誤答の理由だけでよい。「正答は D「…」。」の行、出典表記、
断り書きは `build_kokushi_explanations.py` が設問データから機械的に付ける。
正答の記号や選択肢の文言を手で書き写すと、データとずれたときに気づけない。

## 反映

```
python scripts/build_kokushi_explanations.py            # 組み立て + 検証
python backend/manage.py apply_kokushi_explanations     # ローカルDBへ
python scripts/build_kokushi_explanations.py --sql out.sql   # 本番用SQL
```

## 監修について

ここに書かれた解説はアプリ側で作成したもので、厚生労働省が公表している
過去問には含まれない。出典表記（Public Data License 1.0）が及ぶのは設問文と
選択肢だけなので、解説を出典の中に混ぜて表示してはいけない。組み立て側で
別段落に分け、アプリ作成であることを明記している。

医学的な監修は未了。監修が済んだものから `"reviewed": true` を付けていく。
