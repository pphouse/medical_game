#!/usr/bin/env python3
"""LLM 問題生成スクリプト (spec 2-2).

    usage: generate_questions.py --area D-5 --count 40 --type M --out data/generated/

- CBTBlueprint から対象コードを取得し、コード単位で生成をループする。
- Anthropic API を直接叩く（1リクエスト = 1〜4問。大量一括生成は品質が
  落ちるため blueprint_code ごとに独立させる）。
- 出力はバッチ JSON。取り込み前に必ず scripts/validate_questions.py を通し、
  import_questions で status=pending として取り込み、人手レビューを経て
  公開する。**生成物を無審査で公開してはならない。**

環境変数: ANTHROPIC_API_KEY（必須）, DATABASE_URL（CBTBlueprint 参照用）
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

from _django import setup_django

setup_django()

import anthropic  # noqa: E402

from quiz.models import CBTBlueprint  # noqa: E402

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
DEFAULT_MODEL = "claude-opus-4-8"
MAX_QUESTIONS_PER_REQUEST = 4

CLASS_GROUP_LABELS = {"I": "Ⅰ群（病因〜診断まで修得必須）", "II": "Ⅱ群", "": "（指定なし）"}


def load_prompt(question_type):
    name = "question_m.md" if question_type == "M" else "question_q.md"
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def build_prompt(template, blueprint, *, count, batch_id, category):
    return template.format(
        count=count,
        blueprint_code=blueprint.code,
        area=blueprint.area,
        area_title=blueprint.area_title,
        subsection_title=blueprint.subsection_title or blueprint.area_title,
        objective_text=blueprint.objective_text,
        depth=blueprint.depth or "説明できる",
        class_group=blueprint.class_group,
        class_group_label=CLASS_GROUP_LABELS.get(blueprint.class_group, "（指定なし）"),
        disease_names="、".join(blueprint.disease_names) or blueprint.subsection_title or "到達目標に準ずる",
        batch_id=batch_id,
        category=category,
    )


def parse_json_response(text):
    """モデル出力から JSON を取り出す（コードフェンスで包まれた場合に耐性を持たせる）。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text)


def generate_for_blueprint(client, template, blueprint, *, question_type, count, batch_id, category, model):
    prompt = build_prompt(template, blueprint, count=count, batch_id=batch_id, category=category)
    # 出力が長くなるためストリーミングで受ける（タイムアウト回避）
    with client.messages.stream(
        model=model,
        max_tokens=32000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        print(f"  ! {blueprint.code}: モデルが生成を拒否しました (stop_details={response.stop_details})")
        return None

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return parse_json_response(text)
    except json.JSONDecodeError as exc:
        print(f"  ! {blueprint.code}: JSON parse error: {exc}")
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", required=True, help='例 "D-5"')
    parser.add_argument("--count", type=int, default=40, help="タイプM: 問題数 / タイプQ: セット数")
    parser.add_argument("--type", dest="question_type", choices=["M", "Q"], default="M")
    parser.add_argument("--out", default="data/generated/")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--category", default=None, help="未指定なら area_title を使う")
    args = parser.parse_args()

    blueprints = list(
        CBTBlueprint.objects.filter(area=args.area).order_by("code")
    )
    if args.question_type == "Q":
        # タイプQはⅠ群疾患が出題対象 (spec 3.1)。未分類しかなければ全件から選ぶ。
        group1 = [b for b in blueprints if b.class_group == "I"]
        blueprints = group1 or blueprints
    if not blueprints:
        print(f"CBTBlueprint に {args.area} のコードがありません。import_blueprint を先に実行してください。")
        sys.exit(1)

    client = anthropic.Anthropic()
    template = load_prompt(args.question_type)
    today = datetime.date.today().strftime("%Y%m%d")
    batch_id = f"cbt-{args.area}-{args.question_type}-{today}"
    category = args.category or blueprints[0].area_title

    questions, question_sets = [], []
    remaining = args.count
    i = 0
    while remaining > 0 and blueprints:
        blueprint = blueprints[i % len(blueprints)]
        i += 1
        n = 1 if args.question_type == "Q" else min(MAX_QUESTIONS_PER_REQUEST, remaining)
        print(f"generate {blueprint.code} x{n} ({remaining} remaining)")
        result = generate_for_blueprint(
            client,
            template,
            blueprint,
            question_type=args.question_type,
            count=n,
            batch_id=f"{batch_id}-{i:03d}",
            category=category,
            model=args.model,
        )
        if not result:
            continue
        got_questions = result.get("questions", [])
        got_sets = result.get("question_sets", [])
        questions.extend(got_questions)
        question_sets.extend(got_sets)
        remaining -= len(got_sets) if args.question_type == "Q" else len(got_questions)

    batch = {
        "meta": {
            "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "generator": args.model,
            "blueprint_version": "R7",
            "batch_id": batch_id,
        },
        "questions": questions,
        "question_sets": question_sets,
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{batch_id}.json"
    out_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"\nwrote {len(questions)} questions / {len(question_sets)} sets -> {out_path}\n"
        f"next: python scripts/validate_questions.py --file {out_path}\n"
        f"      (validation が pass したら) python backend/manage.py import_questions --file {out_path}"
    )


if __name__ == "__main__":
    main()
