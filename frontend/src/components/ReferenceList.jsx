import { REFERENCE_GROUPS } from "../references";

/** 出典・参考文献の一覧。外部リンクはネイティブでは in-app ブラウザで開く
 * （nativeBootstrap のクリック処理）。 */
export default function ReferenceList() {
  return (
    <div className="reference-list">
      {REFERENCE_GROUPS.map((group) => (
        <section key={group.title}>
          <h3>{group.title}</h3>
          <ul>
            {group.items.map((item) => (
              <li key={item.url}>
                <a href={item.url} target="_blank" rel="noreferrer">
                  {item.label}
                </a>
                {item.note && <span className="reference-note">{item.note}</span>}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
