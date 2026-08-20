"""簡易IRT（2PLロジスティックモデル）: CBT模試の「予想IRT」算出用。

外部ライブラリ（numpy/scipy）を使わず pure Python で実装する。
（サーバーレス関数サイズを抑える方針, docs/deploy-vercel.md 参照）

- calibrate(): 周辺最尤推定（MMLE）を EM アルゴリズムで解き、項目パラメータ
  a（識別力）・b（困難度）を過去の解答履歴から較正する。M-step は勾配法
  （厳密なNewton-Raphsonの代わりに正規化した勾配で少数ステップ更新）。
- estimate_theta(): 較正済みパラメータ + 標準正規分布を事前分布とした
  MAP推定（Newton-Raphson）で受験者の能力値 θ を求める。
"""

import math

QUAD_POINTS = [-4.0 + 0.4 * i for i in range(21)]  # -4.0 〜 4.0 を21等分


def _normal_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


_RAW_WEIGHTS = [_normal_pdf(x) for x in QUAD_POINTS]
_WEIGHT_SUM = sum(_RAW_WEIGHTS)
QUAD_WEIGHTS = [w / _WEIGHT_SUM for w in _RAW_WEIGHTS]  # 事前分布 N(0,1) の近似

DEFAULT_A = 1.0
# Question.difficulty (1易/2標準/3難) から決め打ちする初期困難度
DIFFICULTY_TO_B = {1: -1.0, 2: 0.0, 3: 1.0}


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _prob_correct(theta, a, b):
    z = a * (theta - b)
    if z > 35:
        return 1.0
    if z < -35:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def calibrate(responses, item_params, *, iterations=8, m_steps=5, min_responses=20):
    """項目パラメータを EM法（MMLE）で較正する。

    responses: (item_id, examinee_id, correct: bool) のイテラブル。
    item_params: {item_id: {"a":.., "b":..}} の初期値（呼び出し側は変更しない）。
    戻り値: {item_id: {"a":.., "b":.., "n":解答数}}。解答数が min_responses
    未満の項目は初期値のまま返す（較正しない）。
    """
    by_examinee = {}
    n_by_item = {}
    for item_id, examinee_id, correct in responses:
        by_examinee.setdefault(examinee_id, []).append((item_id, bool(correct)))
        n_by_item[item_id] = n_by_item.get(item_id, 0) + 1

    calibratable = {iid for iid, n in n_by_item.items() if n >= min_responses}
    params = {iid: dict(p) for iid, p in item_params.items()}
    for iid in calibratable:
        params.setdefault(iid, {"a": DEFAULT_A, "b": 0.0})

    if calibratable:
        for _ in range(iterations):
            # E-step: 受験者ごとの θ 事後分布（quadrature 上の重み）
            posteriors = []
            for answers in by_examinee.values():
                relevant = [(iid, c) for iid, c in answers if iid in calibratable]
                if not relevant:
                    continue
                weights = []
                for k, theta in enumerate(QUAD_POINTS):
                    logl = 0.0
                    for iid, correct in relevant:
                        p = _clamp(_prob_correct(theta, params[iid]["a"], params[iid]["b"]), 1e-6, 1 - 1e-6)
                        logl += math.log(p) if correct else math.log(1 - p)
                    weights.append(QUAD_WEIGHTS[k] * math.exp(logl))
                total = sum(weights) or 1.0
                posteriors.append(([w / total for w in weights], relevant))

            # M-step: 項目ごとに期待対数尤度を最大化する a, b を勾配法で更新
            for iid in calibratable:
                a, b = params[iid]["a"], params[iid]["b"]
                for _step in range(m_steps):
                    exp_correct = [0.0] * len(QUAD_POINTS)
                    exp_total = [0.0] * len(QUAD_POINTS)
                    for post, relevant in posteriors:
                        for r_iid, correct in relevant:
                            if r_iid != iid:
                                continue
                            for k in range(len(QUAD_POINTS)):
                                exp_total[k] += post[k]
                                if correct:
                                    exp_correct[k] += post[k]
                    n_total = sum(exp_total)
                    if n_total <= 0:
                        break
                    grad_a, grad_b = 0.0, 0.0
                    for k, theta in enumerate(QUAD_POINTS):
                        n_k = exp_total[k]
                        if n_k <= 0:
                            continue
                        r_k = exp_correct[k]
                        p = _clamp(_prob_correct(theta, a, b), 1e-6, 1 - 1e-6)
                        residual = r_k - n_k * p
                        grad_a += residual * (theta - b)
                        grad_b += residual * (-a)
                    # 較正データ量に依存しない安定したステップ幅にするため正規化
                    a += 1.0 * (grad_a / n_total)
                    b += 1.0 * (grad_b / n_total)
                    a = _clamp(a, 0.2, 3.0)
                    b = _clamp(b, -4.0, 4.0)
                params[iid] = {"a": a, "b": b}

    return {iid: dict(p, n=n_by_item.get(iid, 0)) for iid, p in params.items()}


def estimate_theta(responses, item_params, *, prior_sd=1.0, iterations=15):
    """MAP推定（Newton-Raphson, 事前分布 N(0, prior_sd^2)）で能力値θを求める。

    responses: (item_id, correct: bool) のイテラブル（1受験者分）。
    item_params: {item_id: {"a":.., "b":..}}。
    """
    theta = 0.0
    prior_var = prior_sd * prior_sd
    for _ in range(iterations):
        grad = -theta / prior_var
        hess = -1.0 / prior_var
        for item_id, correct in responses:
            params = item_params.get(item_id, {"a": DEFAULT_A, "b": 0.0})
            a, b = params["a"], params["b"]
            p = _clamp(_prob_correct(theta, a, b), 1e-6, 1 - 1e-6)
            grad += a * ((1.0 if correct else 0.0) - p)
            hess -= (a * a) * p * (1 - p)
        if hess == 0:
            break
        step = grad / hess
        theta -= step
        theta = _clamp(theta, -4.0, 4.0)
        if abs(step) < 1e-4:
            break
    return theta


def scaled_score(theta):
    """偏差値と同じ感覚で読める 50+10θ スケール（IRT予想偏差値相当）。"""
    return round(50 + 10 * theta, 1)


def seed_item_params(question):
    """未較正の問題向けの初期パラメータ（Question.difficulty から決め打ち）。"""
    return {"a": DEFAULT_A, "b": DIFFICULTY_TO_B.get(question.difficulty, 0.0)}
