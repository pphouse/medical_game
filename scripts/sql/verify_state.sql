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
       (SELECT count(*) FROM quiz_question
        WHERE exam_type = 'KOKUSHI'
          AND (explanation IS NULL OR explanation LIKE '%準備中%'))::text || '問（0であること）';
