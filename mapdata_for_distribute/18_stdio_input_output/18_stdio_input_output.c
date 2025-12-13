// 18_stdio_input_output.c
#include <stdio.h>

int test() { return 2; }

// 標準入力・出力・エラー出力
int main() {
  // setvbufでバッファリングを無効化しないとstdoutが行バッファリングされ、改行やバッファ満杯まで出力が遅れるため即時に表示されない
  setvbuf(stdout, NULL, _IONBF, 0);
  printf("整数を入力してください:\n");
  int x, y;
  if (scanf("%d %d", &x, &y) != 2) {
    fprintf(stderr, "入力エラー\n");
    fprintf(stdout, "%d\n", x);
    return 1;
  }

  printf("入力された数値は: %d\n", x);

  // 数値が偶数か奇数かを出力
  if (x % 2 == 0) {
    printf("%d は偶数です。\n", x);
  } else {
    printf("%d は奇数です。\n", x);
  }

  // 入力値に応じたメッセージ（switch文）
  switch (x) {
  case 0:
    printf("ゼロが入力されました。\n");
    break;
  case 1:
    printf("1 が入力されました。\n");
    break;
  default:
    printf("その他の値が入力されました。\n");
    break;
  }

  return 0;
}
