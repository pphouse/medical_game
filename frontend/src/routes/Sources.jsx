import { Link } from "react-router-dom";
import ReferenceList from "../components/ReferenceList";
import { MEDICAL_DISCLAIMER } from "../references";

/** 出典・参考文献。各解説の下と、マイページ・ログイン画面から開ける。 */
export default function Sources() {
  return (
    <div className="screen legal-screen">
      <Link className="back-link" to="/">
        ← 戻る
      </Link>
      <h1>出典・参考文献</h1>

      <div className="mypage-card legal-card">
        <p>
          {"医師国家試験の問題は、厚生労働省が公表している過去問を、表示形式を整えて収録しています。" +
            "各問題の解説の下に、回と問題番号を記載しています。" +
            "解説は、以下の出題基準・コアカリキュラム・診療ガイドラインに基づいて作成しています。"}
        </p>
        <ReferenceList />
        <p className="legal-updated">{MEDICAL_DISCLAIMER}</p>
      </div>
    </div>
  );
}
