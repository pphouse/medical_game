"""問題演習ランキング（個人・全国/学内）の学年フィルタ共通処理。

対戦ランクとは違い、演習ランキングは「同学年の中での順位」を見せる
（学年が違えば解いている範囲も違うので比べても意味が薄い）。対戦は逆に
全学年まとめてランク付けする（spec の対戦ランク仕様どおり）ので、
ここは RankingView / RankDetailView（どちらも演習側）だけが使う。

RankingSnapshot.rank は集計バッチ（aggregate_rankings）が学年をまたいだ
全体で振った値なので、学年で絞り込んだあとにそのまま使うと歯抜けの順位に
なる（例: 全体1,2,4,7位が同学年でも、絞り込み後の表示は1,2,3,4位で
あるべき）。そのため読み出し時に value で並べ替えて順位を振り直す。
"""


def grade_ranked_rows(qs, grade):
    """qs（RankingSnapshot の QuerySet）を grade で絞り込み、value 降順で
    連続した順位（同値は同順位）を振り直して [(rank, row), ...] を返す。"""
    rows = list(qs.filter(profile__grade=grade).order_by("-value"))
    prev_value, prev_rank = None, 0
    result = []
    for i, row in enumerate(rows, start=1):
        rank = prev_rank if row.value == prev_value else i
        prev_value, prev_rank = row.value, rank
        result.append((rank, row))
    return result
