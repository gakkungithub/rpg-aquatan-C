int decide_robot_action(int battery, int obstacle_dist, int mode) {
  if (battery < 20) {
    return 3; // 3:充電へ戻る
  } else if (obstacle_dist < 5) {
    return 2; // 2:回避行動
  } else if (mode == 1) {
    return 1; // 1:作業継続
  }
  return 4; // 4:待機
}

int evaluate_action(int action, int battery, int obstacle_dist, int mode) {
  int score = 0;
  switch (action) {
  case 1: // 作業継続
    score = battery * 2 - obstacle_dist;
    break;
  case 2: // 回避
    score = (100 - obstacle_dist) + mode;
    break;
  case 3: // 充電
    score = 200 - battery * 3;
    break;
  default: // 待機
    score = battery + mode * 10;
    break;
  }
  return score;
}

int main(void) {
  int battery = 45;
  int obstacle_dist = 12;
  int mode = 1; // 1:作業モード, 0:非作業モード

  int action = decide_robot_action(battery, obstacle_dist, mode);
  return evaluate_action(action, battery, obstacle_dist, mode);
}
