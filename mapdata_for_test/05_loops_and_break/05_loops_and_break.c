// 05_loops_and_break.c
int main() {
  // // for文で1〜10まで出力（6でスキップ）
  // int test;
  // int sum = 0;
  // for (int i = 1; i <= 10; i++) {
  //   if (i == 6) {
  //     break;
  //   } else {
  //     if (test == 3) {
  //       test = 5;
  //     } else {
  //       test = 3;
  //     }
  //   }

  //   sum += i;
  // }

  // // while文で偶数のみ合計
  // int j = 0;
  // int evenSum = 0;
  // while (j <= 10) {
  //   if (j % 2 == 0) {
  //     evenSum += j;
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

  // while文とswitch文の組み合わせ
  int l = 3;
  // do {
  //   break;
  // } while (l);
  int k = 4;
  while (k < 5) {
    switch (k) {
    // case 0:
    case 4:
    case 5: {
      static int nnn = 4;
    }

      static int mmm = 4;
      // break;
      {
        static int ll = 3;
      }
      // while (l)
      //   break;
      // do {
      //   l++;
      // } while (l <= 5);

      for (mmm = 2; mmm < 4; mmm++) {
        for (k = 2; k < 4; k++) {
          break;
        }
        mmm++;
      }
    default:
      k += 3;
    }
    k++;
  }

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

// // 05_loops_and_break.c
// int main() {
//   // for文で1〜10まで出力（6でスキップ）
//   // int test;
//   // int sum = 0;
//   // for (int i = 1; i <= 10; i++) {
//   //   if (i == 6) {
//   //     break;
//   //   } else {
//   //     if (test == 3) {
//   //       test = 5;
//   //     } else {
//   //       test = 3;
//   //     }
//   //   }

//   //   sum += i;
//   // }

//   // // while文で偶数のみ合計
//   // int j = 0;
//   // int evenSum = 0;
//   // while (j <= 10) {
//   //   if (j % 2 == 0) {
//   //     evenSum += j;
//   //   }
//   //   j++;
//   // }

//   // while文とswitch文の組み合わせ
//   int k = 4;
//   while (k < 5) {
//     switch (k) {
//     // case 0:
//     case 3:
//     case 5: {
//       // case 0 の処理
//       // k += 3;
//     }
//       static int j = 4;
//       static int ll = 3;
//       static int mmm = 2;
//       // break;
//     // case 1:
//     //   // case 1 の処理
//     //   break;
//     // case 2:
//     //   // case 2 の処理
//     //   break;
//     default:
//       mmm = 3;
//     }
//     k++;
//   }

//   // do-while文の例（最低1回実行される）
//   int l = 0;
//   int factorial = 1;
//   do {
//     if (l == 0) {
//       factorial = 1;
//     } else {
//       factorial += 2;
//     }
//     l++;
//   } while (l <= 5);

//   return 0;
// }
