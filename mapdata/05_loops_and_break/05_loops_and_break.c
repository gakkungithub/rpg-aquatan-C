// 05_loops_and_break.c
int main() {
  // for文で1〜10まで出力（6でスキップ）
  int test;
  int sum = 0;
  for (int i = 1; i <= 10; i++) {
    if (i == 6) {
      continue;
    } else {
      i++;
    }

    sum += i;
  }

  // // while文で偶数のみ合計
  // int j = 0;
  // int evenSum = 0;
  // while (j <= 10) {
  //   if (j % 2 == 0) {
  //     continue;
  //   }
  //   j++;
  // }

  // while文とswitch文の組み合わせ
  // int k = 0;
  // while (k < 5) {
  //   switch (k) {
  //   case 0:
  //     // case 0 の処理
  //     break;
  //   case 1:
  //     // case 1 の処理
  //     break;
  //   case 2:
  //     // case 2 の処理
  //     break;
  //   default:
  //     // その他の処理
  //     break;
  //   }
  //   k++;
  // }

  // do-while文の例（最低1回実行される）
  // int l = 0;
  // int factorial = 1;
  // do {
  //   if (l == 0) {
  //     factorial = 1;
  //   } else {
  //     factorial += 2;
  //   }
  //   l++;
  // } while (l <= 5);

  return 0;
}
