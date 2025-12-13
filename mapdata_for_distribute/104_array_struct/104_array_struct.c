#include <stdio.h>

struct Student {
  char name[50];
  int scores[2]; // 2教科の点数
  float average;
};

int main(void) {
  struct Student students[3] = {
      {"Alice", {80, 90}, 0}, {"Bob", {55, 60}, 0}, {"Carol", {95, 88}, 0}};

  // 成績計算と判定
  for (int i = 0; i < 3; i++) {
    int sum = 0;

    // 3科目の合計
    sum += students[i].scores[0];
    sum += students[i].scores[1];

    students[i].average = sum / 2.0f;

    printf("=== %s の成績 ===\n", students[i].name);
    printf("平均点: %.1f\n", students[i].average);

    // 合格判定
    if (students[i].average >= 80) {
      printf("判定: 優秀！\n");
    } else if (students[i].average >= 60) {
      printf("判定: 合格\n");
    } else {
      printf("判定: 不合格\n");
    }

    // 特定の科目が極端に低い場合の警告
    if (students[i].scores[0] < 40 || students[i].scores[1] < 40) {
      printf("※警告: 苦手科目があります。\n");
    }

    printf("\n");
  }

  return 0;
}
