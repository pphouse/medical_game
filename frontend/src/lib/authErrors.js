// Supabase Auth のエラーは英語で返ってくる（「Email not confirmed」など）。
// 画面にそのまま出すと分かりにくいので、ここで日本語に置き換える。
// 判定は error.code を優先し、code の無い古い形やメールのリンクから戻った
// ときの error_description は文言で拾う。知らないものは元の文言のまま出す。

const BY_CODE = {
  invalid_credentials: "メールアドレスまたはパスワードが正しくありません。",
  email_not_confirmed:
    "メールアドレスの確認が済んでいません。登録時に届いた確認メールのリンクを開いてから、ログインしてください。",
  user_already_exists:
    "このメールアドレスは登録済みです。ログインするか、「パスワードを忘れた方」から再設定してください。",
  email_exists:
    "このメールアドレスは登録済みです。ログインするか、「パスワードを忘れた方」から再設定してください。",
  weak_password: "パスワードが弱すぎます。8文字以上で、推測されにくいものにしてください。",
  same_password: "新しいパスワードが今のパスワードと同じです。別のパスワードにしてください。",
  email_address_invalid: "メールアドレスの形式が正しくありません。",
  validation_failed: "入力内容に誤りがあります。メールアドレスとパスワードを確認してください。",
  over_email_send_rate_limit:
    "メールの送信回数が上限に達しました。しばらく時間をおいてから、もう一度お試しください。",
  over_request_rate_limit: "操作が多すぎます。しばらく時間をおいてから、もう一度お試しください。",
  otp_expired: "メールのリンクの有効期限が切れているか、すでに使われています。もう一度メールを送信してください。",
  flow_state_expired: "ログインの有効期限が切れました。もう一度お試しください。",
  flow_state_not_found:
    "ログインの手続きが見つかりませんでした。メールを送ったのと同じ端末・アプリでリンクを開いてください。",
  bad_code_verifier:
    "ログインの手続きが見つかりませんでした。メールを送ったのと同じ端末・アプリでリンクを開いてください。",
  session_not_found: "ログインの有効期限が切れました。もう一度ログインしてください。",
  session_expired: "ログインの有効期限が切れました。もう一度ログインしてください。",
  user_not_found: "アカウントが見つかりません。",
  signup_disabled: "現在、新規登録を受け付けていません。",
  email_provider_disabled: "現在、メールアドレスでの登録・ログインを受け付けていません。",
};

const BY_TEXT = [
  [/invalid login credentials/i, BY_CODE.invalid_credentials],
  [/email not confirmed/i, BY_CODE.email_not_confirmed],
  [/already (been )?registered|already exists/i, BY_CODE.user_already_exists],
  [/password should (be|contain)|weak password/i, BY_CODE.weak_password],
  [/should be different from the old password/i, BY_CODE.same_password],
  [/email address .* is invalid|invalid email/i, BY_CODE.email_address_invalid],
  [/email rate limit|for security purposes, you can only request/i, BY_CODE.over_email_send_rate_limit],
  [/rate limit|too many requests/i, BY_CODE.over_request_rate_limit],
  [/link is invalid or has expired|otp.*expired|token has expired/i, BY_CODE.otp_expired],
  [/code verifier|flow state/i, BY_CODE.flow_state_not_found],
  [/session.*(missing|not found)|auth session missing/i, BY_CODE.session_not_found],
  [/signups not allowed/i, BY_CODE.signup_disabled],
  [/failed to fetch|load failed|network ?error|networkerror/i,
    "通信に失敗しました。電波の良いところで、もう一度お試しください。"],
];

/** Supabase Auth のエラー（または Error・文字列）を、画面に出す日本語にする。 */
export function authErrorMessage(err) {
  if (!err) return "";
  const code = typeof err === "object" ? err.code : null;
  if (code && BY_CODE[code]) return BY_CODE[code];
  const text = typeof err === "string" ? err : (err.message ?? String(err));
  for (const [pattern, message] of BY_TEXT) {
    if (pattern.test(text)) return message;
  }
  if (typeof err === "object" && err.status === 429) return BY_CODE.over_request_rate_limit;
  return text;
}
