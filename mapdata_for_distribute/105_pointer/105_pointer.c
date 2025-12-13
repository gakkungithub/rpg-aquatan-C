#include <stdio.h>

int main(void) {
  int data[6] = {10, 25, 7, 42, 18, 30};
  int *p = data; // 配列先頭を指すポインタ
  int sum = 0;
  int max = *p;

  // while文で合計値を求める
  int index = 0;
  while (index < 6) {
    sum += *(p + index); // ポインタ演算でアクセス
    index++;
  }

  // for文で最大値を探す
  for (int i = 1; i < 6; i++) {
    if (*(p + i) > max) {
      max = *(p + i);
    }
  }

  printf("合計値: %d\n", sum);
  printf("最大値: %d\n", max);

  return 0;
}
