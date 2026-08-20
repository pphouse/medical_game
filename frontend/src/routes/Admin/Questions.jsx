import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../api";

const STATUSES = [
  { value: "", label: "すべての状態" },
  { value: "published", label: "公開" },
  { value: "pending", label: "審査待ち" },
  { value: "draft", label: "下書き" },
  { value: "rejected", label: "却下" },
];
const EXAM_TYPES = [
  { value: "", label: "すべての試験" },
  { value: "CBT", label: "CBT" },
  { value: "KOKUSHI", label: "医師国家試験" },
];
const SOURCES = [
  { value: "", label: "すべての出典" },
  { value: "official", label: "公式" },
  { value: "llm", label: "LLM生成" },
  { value: "user", label: "ユーザー投稿" },
];
const STATUS_LABEL = {
  draft: "下書き",
  pending: "審査待ち",
  published: "公開",
  rejected: "却下",
};

export default function AdminQuestions() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  // 入力中の値。検索は Enter / ボタンで確定させる（1文字ごとに叩かない）。
  const [keyword, setKeyword] = useState(searchParams.get("q") ?? "");

  const params = {
    status: searchParams.get("status") ?? "",
    exam_type: searchParams.get("exam_type") ?? "",
    source: searchParams.get("source") ?? "",
    category: searchParams.get("category") ?? "",
    q: searchParams.get("q") ?? "",
    page: searchParams.get("page") ?? "1",
  };

  const load = useCallback(() => {
    setData(null);
    setError(null);
    setSelected(new Set());
    api.adminQuestions(params).then(setData).catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(load, [load]);

  function setParam(key, value) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page"); // 絞り込みを変えたら1ページ目へ
    setSearchParams(next);
  }

  function toggle(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const rows = data?.results ?? [];
  const allOnPageSelected = rows.length > 0 && rows.every((r) => selected.has(r.id));

  async function bulk(status) {
    const ids = [...selected];
    if (ids.length === 0) return;
    if (!window.confirm(`選択した${ids.length}問を「${STATUS_LABEL[status]}」にします。よろしいですか？`)) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api.adminBulkStatus({ ids, status });
      setNotice(`${res.updated}問を「${STATUS_LABEL[status]}」にしました。`);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function bulkAllMatching(status) {
    const total = data?.count ?? 0;
    if (total === 0) return;
    if (
      !window.confirm(
        `絞り込みに一致する${total}問すべてを「${STATUS_LABEL[status]}」にします。取り消せません。よろしいですか？`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // page は絞り込み条件ではないので送らない（サーバ側は件数一致で検証する）
      const filters = { ...params };
      delete filters.page;
      const res = await api.adminBulkStatus({ filters, expected_count: total, status });
      setNotice(`${res.updated}問を「${STATUS_LABEL[status]}」にしました。`);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="admin-block">
        <div className="admin-filters">
          <select value={params.status} onChange={(e) => setParam("status", e.target.value)}>
            {STATUSES.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <select value={params.exam_type} onChange={(e) => setParam("exam_type", e.target.value)}>
            {EXAM_TYPES.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <select value={params.source} onChange={(e) => setParam("source", e.target.value)}>
            {SOURCES.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <form
            className="admin-search"
            onSubmit={(e) => {
              e.preventDefault();
              setParam("q", keyword.trim());
            }}
          >
            <input
              type="search"
              value={keyword}
              placeholder="設問文・解説を検索"
              onChange={(e) => setKeyword(e.target.value)}
            />
            <button type="submit">検索</button>
          </form>
          <Link className="primary-button" to="/admin/questions/new">
            ＋ 新規作成
          </Link>
        </div>
        {params.category && (
          <p className="admin-note">
            分野「{params.category}」で絞り込み中
            <button className="back-link" onClick={() => setParam("category", "")}>
              解除
            </button>
          </p>
        )}
      </div>

      {error && <p className="error">{error}</p>}
      {notice && <p className="admin-notice">{notice}</p>}
      {!data && !error && <p>読み込み中...</p>}

      {data && (
        <>
          <div className="admin-block admin-bulkbar">
            <label>
              <input
                type="checkbox"
                checked={allOnPageSelected}
                onChange={() =>
                  setSelected(allOnPageSelected ? new Set() : new Set(rows.map((r) => r.id)))
                }
              />
              このページを全選択
            </label>
            <span className="admin-note">
              {data.count}問中 {rows.length}問を表示 / {selected.size}問を選択
            </span>
            <div className="admin-bulk-actions">
              <button disabled={busy || selected.size === 0} onClick={() => bulk("published")}>
                公開
              </button>
              <button disabled={busy || selected.size === 0} onClick={() => bulk("pending")}>
                審査待ちに戻す
              </button>
              <button disabled={busy || selected.size === 0} onClick={() => bulk("rejected")}>
                却下
              </button>
              <button
                className="admin-danger"
                disabled={busy || data.count === 0}
                onClick={() => bulkAllMatching("pending")}
              >
                一致する{data.count}問すべてを非公開に
              </button>
            </div>
          </div>

          {rows.length === 0 && <p className="empty-card">該当する問題がありません。</p>}

          <div className="admin-block">
            {rows.map((q) => (
              <div key={q.id} className="admin-row">
                <input
                  type="checkbox"
                  checked={selected.has(q.id)}
                  onChange={() => toggle(q.id)}
                />
                <div className="admin-row-body">
                  <div className="admin-row-meta">
                    <span className={`badge create-status-${q.status}`}>
                      {STATUS_LABEL[q.status]}
                    </span>
                    <span className="badge">{q.exam_type === "CBT" ? "CBT" : "国試"}</span>
                    <span className="badge">{q.category}</span>
                    {q.answer_count > 0 && <span className="badge">解答{q.answer_count}件</span>}
                    {q.report_count > 0 && (
                      <span className="badge admin-danger-badge">通報{q.report_count}件</span>
                    )}
                  </div>
                  <Link to={`/admin/questions/${q.id}`} className="admin-row-text">
                    {q.question_text?.slice(0, 90) || "(設問文なし)"}
                  </Link>
                </div>
              </div>
            ))}
          </div>

          <div className="admin-block admin-pager">
            <button
              disabled={!data.previous}
              onClick={() => setParam("page", String(Number(params.page) - 1))}
            >
              ← 前へ
            </button>
            <span>{params.page}ページ</span>
            <button
              disabled={!data.next}
              onClick={() => setParam("page", String(Number(params.page) + 1))}
            >
              次へ →
            </button>
          </div>
        </>
      )}
    </>
  );
}
