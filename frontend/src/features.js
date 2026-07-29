// Build-time feature flags (Vite env). Keep additions here so gating is
// centralized and greppable.
//
// 学生証アップロード/認証まわりは初期デプロイでは無効（本番運用時に
// Supabase Storage の private bucket を用意してから有効化する）。
// 明示的に "true" のときだけ ON。
export const STUDENT_VERIFICATION_ENABLED =
  import.meta.env.VITE_FEATURE_STUDENT_VERIFICATION === "true";
