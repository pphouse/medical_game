-- 本番に「解説準備中」のまま published で残っていた国試7問を直す。
-- 何度流しても結果は同じ。
--
-- ⚠️ 先に quiz.0009（choice_explanations 列）を当てておくこと。未適用のまま
--    流すと `column "choice_explanations" ... does not exist` で落ちる。
--      manage.py migrate --settings=config.settings_migration
--    か、CLI が使えなければ migrate_quiz_0009_choice_explanations.sql。
--    いま何が当たっていないかは diagnose_migrations.sql で分かる。
--    流し方は docs/production-sql.md。
--
-- 内訳（diagnose_missing_explanations.sql の結果どおり）:
--   ・119-C-2   … 本文の冒頭が欠け、正答も誤っている（D → 正しくは B）
--   ・その他6問 … 図表がないと解けない
--
-- あわせて、解説が設問と食い違っていた4問を差し替える（下の (3)）。
--
-- 119-C-44 の内容は kokushi_119.json から、取り込みと同じ変換
-- （import_questions.build_explanation / convert_choices）を通して生成した。

BEGIN;

-- (1) 119-C-2 を、正しい 119-C-44 の内容に直す。
--
-- 取り込み時に症例文の折り返し「2 日前から下腹部痛も…」を設問番号の行と
-- 取り違えて切り出したため本文の冒頭が欠け、正答表の照合先も C002 にずれて
-- D が入っていた。正しくは B「妊娠反応検査」。生殖年齢の女性の不正性器出血で
-- D「子宮内膜組織診」を正答として出すのは実害があるため、これが最優先。
UPDATE quiz_question SET
    blueprint_code      = '119-C-44',
    question_text       = '40歳の女性。性器出血の持続を主訴に来院した。5日前から性器出血を認め、2日前から下腹部痛も伴うようになった。最終月経は4週間前。月経周期は30〜60日、不整、持続5日間。身長153cm、体重50kg。体温36.5°C。脈拍80/分、整。血圧118/64mmHg。呼吸数18/分。腹部は平坦、軟で、肝・脾を触知しない。最初に行う対応はどれか。',
    choices             = '[{"key": "A", "text": "腹部単純CT"}, {"key": "B", "text": "妊娠反応検査"}, {"key": "C", "text": "経腟超音波検査"}, {"key": "D", "text": "子宮内膜組織診"}, {"key": "E", "text": "プロゲステロン投与"}]'::jsonb,
    correct_choice_key  = 'B',
    category            = '産科',
    difficulty          = 2,
    explanation         = '正答は B「妊娠反応検査」。

生殖年齢の女性の不正性器出血では、まず妊娠の有無を確かめる。異所性妊娠や流産を見落とせば命に関わるため、月経不順であっても妊娠反応検査が最初の一歩になる。

出典：厚生労働省ホームページ 第119回医師国家試験 C044',
    choice_explanations = '{"A": "被曝を伴い、妊娠の可能性を否定する前に行うべきではない。", "C": "経腟超音波検査は次に行う重要な検査だが、妊娠反応の結果があってこそ所見を解釈できる。", "D": "子宮内膜組織診は子宮体癌を疑うときに行う。妊娠の可能性を否定してからである。", "E": "プロゲステロン投与は原因を確かめずに行うもので、妊娠中であれば診断を遅らせる。"}'::jsonb
WHERE exam_type = 'KOKUSHI' AND blueprint_code = '119-C-2';

-- (2) 図表がないと解けない6問を非公開にする。
--
-- 削除しないのは、解答履歴が FK の CASCADE でぶら下がっているため。
-- 消すと、この問題を解いた人の学習記録まで一緒に消える。
UPDATE quiz_question SET status = 'rejected'
WHERE exam_type = 'KOKUSHI'
  AND status = 'published'
  AND blueprint_code IN ('114-C-14', '117-C-30', '117-E-22', '117-F-33', '119-C-15', '119-C-22');

-- (3) 解説が設問と食い違っている4問を差し替える。
--
-- kokushi_explanations.sql を作ったあとに直したもので、その SQL には
-- 古い文面が入っている。3問は否定形（「適切でないのはどれか」「誤って
-- いるのはどれか」）の読み違いで、本文が正答とは別の選択肢を推す書き方に
-- なっていた。正答キー自体は正しいので、直すのは解説だけ。
--
-- 文面は現在の設問データから、取り込みと同じ変換
-- （import_questions.build_explanation）を通して生成した。
UPDATE quiz_question AS q
SET explanation = v.explanation,
    choice_explanations = v.choice_explanations::jsonb
FROM (VALUES
    -- 114-B-10: D（基線細変動増加）の理由が抜けていた。誤答4つのうち1つだけ空欄になる。
    ('114-B-10', '正答は E「基線細変動消失」。

基線細変動の消失は、胎児の自律神経系が低酸素やアシドーシスで抑制されていることを示し、胎児機能不全のなかで最も重篤な所見である。

出典：厚生労働省ホームページ 第114回医師国家試験 B010',
     '{"A": "一過性頻脈は胎児が健常であることを示す所見で、懸念すべきものではない。", "B": "早発一過性徐脈は児頭圧迫による生理的な反応で、予後に影響しない。", "C": "変動一過性徐脈は臍帯圧迫によるもので、軽度・散発性なら経過観察でよい。", "D": "基線細変動の増加は急性の低酸素や臍帯圧迫で生じうるが、消失に比べれば重篤度は低く、最も懸念される所見ではない。"}'),
    -- 116-C-41: 「適切でないもの」を選ぶ設問。本文が B（内服薬の確認）を推す書き方になっており、正答 C と食い違っていた。
    ('116-C-41', '正答は C「摂取エネルギー量の制限を指導する。」。

設問は「適切でない」対応を選ぶもの。身長152cm・体重46kg（BMI 19.9）、アルブミン3.4g/dLと低栄養に傾いており、転倒を繰り返す高齢者では筋肉量の維持が転倒予防そのものになる。HbA1c 6.9%は高齢者の目標として良好で、厳格な血糖管理の適応でもない。ここで摂取エネルギー量の制限を指導するのは、フレイルとサルコペニアを進めるだけで不適切である。

出典：厚生労働省ホームページ 第116回医師国家試験 C041',
     '{"A": "転倒を繰り返し、残薬も管理できていない。認知機能の評価は必要で適切である。", "B": "小刻み歩行と筋強剛があり振戦を欠くパーキンソニズムで、薬剤性が疑われる。残薬も多く、内服内容の確認は適切である。", "D": "日中は独居で転倒が多い。在宅支援の導入は適切である。", "E": "高齢者の頭部打撲後は、CTで出血がなくても慢性硬膜下血腫が遅れて現れうる。説明しておくのは適切である。"}'),
    -- 116-D-35: 「誤っているもの」を選ぶ設問。本文が C（特異的IgE抗体）を推す書き方になっており、正答 A と食い違っていた。
    ('116-D-35', '正答は A「肺拡散能検査」。

設問は診断に有用な検査として「誤っている」ものを選ぶもの。製パン工房で働き始めてから、職場にいる日中だけ乾性咳嗽が出て週末には消える。小麦粉抗原による職業性喘息（baker''s asthma）を考える病歴である。肺拡散能検査は間質性肺疾患や肺気腫で低下をみる検査で、気道の可逆性や過敏性を評価するものではなく、この診断には寄与しない。

出典：厚生労働省ホームページ 第116回医師国家試験 D035',
     '{"B": "気道過敏性試験は喘息の本態である気道過敏性を証明でき、有用である。", "C": "小麦粉抗原に対する特異的IgE抗体は職業性の感作を裏づけられる。好酸球12%と花粉症の既往もアトピー素因を支持する。", "D": "気道可逆性試験は気管支拡張薬への反応から可逆性の気流制限を示せる。", "E": "ピークフローの日内変動は、職場にいる日と週末で差が出るかを見られ、職業性喘息の診断に有用である。"}'),
    -- 117-A-20: 「適切でない」対応を選ぶ設問。本文が D（病状認識の確認）を推す書き方になっており、正答 A と食い違っていた。
    ('117-A-20', '正答は A「胃全摘術を予定する。」。

設問は「適切でない」対応を選ぶもの。多発肝転移・リンパ節転移・腹膜播種が確認されており、根治手術の適応はない。患者が手術を希望したからといって胃全摘術を予定するのは医学的適応を欠き、侵襲だけを与えることになる。希望の背景を聴き、病状の理解を確かめたうえで標準治療を共有していく。

出典：厚生労働省ホームページ 第117回医師国家試験 A020',
     '{"B": "「家族と相談してきたい」と申し出ており、家族同席での説明は適切である。", "C": "手術を希望する理由を尋ねることは、本人の価値観や不安を知る手がかりになり適切である。", "D": "本人が病状をどう理解しているかの確認は、説明の出発点として適切である。", "E": "セカンドオピニオンの案内は患者の権利であり、適切である。"}')
) AS v(blueprint_code, explanation, choice_explanations)
WHERE q.exam_type = 'KOKUSHI' AND q.blueprint_code = v.blueprint_code;

-- 確認。Supabase の SQL Editor は最後の SELECT しか表示しないので、
-- 5つの確認を1つの表にまとめてある。この結果をそのまま貼ってもらえれば
-- 当たったかどうか分かる。秘密は含まれない。
SELECT * FROM (
    -- (a) 公開中で解説が入っていない国試。0問なら完了。
    SELECT 'a. 解説なしの公開中の国試' AS 確認項目,
           count(*)::text || '問（0であること）' AS 状態
    FROM quiz_question
    WHERE exam_type = 'KOKUSHI' AND status = 'published'
      AND (explanation IS NULL OR explanation LIKE '%準備中%')

    UNION ALL
    -- (b) 直した1問。正答 B・本文171字・誤答解説4件になっていること。
    SELECT 'b. 119-C-44',
           coalesce(
               (SELECT '正答' || correct_choice_key || ' / ' || category
                       || ' / 本文' || length(question_text)::text || '字'
                       || ' / 誤答解説'
                       || (SELECT count(*) FROM jsonb_object_keys(choice_explanations))::text || '件'
                FROM quiz_question WHERE blueprint_code = '119-C-44'),
               '見つからない（(1) が当たっていない）')

    UNION ALL
    -- (c) 正答が誤っていた間に記録された解答。0でなければ、その履歴は
    --     誤った正答キーで正誤を判定されている。
    SELECT 'c. 誤った正答で判定された解答',
           (SELECT count(*)::text || '件'
            FROM quiz_answerhistory h
            JOIN quiz_question q ON q.id = h.question_id
            WHERE q.blueprint_code = '119-C-44')

    UNION ALL
    -- (d) 差し替えた4問。誤答解説が4件そろい、出典が残っていること。
    SELECT 'd. ' || blueprint_code,
           '誤答解説'
           || (SELECT count(*) FROM jsonb_object_keys(choice_explanations))::text
           || '件（4であること） / 出典'
           || CASE WHEN explanation LIKE '%出典：厚生労働省%' THEN 'あり' ELSE 'なし' END
           || ' / ' || left(split_part(explanation, E'\n\n', 2), 20)
    FROM quiz_question
    WHERE exam_type = 'KOKUSHI'
      AND blueprint_code IN ('114-B-10', '116-C-41', '116-D-35', '117-A-20')

    UNION ALL
    -- (e) 解説がまだ本文に畳み込まれたままの公開中の国試。0でなければ
    --     kokushi_choice_explanations が当たっておらず、誤答の理由が
    --     選択肢の横に出ない。
    SELECT 'e. 畳み込まれたままの国試',
           count(*)::text || '問（0であること）'
    FROM quiz_question
    WHERE exam_type = 'KOKUSHI' AND status = 'published'
      AND explanation LIKE '%【誤答選択肢の解説】%'
      AND choice_explanations = '{}'::jsonb
) AS 確認 ORDER BY 確認項目;

COMMIT;
