#include <stdio.h>

int main(void) {
  // this is for blocking buffering making it possible to give immediate ouput
  // to stdout (you don't need to understand this function !!)
  setvbuf(stdout, NULL, _IONBF, 0);

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
  int i;
  for (i = 1; i < 6; i++) {
    if (*(p + i) > max) {
      max = *(p + i);
    }
  }

  printf("合計値: %d\n", sum);
  printf("最大値: %d\n", max);

  return 0;
}
