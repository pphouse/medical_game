from django.core.management.base import BaseCommand

from accounts.models import University
from quiz.models import Question

# Original sample questions written for this demo (not reproductions of real
# CBT/国試 exam content) covering a handful of major clinical categories.
SAMPLE_QUESTIONS = [
    dict(
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
        explanation="心臓の洞房結節・房室結節に対して陰性変時作用を持つ主な神経伝達物質は迷走神経終末から放出されるアセチルコリンである。ムスカリン受容体を介して心拍数を低下させる。",
    ),
    dict(
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
        explanation="左房と左室の間に位置する房室弁は僧帽弁（二尖弁）である。三尖弁は右房と右室の間に位置する。",
    ),
    dict(
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
        explanation="肺線維症は肺コンプライアンスが低下する拘束性換気障害の代表であり、%VCの低下とFEV1.0%の維持〜上昇を特徴とする。",
    ),
    dict(
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
        explanation="右肺は上葉・中葉・下葉の3葉、左肺は心臓のスペースを確保するため上葉・下葉の2葉からなる。",
    ),
    dict(
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
        explanation="アンモニアを尿素に変換する尿素回路（オルニチン回路）の主座は肝臓である。",
    ),
    dict(
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
        explanation="胃前庭部のG細胞から分泌されるガストリンは胃酸分泌を促進する代表的な消化管ホルモンである。",
    ),
    dict(
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
        explanation="抗利尿ホルモン（ADH/バソプレシン）は視床下部で産生され、下垂体後葉から血中に放出される。",
    ),
    dict(
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
        explanation="1型糖尿病はインスリン絶対的欠乏によりグルコースの細胞内取り込みが障害され、高血糖・ケトアシドーシスをきたしうる。",
    ),
    dict(
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
        explanation="海馬は短期記憶から長期記憶への固定化（記憶の符号化）に中心的な役割を果たす辺縁系の構造である。",
    ),
    dict(
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
        explanation="表情筋の運動支配を担うのは顔面神経（第VII脳神経）である。末梢性障害ではベル麻痺のように前額のしわ寄せも障害される。",
    ),
    dict(
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


class Command(BaseCommand):
    help = "Seed demo University + sample Question data for local development."

    def handle(self, *args, **options):
        university, created = University.objects.get_or_create(name="サンプル医科大学")
        self.stdout.write(
            self.style.SUCCESS(f"{'Created' if created else 'Reusing'} university: {university.name}")
        )

        created_count = 0
        for q in SAMPLE_QUESTIONS:
            _, was_created = Question.objects.get_or_create(
                category=q["category"],
                exam_type=q["exam_type"],
                explanation=q["explanation"],
                defaults=dict(
                    difficulty=q["difficulty"],
                    choices=q["choices"],
                    correct_choice_key=q["correct_choice_key"],
                    visibility=Question.Visibility.PUBLIC,
                ),
            )
            created_count += int(was_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created_count} new questions (total in DB: {Question.objects.count()})."
            )
        )
