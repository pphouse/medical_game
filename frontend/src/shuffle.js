/** 配列をシャッフルした新しい配列を返す（Fisher-Yates）。元の配列は触らない。 */
export function shuffled(arr) {
  const out = arr.slice();
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}
