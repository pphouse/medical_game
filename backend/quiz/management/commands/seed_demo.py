from django.core.management.base import BaseCommand

from accounts.models import University
from quiz.categories import normalize
from quiz.models import Question

# Original sample questions written for this demo (not reproductions of real
# CBT/国試 exam content) covering a handful of major clinical categories.
SAMPLE_QUESTIONS = [
    dict(
        question_text="心拍数を低下させる作用をもつ神経伝達物質はどれか。",
        category="循環器",
        exam_type="CBT",
        difficulty=2,
        choices=[
            {"key": "A", "text": "アドレナリン"},
            {"key": "B", "text": "アセチルコリン"},
            {"key": "C", "text": "ドパミン"},
            {"key": "D", "text": "ノルアドレナリン"},
            {"key": "E", "text": "セロトニン"},
        ],
        correct_choice_key="B",
        explanation="心拍数は洞房結節の自動能によって決まり、自律神経による二重支配を受ける。副交感神経である迷走神経の終末から放出されるアセチルコリンは、洞房結節のムスカリンM2受容体に結合し、Gi蛋白を介してcAMPを低下させるとともにK+チャネル（IKACh）を開口させる。その結果、細胞膜が過分極して拡張期脱分極の傾きが緩やかになり、心拍数が低下する（陰性変時作用）。房室結節の伝導も遅くなる。一方、交感神経系のカテコールアミンはβ1受容体を介して心拍数を増加させる。",
        choice_explanations={
            "A": "アドレナリンはβ1受容体を刺激し心拍数を増加させる。",
            "C": "ドパミンは中等量でβ1受容体を刺激し心拍数・心収縮力を増加させる。",
            "D": "ノルアドレナリンは交感神経終末から放出されβ1受容体を介して心拍数を増加させる。",
            "E": "セロトニンは主に血管・消化管・中枢に作用し、心拍数低下の主な伝達物質ではない。",
        },
    ),
    dict(
        question_text="左心房と左心室の間にある弁はどれか。",
        category="循環器",
        exam_type="CBT",
        difficulty=1,
        choices=[
            {"key": "A", "text": "僧帽弁"},
            {"key": "B", "text": "三尖弁"},
            {"key": "C", "text": "大動脈弁"},
            {"key": "D", "text": "肺動脈弁"},
        ],
        correct_choice_key="A",
        explanation="心臓には4つの弁があり、心房と心室の間にある房室弁と、心室と大血管の間にある動脈弁（半月弁）に分けられる。左心房と左心室の間の房室弁は僧帽弁であり、前尖と後尖の2枚の弁尖からなるため二尖弁ともよばれる。僧帽弁は腱索と乳頭筋によって支えられ、収縮期に閉鎖して左房への逆流を防ぐ。右心房と右心室の間には3枚の弁尖をもつ三尖弁がある。僧帽弁狭窄症や僧帽弁閉鎖不全症は頻度の高い弁膜症であり、位置関係とともに確実に覚えておく。",
        choice_explanations={
            "B": "三尖弁は右心房と右心室の間にある房室弁である。",
            "C": "大動脈弁は左心室と大動脈の間にある半月弁である。",
            "D": "肺動脈弁は右心室と肺動脈の間にある半月弁である。",
        },
    ),
    dict(
        question_text="急性心筋梗塞の急性期にみられる特徴的な心電図所見はどれか。",
        category="循環器",
        exam_type="KOKUSHI",
        difficulty=3,
        choices=[
            {"key": "A", "text": "ST上昇"},
            {"key": "B", "text": "ST低下"},
            {"key": "C", "text": "PQ短縮"},
            {"key": "D", "text": "QT短縮"},
            {"key": "E", "text": "P波消失"},
        ],
        correct_choice_key="A",
        explanation="急性心筋梗塞の急性期には、閉塞冠動脈の灌流域に一致した心電図誘導でST上昇（貫壁性虚血を反映）がみられるのが特徴的所見である。",
    ),
    dict(
        question_text="拘束性換気障害を呈する疾患はどれか。",
        category="呼吸器",
        exam_type="CBT",
        difficulty=2,
        choices=[
            {"key": "A", "text": "気管支喘息"},
            {"key": "B", "text": "肺線維症"},
            {"key": "C", "text": "COPD"},
            {"key": "D", "text": "気胸"},
        ],
        correct_choice_key="B",
        explanation="拘束性換気障害は肺の膨らみにくさにより肺容量が減少する病態で、%VCが80%未満となるがFEV1%は保たれる。肺線維症（特発性肺線維症など間質性肺炎）は肺胞壁の線維化により肺コンプライアンスが低下するため、拘束性換気障害の代表である。さらに肺胞壁の肥厚により拡散能（DLCO）が低下し、労作時の低酸素血症をきたしやすい。これに対し、気管支喘息やCOPDは気道の狭窄により呼出が障害される閉塞性換気障害であり、FEV1%が70%未満となる点で区別される。",
        choice_explanations={
            "A": "気管支喘息は可逆性の気道狭窄による閉塞性換気障害である。",
            "C": "COPDは非可逆性の気流閉塞を特徴とする閉塞性換気障害の代表である。",
            "D": "気胸は胸腔内への空気の貯留による肺の虚脱であり、拘束性換気障害の代表疾患としては扱われない。",
        },
    ),
    dict(
        question_text="肺葉の構成で正しいのはどれか。",
        category="呼吸器",
        exam_type="CBT",
        difficulty=1,
        choices=[
            {"key": "A", "text": "右肺は2葉、左肺は3葉"},
            {"key": "B", "text": "右肺は3葉、左肺は2葉"},
            {"key": "C", "text": "左右とも3葉"},
            {"key": "D", "text": "左右とも2葉"},
        ],
        correct_choice_key="B",
        explanation="右肺は水平裂と斜裂により上葉・中葉・下葉の3葉に分かれ、左肺は斜裂のみにより上葉・下葉の2葉に分かれる。左肺は心臓が左側に偏在するため容積がやや小さく、右肺の中葉に相当する部分は左上葉の舌区となっている。肺区域は右10区域、左は8〜10区域とされる。また右主気管支は左より太く短く、急峻に分岐するため、誤嚥物は右肺に入りやすい。肺葉と区域の解剖は画像診断や肺切除術の理解の基礎となる。",
        choice_explanations={
            "A": "左右が逆であり、右肺が3葉、左肺が2葉である。",
            "C": "左肺には中葉がなく、上葉・下葉の2葉である。",
            "D": "右肺は上葉・中葉・下葉の3葉からなる。",
        },
    ),
    dict(
        question_text="COPDで肺の弾性収縮力が低下したことを直接示す所見はどれか。",
        category="呼吸器",
        exam_type="KOKUSHI",
        difficulty=3,
        choices=[
            {"key": "A", "text": "気道抵抗の上昇"},
            {"key": "B", "text": "肺拡散能の低下"},
            {"key": "C", "text": "肺コンプライアンスの上昇"},
            {"key": "D", "text": "残気量の増加"},
            {"key": "E", "text": "1秒率の低下"},
        ],
        correct_choice_key="C",
        explanation="COPDでは肺胞破壊により肺の弾性収縮力が低下し、肺コンプライアンスは上昇する。これに伴い残気量増加・1秒率低下がみられる。",
    ),
    dict(
        question_text="尿素回路〈オルニチン回路〉が行われる臓器はどれか。",
        category="消化器",
        exam_type="CBT",
        difficulty=2,
        choices=[
            {"key": "A", "text": "膵臓"},
            {"key": "B", "text": "肝臓"},
            {"key": "C", "text": "脾臓"},
            {"key": "D", "text": "胆嚢"},
        ],
        correct_choice_key="B",
        explanation="アミノ酸の分解などで生じる有毒なアンモニアは、肝細胞で尿素回路（オルニチン回路）により無毒な尿素に変換され、腎臓から尿中に排泄される。回路の最初の2段階（カルバモイルリン酸合成酵素Iとオルニチントランスカルバモイラーゼ）はミトコンドリア内、残りは細胞質で進行する。肝硬変などで肝機能が低下すると尿素合成が障害されて高アンモニア血症となり、肝性脳症の原因となる。先天的な酵素欠損症としてはOTC欠損症が最も多い。",
        choice_explanations={
            "A": "膵臓は消化酵素やインスリンなどを分泌する臓器で、尿素回路の主座ではない。",
            "C": "脾臓は老化赤血球の破壊や免疫応答を担う臓器である。",
            "D": "胆嚢は肝臓で生成された胆汁を貯留・濃縮する臓器である。",
        },
    ),
    dict(
        question_text="胃前庭部のG細胞から分泌され、胃酸分泌を促進する消化管ホルモンはどれか。",
        category="消化器",
        exam_type="CBT",
        difficulty=1,
        choices=[
            {"key": "A", "text": "セクレチン"},
            {"key": "B", "text": "ガストリン"},
            {"key": "C", "text": "コレシストキニン"},
            {"key": "D", "text": "モチリン"},
        ],
        correct_choice_key="B",
        explanation="ガストリンは胃前庭部（幽門部）のG細胞から分泌される消化管ホルモンで、食物中のペプチドやアミノ酸、胃内pHの上昇、迷走神経刺激（GRP）により分泌が促進される。ガストリンは壁細胞を直接刺激するとともに、ECL細胞からのヒスタミン放出を促して胃酸分泌を強く促進し、胃粘膜の増殖作用ももつ。胃内が酸性になるとD細胞のソマトスタチンを介して分泌が抑制される。ガストリン産生腫瘍ではゾリンジャー・エリソン症候群をきたし、難治性潰瘍を生じる。",
        choice_explanations={
            "A": "セクレチンは十二指腸のS細胞から分泌され、膵からの重炭酸分泌を促し胃酸分泌を抑制する。",
            "C": "コレシストキニンは十二指腸・空腸のI細胞から分泌され、胆嚢収縮と膵酵素分泌を促す。",
            "D": "モチリンは十二指腸・空腸から分泌され、空腹期の消化管運動（伝播性収縮）を促す。",
        },
    ),
    dict(
        question_text="総胆管結石による閉塞性黄疸でみられる検査所見はどれか。",
        category="消化器",
        exam_type="KOKUSHI",
        difficulty=3,
        choices=[
            {"key": "A", "text": "直接ビリルビン優位の高ビリルビン血症"},
            {"key": "B", "text": "間接ビリルビン優位の高ビリルビン血症"},
            {"key": "C", "text": "低アルブミン血症のみ"},
            {"key": "D", "text": "AST/ALT比の著明な低下"},
            {"key": "E", "text": "アンモニアの正常化"},
        ],
        correct_choice_key="A",
        explanation="閉塞性黄疸（総胆管結石など）では胆汁うっ滞により抱合型（直接型）ビリルビンが優位に上昇する。",
    ),
    dict(
        question_text="抗利尿ホルモン〈ADH〉が血中に放出される部位はどれか。",
        category="内分泌代謝",
        exam_type="CBT",
        difficulty=2,
        choices=[
            {"key": "A", "text": "下垂体前葉"},
            {"key": "B", "text": "下垂体後葉"},
            {"key": "C", "text": "視床下部"},
            {"key": "D", "text": "副腎皮質"},
        ],
        correct_choice_key="B",
        explanation="抗利尿ホルモン（ADH、バソプレシン）は視床下部の視索上核・室傍核の神経細胞で産生され、軸索内を輸送されて下垂体後葉の神経終末に貯蔵され、血漿浸透圧の上昇や循環血液量の減少を刺激として血中に放出される。腎集合管のV2受容体に作用してアクアポリン2を管腔側膜に移動させ、水の再吸収を促進する。同様の経路をとるホルモンにオキシトシンがある。これに対し下垂体前葉のホルモンは前葉細胞自身が産生し、視床下部ホルモンが下垂体門脈を介して分泌を調節する。",
        choice_explanations={
            "A": "下垂体前葉はGH・PRL・ACTH・TSH・LH・FSHを産生・分泌する。",
            "C": "視床下部はADHを産生する部位であり、血中への放出は下垂体後葉で行われる。",
            "D": "副腎皮質はコルチゾール・アルドステロン・副腎アンドロゲンを分泌する。",
        },
    ),
    dict(
        question_text="1型糖尿病でインスリンが絶対的に欠乏したときにみられるのはどれか。",
        category="内分泌代謝",
        exam_type="CBT",
        difficulty=2,
        choices=[
            {"key": "A", "text": "低血糖"},
            {"key": "B", "text": "高血糖"},
            {"key": "C", "text": "低カリウム血症"},
            {"key": "D", "text": "低ナトリウム血症"},
        ],
        correct_choice_key="B",
        explanation="1型糖尿病は自己免疫機序などにより膵β細胞が破壊され、インスリンが絶対的に欠乏する病態である。インスリンが欠乏すると筋・脂肪組織へのグルコース取り込みが低下し、肝での糖新生・グリコーゲン分解が亢進するため高血糖となる。さらに脂肪分解が亢進して遊離脂肪酸からケトン体が過剰に産生され、糖尿病ケトアシドーシスをきたしうる。浸透圧利尿による脱水も伴う。治療はインスリン補充が必須であり、ケトアシドーシスでは輸液とインスリン持続静注を行う。",
        choice_explanations={
            "A": "低血糖はインスリン過剰時にみられ、インスリン欠乏では高血糖となる。",
            "C": "インスリン欠乏ではKが細胞外へ移行し、血清Kは正常〜高値を示すことが多い。",
            "D": "高血糖では細胞内から細胞外への水移動により血清Naが低下しうるが、インスリン欠乏の本質的所見ではない。",
        },
    ),
    dict(
        question_text="バセドウ病でみられるTSHと遊離サイロキシン〈FT4〉の組合せはどれか。",
        category="内分泌代謝",
        exam_type="KOKUSHI",
        difficulty=3,
        choices=[
            {"key": "A", "text": "TSH低値・FT4高値"},
            {"key": "B", "text": "TSH高値・FT4低値"},
            {"key": "C", "text": "TSH低値・FT4低値"},
            {"key": "D", "text": "TSH高値・FT4高値"},
            {"key": "E", "text": "TSH・FT4ともに正常"},
        ],
        correct_choice_key="A",
        explanation="バセドウ病に代表される原発性甲状腺機能亢進症では、甲状腺ホルモン過剰によるネガティブフィードバックでTSHが低下し、FT4は上昇する。",
    ),
    dict(
        question_text="短期記憶から長期記憶への固定化に中心的な役割を果たす部位はどれか。",
        category="神経",
        exam_type="CBT",
        difficulty=2,
        choices=[
            {"key": "A", "text": "小脳"},
            {"key": "B", "text": "大脳基底核"},
            {"key": "C", "text": "海馬"},
            {"key": "D", "text": "延髄"},
        ],
        correct_choice_key="C",
        explanation="海馬は側頭葉内側にある大脳辺縁系の構造で、新しく得た情報を短期記憶から長期記憶へ固定化する役割を担う。特に出来事や知識に関する陳述記憶（エピソード記憶・意味記憶）の形成に不可欠であり、長期増強（LTP）がその細胞レベルの基盤と考えられている。両側の海馬が障害されると前向性健忘をきたし、新しいことを覚えられなくなる。アルツハイマー型認知症では早期から海馬の萎縮がみられ、記銘力障害が初発症状となりやすい。",
        choice_explanations={
            "A": "小脳は運動の協調や平衡の調節、運動学習を担う。",
            "B": "大脳基底核は運動の制御や手続き記憶・習慣形成に関与する。",
            "D": "延髄は呼吸・循環中枢などの生命維持機能を担う。",
        },
    ),
    dict(
        question_text="表情筋の運動を支配する脳神経はどれか。",
        category="神経",
        exam_type="CBT",
        difficulty=1,
        choices=[
            {"key": "A", "text": "動眼神経"},
            {"key": "B", "text": "顔面神経"},
            {"key": "C", "text": "三叉神経"},
            {"key": "D", "text": "舌咽神経"},
            {"key": "E", "text": "迷走神経"},
        ],
        correct_choice_key="B",
        explanation="顔面神経（第VII脳神経）は表情筋の運動を支配するほか、アブミ骨筋の運動、舌前2/3の味覚、涙腺・顎下腺・舌下腺の分泌も担う。前額部の筋は両側の大脳皮質から支配を受けるため、中枢性顔面神経麻痺では額のしわ寄せが保たれ、末梢性顔面神経麻痺（ベル麻痺など）では額のしわ寄せも障害される点が鑑別に重要である。末梢性麻痺の障害部位によっては聴覚過敏や味覚障害、涙分泌低下を伴う。",
        choice_explanations={
            "A": "動眼神経は上直筋・下直筋・内直筋・下斜筋・上眼瞼挙筋と瞳孔括約筋を支配する。",
            "C": "三叉神経は顔面の感覚と咀嚼筋の運動を支配する。",
            "D": "舌咽神経は舌後1/3の味覚・感覚や咽頭の感覚、耳下腺の分泌を担う。",
            "E": "迷走神経は咽頭・喉頭の筋の運動や胸腹部内臓の副交感神経支配を担う。",
        },
    ),
    dict(
        question_text="パーキンソン病の中核症状はどれか。",
        category="神経",
        exam_type="KOKUSHI",
        difficulty=3,
        choices=[
            {"key": "A", "text": "安静時振戦・筋強剛・寡動"},
            {"key": "B", "text": "間欠性跛行"},
            {"key": "C", "text": "上位運動ニューロン徴候のみ"},
            {"key": "D", "text": "感覚障害が主体"},
            {"key": "E", "text": "眼球運動障害が主体"},
        ],
        correct_choice_key="A",
        explanation="パーキンソン病の中核症状は安静時振戦・筋強剛（固縮）・寡動（無動）・姿勢反射障害であり、黒質緻密部のドパミン作動性ニューロン変性による。",
    ),
]

# 設問文の書き忘れを import 時点で止める。本文が空でもモデルは保存でき
# （blank=True）、アプリ側は「（本文なし）」と出すだけなので、実際に本番へ
# 15問が本文なしで入っていた。
for _i, _q in enumerate(SAMPLE_QUESTIONS, 1):
    if not _q.get("question_text", "").strip():
        raise ValueError(f"SAMPLE_QUESTIONS[{_i}] に question_text が無い")



class Command(BaseCommand):
    help = (
        "Seed demo University + sample Question data for local development. "
        "--with-batch additionally loads the bundled editorial demo batch "
        "(cbt_batch_core_2026.json) as published official questions (デモ専用: "
        "本番の LLM 生成問題は import_questions + 人手レビューを必ず通すこと)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-batch",
            action="store_true",
            help="Load the bundled cbt_batch_core_2026.json (58問+2四連問) as published demo data",
        )

    def handle(self, *args, **options):
        university, created = University.objects.get_or_create(name="サンプル医科大学")
        self.stdout.write(
            self.style.SUCCESS(f"{'Created' if created else 'Reusing'} university: {university.name}")
        )

        created_count = 0
        for q in SAMPLE_QUESTIONS:
            # 見本の分野名（「内分泌代謝」「消化器」）はどちらの試験の科目名でも
            # ないことがあるので、その試験の科目に寄せる。そのまま入れると
            # 演習画面で「内分泌・代謝」と別の行になる。既存の行は分野名では
            # なく本文で探す（分野名を直すたびに見本が増えないように）。
            _, was_created = Question.objects.get_or_create(
                exam_type=q["exam_type"],
                question_text=q["question_text"],
                defaults=dict(
                    category=normalize(
                        q["category"], q["question_text"], exam_type=q["exam_type"]
                    ),
                    explanation=q["explanation"],
                    choice_explanations=q.get("choice_explanations", {}),
                    difficulty=q["difficulty"],
                    choices=q["choices"],
                    correct_choice_key=q["correct_choice_key"],
                    visibility=Question.Visibility.PUBLIC,
                    # Hand-written demo questions: human-authored, so publish
                    # directly (the pending-review gate is for LLM/user 投稿).
                    status=Question.Status.PUBLISHED,
                    source=Question.Source.OFFICIAL,
                ),
            )
            created_count += int(was_created)

        if options["with_batch"]:
            created_count += self._load_bundled_batch()

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created_count} new questions (total in DB: {Question.objects.count()})."
            )
        )

    def _load_bundled_batch(self):
        """デモ用: リポジトリ同梱の編集バッチを published で直接投入する。

        通常の LLM 生成問題は import_questions（強制 pending）→ 人手レビューを
        通すこと。この同梱バッチはデモ表示用に人手確認済みとして扱う。
        単問（questions）と四連問（question_sets）の両方を公開する。
        """
        import json
        from pathlib import Path

        from quiz.models import QuestionSet

        from .import_questions import (
            DIFFICULTY_MAP,
            build_explanation,
            convert_choices,
        )

        data_path = (
            Path(__file__).resolve().parent / "data" / "cbt_batch_core_2026.json"
        )
        payload = json.loads(data_path.read_text(encoding="utf-8"))
        created = 0

        for q in payload.get("questions", []):
            # build_explanation は（本文, 選択肢ごとの解説）の組を返す。
            explanation, choice_explanations = build_explanation(q)
            _, was_created = Question.objects.get_or_create(
                exam_type=q["exam_type"],
                question_text=q["question_text"],
                choices=convert_choices(q["choices"]),
                defaults=dict(
                    category=normalize(
                        q["category"], q["question_text"], exam_type=q["exam_type"]
                    ),
                    topic=q.get("disease", ""),
                    difficulty=DIFFICULTY_MAP.get(q.get("difficulty", "standard"), 2),
                    question_type=q.get("question_type", Question.QuestionType.MULTIPLE_CHOICE),
                    blueprint_code=q.get("blueprint_code", ""),
                    class_group=q.get("class_group", ""),
                    correct_choice_key=q["correct_choice_id"],
                    explanation=explanation,
                    choice_explanations=choice_explanations,
                    visibility=Question.Visibility.PUBLIC,
                    status=Question.Status.PUBLISHED,
                    source=Question.Source.OFFICIAL,
                ),
            )
            created += int(was_created)

        for s in payload.get("question_sets", []):
            if QuestionSet.objects.filter(case_stem=s["case_stem"]).exists():
                continue
            question_set = QuestionSet.objects.create(
                title=s.get("title") or f"{s.get('disease', s['id'])}の四連問",
                blueprint_code=s.get("blueprint_code", ""),
                case_stem=s["case_stem"],
                status=Question.Status.PUBLISHED,
                source=Question.Source.OFFICIAL,
            )
            for step in s["steps"]:
                step_explanation, step_choice_explanations = build_explanation(step)
                Question.objects.create(
                    category=s["category"],
                    topic=s.get("disease", ""),
                    exam_type=s.get("exam_type", Question.ExamType.CBT),
                    difficulty=DIFFICULTY_MAP.get(s.get("difficulty", "standard"), 2),
                    question_type=Question.QuestionType.SEQUENTIAL,
                    blueprint_code=s.get("blueprint_code", ""),
                    class_group=s.get("class_group", ""),
                    question_set=question_set,
                    set_order=step["set_order"],
                    question_text=step["question_text"],
                    choices=convert_choices(step["choices"]),
                    correct_choice_key=step["correct_choice_id"],
                    explanation=step_explanation,
                    choice_explanations=step_choice_explanations,
                    visibility=Question.Visibility.PUBLIC,
                    status=Question.Status.PUBLISHED,
                    source=Question.Source.OFFICIAL,
                )
                created += 1

        return created
