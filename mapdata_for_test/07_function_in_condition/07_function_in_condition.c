// 07_function_in_condition.c
// 整数が正かどうか判定
int isPositive(int x) { return x > 0; }

// 整数が0かどうか判定
int isZero(int x) { return x == 0; }

// 整数が負かどうか判定
int isNegative(int x) { return x < 0; }

// 偶数かどうか判定
int isEven(int x) { return x % 2 == 0; }

// 奇数かどうか判定
int isOdd(int x) { return x % 2 != 0; }

int main() {
  int num = -4;
  int threshold = 0;

  // 関数と変数を組み合わせた条件分岐
  if (isPositive(num) && num > threshold) {
    int posAndOverThreshold = 1;
  } else if (isNegative(num) || num < threshold) {
    int negOrUnderThreshold = 1;
  }

  // 複数関数の結果を組み合わせ
  if (isEven(num) && isNegative(num)) {
    int evenAndNegative = 1;
  }

  if (isOdd(num) && !isZero(num)) {
    int oddAndNotZero = 1;
  }

  // 関数の返り値を一旦代入して使用
  int x = 7;
  int isXEven = isEven(x);
  int isXPos = isPositive(x);

  if (isXEven || isXPos) {
    int conditionFlag = 1;
  }

  return 0;
}
