// 15_pointer.c
#include <stdio.h>

int main() {
  int x = 10;
  int y = 20;

  // ポインタの宣言と初期化
  int *ptr = &x;

  // ポインタを介して値を取得
  int val = *ptr; // val = 10

  // ポインタを介して値を変更
  *ptr = 15; // x の値が 15 に変更される

  // ポインタの再代入
  ptr = &y;
  *ptr += 5; // y の値が 25 に変更される

  // ポインタと配列
  int arr[5] = {1, 2, 3, 4, 5};
  int *aptr = arr; // arr[0]のアドレス

  for (int i = 0; i < 5; i++) {
    *(aptr + i) = *(aptr + i) * 2; // 要素を2倍
  }

  // ポインタのポインタ
  int **pptr = &ptr;
  **pptr = 100; // y の値が 100 に変更される

  return 0;
}
