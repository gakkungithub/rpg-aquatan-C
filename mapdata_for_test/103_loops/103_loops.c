int main(void) {
  float base_calorie = 50.0f; // 1日あたりの基礎消費カロリー
  float total = 0.0f;
  int days = 7;
  int i;

  for (i = 0; i < days; i++) {
    total += base_calorie;
  }

  float goal = 500.0f;    // 目標消費カロリー
  float exercise = 30.0f; // 1回の運動で消費するカロリー
  int session = 0;

  while (total < goal) {
    total += exercise;
    session++;

    if (session > 100) { // 無限ループ防止
      break;
    }
  }

  int cooldown_days = 3;
  int cooldown_count = 0;

  do {
    total -= 10.0f; // クールダウン中は消費量を少し減らす
    cooldown_count++;
  } while (cooldown_count < cooldown_days);

  /* 計算結果を戻り値としてまとめる */
  if (total > goal) {
    return session;
  } else {
    return -1; // 目標未達
  }
}
