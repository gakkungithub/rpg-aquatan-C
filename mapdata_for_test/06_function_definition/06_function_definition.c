// 06_function_definition.c
// 整数の2乗を返す関数
int square(int x) { return x * x; }

// 整数の最大値を返す関数
int max(int a, int b) { return a > b ? a : b; }

// 整数の最小値を返す関数
int min(int a, int b) { return a < b ? a : b; }

// 符号付き整数の絶対値
int abs(int x) { return x < 0 ? -x : x; }

// 実数の加算（float）
float add_floats(float x, float y) { return x + y; }

// 実数の平均（double）
double average(double a, double b) { return (a + b) / 2.0; }

// 文字を大文字に変換（ASCII限定）
char to_upper(char c) {
  if (c >= 'a' && c <= 'z')
    return c - ('a' - 'A');
  return c;
}

// long型の乗算
long multiply_long(long a, long b) { return a * b; }

int main() {
  int r1 = 5 + square(4);
  // int r2 = max(3, 7);
  // int r3 = abs(-5);
  // int r4 = min(2, 9);

  // float fsum = add_floats(2.5f, 3.2f);
  // double avg = average(5.0, 7.0);
  char upper = to_upper('b');
  // long lprod = multiply_long(1000L, 2000L);

  return 0;
}