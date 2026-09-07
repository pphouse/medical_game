-- 本番の状態を確認するだけ。書き込みは一切しない。
-- 結果をそのまま貼ってもらえれば、どこまで反映されているか分かる。

SELECT '1. 退会テーブル' AS "確認項目",
       CASE WHEN to_regclass('public.accounts_deletedaccount') IS NULL
            THEN '未作成 — migrate_0010_deleted_account.sql を流す（コードのデプロイ前に）'
            ELSE '作成済み' END AS "状態"

UNION ALL SELECT '2. migrate の記録',
       CASE WHEN EXISTS (SELECT 1 FROM django_migrations
                         WHERE app = 'accounts' AND name = '0010_deletedaccount')
            THEN '記録あり（あとで manage.py migrate を通しても二重にならない）'
            ELSE '記録なし' END

UNION ALL SELECT '3. 退会テーブルの RLS',
       COALESCE((SELECT CASE WHEN relrowsecurity THEN '有効' ELSE '無効 — Data API から見える恐れ' END
                 FROM pg_class WHERE relname = 'accounts_deletedaccount'), '—（テーブルが無い）')

UNION ALL SELECT '4. 科目の統合',
       CASE WHEN EXISTS (SELECT 1 FROM quiz_question
                         WHERE category IN ('救急', '中毒', '麻酔科', '中毒・環境'))
            THEN '未反映 — 旧科目名が ' ||
                 (SELECT count(*) FROM quiz_question
                  WHERE category IN ('救急', '中毒', '麻酔科', '中毒・環境'))::text ||
                 '問残っている（apply_categories.sql）'
            ELSE '反映済み（旧科目名は0問）' END

UNION ALL SELECT '5. 統合後の科目',
       COALESCE((SELECT count(*) FROM quiz_question
                 WHERE category = '救急・中毒・麻酔')::text || '問', '0問')

UNION ALL SELECT '6. 感染症 / 放射線科',
       (SELECT count(*) FROM quiz_question WHERE category = '感染症')::text || '問 / ' ||
       (SELECT count(*) FROM quiz_question WHERE category = '放射線科')::text || '問'

UNION ALL SELECT '7. 本文なしの設問',
       (SELECT count(*) FROM quiz_question
        WHERE question_text IS NULL OR btrim(question_text) = '')::text || '問（0であること）'

UNION ALL SELECT '8. 解説が未作成の国試',
       -- 非公開にした設問は学習者に出ないので数えない。ここで status を見ないと、
       -- 図表がないと解けない6問（項目14）を数えてしまう。
       (SELECT count(*) FROM quiz_question
        WHERE exam_type = 'KOKUSHI' AND status = 'published'
          AND (explanation IS NULL OR explanation LIKE '%準備中%'))::text
       || '問が公開中（0であること）／非公開のものを含めると'
       || (SELECT count(*) FROM quiz_question
           WHERE exam_type = 'KOKUSHI'
             AND (explanation IS NULL OR explanation LIKE '%準備中%'))::text || '問'

UNION ALL SELECT '9. choice_explanations 列',
       CASE WHEN NOT EXISTS (SELECT 1 FROM information_schema.columns
                             WHERE table_name = 'quiz_question'
                               AND column_name = 'choice_explanations')
            THEN '無い — migrate_quiz_0009_choice_explanations.sql を流す'
            WHEN EXISTS (SELECT 1 FROM django_migrations
                         WHERE app = 'quiz' AND name = '0009_question_choice_explanations')
            THEN 'あり・記録あり'
            ELSE 'あり・記録なし（あとで migrate すると二重に当たる）' END

UNION ALL SELECT '10. 誤答解説の移行',
       (SELECT count(*) FROM quiz_question
        WHERE exam_type = 'KOKUSHI' AND status = 'published'
          AND explanation LIKE '%【誤答選択肢の解説】%'
          AND choice_explanations = '{}'::jsonb)::text || '問が畳み込まれたまま（0であること）／記録は'
       || CASE WHEN EXISTS (SELECT 1 FROM django_migrations
                            WHERE app = 'quiz' AND name = '0010_backfill_choice_explanations')
               THEN 'あり' ELSE 'なし' END

UNION ALL SELECT '11. 正答が誤っていた1問',
       COALESCE((SELECT '119-C-44 / 正答' || correct_choice_key
                        || ' / 本文' || length(question_text)::text || '字'
                        || ' / 誤答解説'
                        || (SELECT count(*) FROM jsonb_object_keys(choice_explanations))::text || '件'
                 FROM quiz_question WHERE blueprint_code = '119-C-44'),
                '未修正 — 119-C-2 のまま（fix_published_kokushi.sql）')

UNION ALL SELECT '12. 誤った正答で判定された解答',
       (SELECT count(*)::text FROM quiz_answerhistory h
        JOIN quiz_question q ON q.id = h.question_id
        WHERE q.blueprint_code = '119-C-44')
       || '件（0でなければ、その履歴の正誤は誤った正答キーで付いている）'

UNION ALL SELECT '13. 解説を差し替えた4問',
       (SELECT count(*)::text FROM quiz_question
        WHERE blueprint_code IN ('114-B-10', '116-C-41', '116-D-35', '117-A-20')
          AND (SELECT count(*) FROM jsonb_object_keys(choice_explanations)) = 4
          AND explanation LIKE '%出典：厚生労働省%')
       || '問が誤答解説4件・出典ありで揃っている（4であること）'

UNION ALL SELECT '14. 図表がないと解けない6問',
       (SELECT '本番にある' || count(*)::text || '問中、非公開'
               || count(*) FILTER (WHERE status = 'rejected')::text
               || '問／公開中のまま'
               || count(*) FILTER (WHERE status = 'published')::text || '問'
        FROM quiz_question
        WHERE blueprint_code IN ('114-C-14', '117-C-30', '117-E-22',
                                 '117-F-33', '119-C-15', '119-C-22'));
