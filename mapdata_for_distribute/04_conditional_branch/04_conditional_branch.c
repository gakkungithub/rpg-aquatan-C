// 04_conditional_branch.c
int main() {
  // 基本的な条件分岐
  int score = 85;
  if (score == 100) {
    int gradeA = 1;
  } else if (score >= 95) {
    int gradeB = 1;
  } else if (score >= 85) {
    int gradeC = 1;
  } else {
    int gradeF = 1;
  }

  // 変数と三項演算子を使った合否判定
  int passed = (score >= 60) ? 1 : 0;

  // スカラー型との組み合わせ（float型の判定）
  float percentage = 72.5f;
  if (percentage > 90.0f) {
    // 優秀
  } else if (percentage > 75.0f) {
    // 良
  } else if (percentage > 72.5f) {
    // 可
  } else {
    // 不可
  }

  // switch文の応用（評価文字による分類）
  char grade = 'B';
  switch (grade) {
  case 'A':
    // 優
    break;
  case 'B':
    // 良
    break;
  case 'C':
    // 可
    break;
  case 'F':
    // 不可
    break;
  default:
    // 不明
    break;
  }

  // 組み合わせた条件式（論理演算子）
  int age = 20;
  int hasID = 1;
  if ((age >= 18 && hasID) || age >= 65) {
    // 入場許可
  } else {
    // 入場不可
  }

  return 0;
}
