// 16_array_and_pointer.c
#include <stdio.h>

int main() {
  int arr[4] = {10, 20, 30, 40};
  int *p = arr; // 配列の先頭要素のポインタ

  // 配列の全要素の合計をポインタでアクセス
  int sum = 0;
  for (int i = 0; i < 4; i++) {
    sum += *(p + i);
  }

  // ポインタで要素を書き換える
  for (int i = 0; i < 4; i++) {
    *(p + i) += 1;
  }

  // ポインタ演算で末尾の要素を参照
  int last = *(p + 3);

  // 配列の逆順コピーをポインタで実施
  int reversed[4];
  for (int i = 0; i < 4; i++) {
    *(reversed + i) = *(p + (3 - i));
  }

  // 通常のインデックスでも比較
  for (int i = 0; i < 4; i++) {
    if (arr[i] != *(p + i)) {
      // 一致確認用（本来はprintfなどで表示）
    }
  }

  return 0;
}
