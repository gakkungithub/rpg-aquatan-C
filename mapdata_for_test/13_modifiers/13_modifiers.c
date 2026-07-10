// 13_modifier.c
#include <stdio.h>

// 関数呼び出し回数をカウント（static修飾子）
int countUp() {
  static int count = 0; // 静的変数：関数を抜けても値が保持される
  count++;
  return count;
}

// 外部変数（external linkage の例）
int globalCounter = 0; // global な変数

// const修飾子の利用
void printConstValue(const int value) {
  // value = 10; // エラー: constなので書き換え不可
  // printf("固定値: %d", value);
}

int main() {
  // static の効果確認
  int a = countUp(); // 1
  int b = countUp(); // 2
  int c = countUp(); // 3

  // register修飾子（最適化ヒント、現代ではほぼ無視される）
  register int fast = 100;

  // volatile修飾子（I/Oなどに必要な例外的読み書きを示唆）
  volatile int hardwareStatus = 1; // 仮想的にI/Oポート値が変動

  // const変数
  const double pi = 3.14159;
  // pi = 3.14; // エラー：constのため変更できない

  // const引数を使った関数
  printConstValue(42);

  // グローバル変数の変更
  globalCounter++;
  globalCounter += 10;

  return 0;
}
