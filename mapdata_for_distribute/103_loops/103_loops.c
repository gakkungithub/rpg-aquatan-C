int main(void) {
  float base_calorie = 50.0f; // 1日あたりの基礎消費(軽い活動)
  float total = 0.0f;
  int days = 7; // 1週間分
  int i;

  // 7日分の基礎消費カロリーを合計
  for (i = 0; i < days; i++) {
    total += base_calorie;
  }

  float goal = 500.0f;    // 運動で目指す消費カロリー
  float exercise = 30.0f; // 1回の運動で消費するカロリー
  int session = 0;

  // 目標に届くまで運動を追加
  while (total < goal) {
    total += exercise;
    session++;

    if (session > 100) { // 念のため無限ループ防止
      break;
    }
  }

  return session; // 達成までに必要だった運動回数
}
