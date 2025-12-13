// 20_memory_management.c
#include <stdio.h>
#include <stdlib.h>

// 動的メモリ確保と解放
int main() {
  int *data = (int *)malloc(5 * sizeof(int));
  if (!data) {
    fprintf(stderr, "メモリ確保に失敗しました。");
    return 1;
  }

  // // 初期化と利用
  // for (int i = 0; i < 5; i++) {
  //   data[i] = i * i;
  // }

  // // 値の表示
  // for (int i = 0; i < 5; i++) {
  //   printf("data[%d] = %d", i, data[i]);
  // }

  // realloc を使用してサイズ拡張
  int *newData = (int *)realloc(data, 10 * sizeof(int));
  // if (!newData) {
  //   fprintf(stderr, "メモリ再確保に失敗しました。");
  //   free(data);
  //   return 1;
  // }
  data = newData;

  // // 拡張領域に値を格納
  // for (int i = 5; i < 10; i++) {
  //   data[i] = i * i;
  // }

  // // 拡張後の表示
  // for (int i = 0; i < 10; i++) {
  //   printf("data[%d] = %d", i, data[i]);
  // }

  // メモリ解放
  free(data);
  return 0;
}
